from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
import io
import os
from unittest import mock

from scripts.coolify_database_backup_api import (
    APPLY_CONFIRMATION,
    BackupPlan,
    CoolifyApiClient,
    DatabaseBackupError,
    adopt_schedule,
    build_plan,
    configure_schedule,
    load_state,
    normalize_base_url,
    trigger_backup,
    validate_execution,
    validate_schedule,
    verify_schedule,
    write_state,
)

DB_UUID = "database123"
S3_UUID = "storage123"
BACKUP_UUID = "backup123"


def plan(**overrides) -> BackupPlan:
    values = dict(
        base_url="http://127.0.0.1:8000/api/v1",
        database_uuid=DB_UUID,
        s3_storage_uuid=S3_UUID,
        frequency="daily",
        databases_to_backup="app",
        dump_all=False,
        enabled=True,
        retention_amount_locally=2,
        retention_days_s3=30,
        freshness_hours=36,
    )
    values.update(overrides)
    return build_plan(**values)


def schedule(**overrides):
    value = {"uuid": BACKUP_UUID, **plan().desired_payload}
    value.update(overrides)
    return value


def execution(**overrides):
    value = {
        "uuid": "execution123",
        "filename": "pg-dump-app-123.dmp",
        "size": 1024,
        "created_at": "2026-08-17T10:00:00+00:00",
        "message": "Database backup successful",
        "status": "success",
    }
    value.update(overrides)
    return value


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, payload=None):
        self.calls.append((method, url, payload))
        if not self.responses:
            raise AssertionError("unexpected request")
        return self.responses.pop(0)


class CoolifyDatabaseBackupTests(unittest.TestCase):
    def test_loopback_contract(self):
        self.assertEqual(normalize_base_url("http://127.0.0.1:8000/api/v1"), "http://127.0.0.1:8000/api/v1")
        self.assertEqual(normalize_base_url("http://127.0.0.1:18000/api/v1"), "http://127.0.0.1:18000/api/v1")
        for bad in ("https://127.0.0.1:8000/api/v1", "http://localhost:8000/api/v1", "http://203.0.113.10:8000/api/v1"):
            with self.subTest(bad=bad), self.assertRaises(DatabaseBackupError):
                normalize_base_url(bad)

    def test_plan_requires_s3_and_exact_database_selection(self):
        p = plan()
        self.assertTrue(p.desired_payload["save_s3"])
        self.assertEqual(p.desired_payload["databases_to_backup"], "app")
        self.assertEqual(p.desired_payload["database_backup_retention_days_s3"], 30)
        with self.assertRaises(DatabaseBackupError):
            plan(databases_to_backup="", dump_all=False)
        with self.assertRaises(DatabaseBackupError):
            plan(databases_to_backup="app", dump_all=True)

    def test_dump_all_is_explicit(self):
        p = plan(databases_to_backup="", dump_all=True)
        self.assertTrue(p.dump_all)
        self.assertEqual(p.databases_to_backup, "")

    def test_schedule_drift_fails_closed(self):
        validate_schedule(schedule(), plan(), BACKUP_UUID)
        with self.assertRaises(DatabaseBackupError):
            validate_schedule(schedule(save_s3=False), plan(), BACKUP_UUID)
        with self.assertRaises(DatabaseBackupError):
            validate_schedule(schedule(database_backup_retention_days_s3=7), plan(), BACKUP_UUID)

    def test_state_is_atomic_external_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "db-state"
            path = write_state(state_dir, DB_UUID, BACKUP_UUID)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(state_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(load_state(state_dir, DB_UUID)["backup_uuid"], BACKUP_UUID)

    def test_create_refuses_existing_unmanaged_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient([[schedule()]])
            with self.assertRaisesRegex(DatabaseBackupError, "Adopt"):
                configure_schedule(client, plan(), Path(tmp))
            self.assertEqual(len(client.calls), 1)

    def test_create_when_no_schedule_persists_uuid_and_rechecks(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient([[], {"uuid": BACKUP_UUID}, [schedule()]])
            backup_uuid, outcome = configure_schedule(client, plan(), Path(tmp))
            self.assertEqual((backup_uuid, outcome), (BACKUP_UUID, "created"))
            self.assertEqual(client.calls[1][0], "POST")
            self.assertEqual(client.calls[1][2], plan().desired_payload)
            self.assertEqual(load_state(Path(tmp), DB_UUID)["backup_uuid"], BACKUP_UUID)

    def test_update_owned_schedule_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_state(Path(tmp), DB_UUID, BACKUP_UUID)
            client = FakeClient([[schedule()], {}, [schedule()]])
            backup_uuid, outcome = configure_schedule(client, plan(), Path(tmp))
            self.assertEqual((backup_uuid, outcome), (BACKUP_UUID, "updated"))
            self.assertEqual(client.calls[1], ("PATCH", plan().schedule_url(BACKUP_UUID), plan().desired_payload))

    def test_adoption_requires_exact_matching_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient([[schedule()]])
            adopt_schedule(client, plan(), Path(tmp), BACKUP_UUID)
            self.assertEqual(load_state(Path(tmp), DB_UUID)["backup_uuid"], BACKUP_UUID)
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient([[schedule(save_s3=False)]])
            with self.assertRaises(DatabaseBackupError):
                adopt_schedule(client, plan(), Path(tmp), BACKUP_UUID)

    def test_fresh_execution_is_accepted(self):
        evidence = validate_execution(execution(), plan(), now=datetime(2026, 8, 17, 11, 0, tzinfo=timezone.utc))
        self.assertEqual(evidence["status"], "success")
        self.assertEqual(evidence["age_hours"], 1.0)

    def test_stale_failed_zero_size_or_s3_warning_is_rejected(self):
        now = datetime(2026, 8, 19, 0, 0, tzinfo=timezone.utc)
        for item in (
            execution(status="failed"),
            execution(size=0),
            execution(message="Backup successful locally, S3 upload failed"),
            execution(),
        ):
            with self.subTest(item=item), self.assertRaises(DatabaseBackupError):
                validate_execution(item, plan(freshness_hours=1), now=now)

    def test_verify_requires_owned_schedule_and_latest_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_state(Path(tmp), DB_UUID, BACKUP_UUID)
            client = FakeClient([[schedule()], {"executions": [execution()]}])
            result = verify_schedule(client, plan(), Path(tmp), now=datetime(2026, 8, 17, 11, 0, tzinfo=timezone.utc))
            self.assertEqual(result["schedule"], "MATCHED")
            self.assertFalse(result["s3_object_independently_verified"])

    def test_trigger_uses_backup_now_and_new_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_state(Path(tmp), DB_UUID, BACKUP_UUID)
            before = execution(uuid="oldexecution", created_at="2026-08-17T08:00:00+00:00")
            new = execution(uuid="newexecution", created_at=datetime.now(timezone.utc).isoformat())
            client = FakeClient([[schedule()], {"executions": [before]}, {}, {"executions": [before]}, {"executions": [new, before]}])
            clock = iter([0.0, 0.1, 0.2])
            result = trigger_backup(client, plan(), Path(tmp), poll_interval=0, timeout=10, sleeper=lambda _: None, monotonic=lambda: next(clock))
            self.assertEqual(result["execution_uuid"], "newexecution")
            self.assertEqual(client.calls[2], ("PATCH", plan().schedule_url(BACKUP_UUID), {"backup_now": True}))

    def test_trigger_failure_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_state(Path(tmp), DB_UUID, BACKUP_UUID)
            failed = execution(uuid="newexecution", status="failed", created_at=datetime.now(timezone.utc).isoformat())
            client = FakeClient([[schedule()], {"executions": []}, {}, {"executions": [failed]}])
            with self.assertRaises(DatabaseBackupError):
                trigger_backup(client, plan(), Path(tmp), poll_interval=0, sleeper=lambda _: None)

    def test_api_token_is_header_only(self):
        captured = {}

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b'{}'

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["auth"] = request.headers["Authorization"]
            captured["body"] = request.data or b""
            return Response()

        client = CoolifyApiClient("123|very-secret", opener=opener)
        client.request("PATCH", plan().schedule_url(BACKUP_UUID), {"backup_now": True})
        self.assertEqual(captured["auth"], "Bearer 123|very-secret")
        self.assertNotIn("very-secret", captured["url"])
        self.assertNotIn(b"very-secret", captured["body"])

    def test_state_loader_rejects_permissive_state_directory_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            write_state(state_dir, "database123", "backup123")
            os.chmod(state_dir, 0o755)
            with self.assertRaisesRegex(DatabaseBackupError, "0700"):
                load_state(state_dir, "database123")
            os.chmod(state_dir, 0o700)
            os.chmod(state_dir / "database123.json", 0o644)
            with self.assertRaisesRegex(DatabaseBackupError, "0600"):
                load_state(state_dir, "database123")

    def test_http_error_diagnostic_redacts_bearer_token(self):
        token = "token-value-that-must-not-print"
        error = HTTPError("http://127.0.0.1:8000/api/v1/test", 422, "bad", {}, io.BytesIO(("echo " + token).encode()))
        client = CoolifyApiClient(token, opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(error))
        with self.assertRaises(DatabaseBackupError) as caught:
            client.request("GET", "http://127.0.0.1:8000/api/v1/test")
        self.assertNotIn(token, str(caught.exception))
        self.assertIn("[REDACTED]", str(caught.exception))

    def test_confirmation_constant_is_explicit(self):
        self.assertEqual(APPLY_CONFIRMATION, "I_HAVE_REVIEWED_THE_COOLIFY_DATABASE_BACKUP_POLICY")


if __name__ == "__main__":
    unittest.main()
