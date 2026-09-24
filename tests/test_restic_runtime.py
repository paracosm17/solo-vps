from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

from scripts import restic_runtime as runtime


CONFIG = runtime.RuntimeConfig(
    repository="s3:https://storage.example.net/solo-vps/solo-vps/prod-01",
    region="us-east-1",
    host="prod-01",
    sources=("/data/coolify",),
    excludes=("/data/coolify/ssh/mux", "/data/coolify/databases", "/data/coolify/backups"),
    tag="solo-vps",
    group_by="host,tags",
    retention=dict(runtime.EXPECTED_RETENTION),
    freshness_hours=36,
    cache_dir="/var/cache/solo-vps/restic",
)
CREDS = {
    "AWS_ACCESS_KEY_ID": "access",
    "AWS_SECRET_ACCESS_KEY": "secret",
    "RESTIC_PASSWORD": "password",
}


def snapshot(*, when: datetime, paths=None, host="prod-01", tags=None, sid="a" * 64):
    return {
        "time": when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "paths": paths or ["/data/coolify"],
        "hostname": host,
        "tags": tags or ["solo-vps"],
        "id": sid,
    }


class FakeRunner:
    def __init__(self, snapshots=None, fail_commands=None):
        self.snapshots = list(snapshots or [])
        self.fail_commands = set(fail_commands or [])
        self.commands = []
        self.environments = []

    def __call__(self, command, **kwargs):
        self.commands.append(list(command))
        env = dict(kwargs.get("env") or {})
        if env.get("RESTIC_PASSWORD_FILE"):
            env["__password_file_content"] = Path(env["RESTIC_PASSWORD_FILE"]).read_text(encoding="utf-8")
        if env.get("AWS_SHARED_CREDENTIALS_FILE"):
            env["__aws_file_content"] = Path(env["AWS_SHARED_CREDENTIALS_FILE"]).read_text(encoding="utf-8")
        self.environments.append(env)
        verb = command[1] if len(command) > 1 else ""
        if verb in self.fail_commands:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr=f"{verb} failed")
        if verb == "snapshots":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(self.snapshots), stderr="")
        if verb == "backup":
            self.snapshots.append(snapshot(when=datetime.now(timezone.utc), sid="b" * 64))
        if verb == "init":
            self.snapshots = []
        if verb == "restore":
            target = Path(command[command.index("--target") + 1])
            (target / "data/coolify/source").mkdir(parents=True)
            (target / "data/coolify/source/.env").write_text("APP_KEY=synthetic\n", encoding="utf-8")
            (target / "data/coolify/ssh/keys").mkdir(parents=True)
            (target / "data/coolify/marker").write_text("restored", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")


class ResticRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.secret_tmp = tempfile.TemporaryDirectory()
        self.secret_root_patch = mock.patch.object(runtime, "RUNTIME_SECRET_ROOT", Path(self.secret_tmp.name))
        self.secret_root_patch.start()
        self.cache_patch = mock.patch.object(runtime, "_require_private_cache")
        self.cache_patch.start()

    def tearDown(self) -> None:
        self.cache_patch.stop()
        self.secret_root_patch.stop()
        self.secret_tmp.cleanup()

    def patch_restic(self):
        return mock.patch.object(runtime, "RESTIC", Path(sys.executable))

    def patch_staging_owner(self, target: Path, *, uid: int, gid: int):
        resolved_target = target.resolve()
        real_lstat = Path.lstat

        def lstat_with_owner(path: Path):
            metadata = real_lstat(path)
            if path == resolved_target:
                return types.SimpleNamespace(
                    st_mode=metadata.st_mode,
                    st_uid=uid,
                    st_gid=gid,
                )
            return metadata

        return mock.patch.object(Path, "lstat", autospec=True, side_effect=lstat_with_owner)

    def test_child_environment_uses_private_files_not_secret_environment_values(self):
        fake = FakeRunner([])
        with self.patch_restic():
            runtime.run_restic(["snapshots", "--json"], CONFIG, CREDS, runner=fake)
        env = fake.environments[0]
        self.assertEqual(env["RESTIC_REPOSITORY"], CONFIG.repository)
        self.assertNotIn("RESTIC_PASSWORD", env)
        self.assertNotIn("AWS_ACCESS_KEY_ID", env)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", env)
        self.assertEqual(env["__password_file_content"], "password\n")
        self.assertIn("aws_access_key_id = access", env["__aws_file_content"] )
        self.assertIn("aws_secret_access_key = secret", env["__aws_file_content"] )
        self.assertNotIn("GITHUB_TOKEN", env)

    def test_runtime_config_requires_private_root_file(self):
        payload = {
            "version": 1,
            "repository": CONFIG.repository,
            "region": CONFIG.region,
            "host": CONFIG.host,
            "sources": list(CONFIG.sources),
            "excludes": list(CONFIG.excludes),
            "tag": CONFIG.tag,
            "group_by": CONFIG.group_by,
            "retention": CONFIG.retention,
            "freshness_hours": CONFIG.freshness_hours,
            "cache_dir": CONFIG.cache_dir,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            path.chmod(0o644)
            with self.assertRaises(runtime.ResticRuntimeError):
                runtime.load_runtime_config(path)
        encoded = json.dumps(payload).encode("utf-8")
        with mock.patch.object(runtime, "_read_regular_private_file", return_value=encoded):
            loaded = runtime.load_runtime_config(Path("/synthetic/runtime.json"))
        self.assertEqual(loaded.repository, CONFIG.repository)

    def test_backup_arguments_keep_reviewed_scope_and_grouping(self):
        args = runtime._backup_args(CONFIG)
        self.assertEqual(args[:2], ["backup", "/data/coolify"])
        self.assertIn("host,tags", args)
        self.assertIn("/data/coolify/ssh/mux", args)
        self.assertNotIn("/var/lib/docker", args)
        self.assertNotIn("/var/lib/postgresql", args)

    def test_retention_plan_is_dry_run_and_apply_prunes(self):
        plan = runtime._retention_args(CONFIG, dry_run=True)
        apply = runtime._retention_args(CONFIG, dry_run=False)
        self.assertIn("--dry-run", plan)
        self.assertNotIn("--prune", plan)
        self.assertIn("--prune", apply)
        self.assertNotIn("--dry-run", apply)
        self.assertEqual(plan[plan.index("--keep-daily") + 1], "14")

    def test_latest_snapshot_ignores_wrong_path_or_tag(self):
        now = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)
        fake = FakeRunner([
            snapshot(when=now - timedelta(hours=1), paths=["/other"], sid="1" * 64),
            snapshot(when=now - timedelta(hours=2), tags=["other"], sid="2" * 64),
            snapshot(when=now - timedelta(hours=3), sid="3" * 64),
        ])
        with self.patch_restic():
            evidence = runtime.latest_snapshot(CONFIG, CREDS, runner=fake, now=now)
        self.assertEqual(evidence.snapshot_id, "3" * 64)
        self.assertAlmostEqual(evidence.age_hours, 3.0)

    def test_freshness_rejects_stale_snapshot(self):
        now = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)
        fake = FakeRunner([snapshot(when=now - timedelta(hours=40))])
        with self.patch_restic(), self.assertRaises(runtime.ResticRuntimeError):
            runtime.require_fresh_snapshot(CONFIG, CREDS, runner=fake, now=now)

    def test_repository_adopt_requires_access_then_check(self):
        fake = FakeRunner([])
        with self.patch_restic():
            runtime.repository_adopt(CONFIG, CREDS, runner=fake)
        verbs = [cmd[1] for cmd in fake.commands]
        self.assertEqual(verbs, ["snapshots", "check"])

    def test_repository_init_refuses_existing_repository(self):
        fake = FakeRunner([])
        with self.patch_restic(), self.assertRaises(runtime.ResticRuntimeError):
            runtime.repository_init(CONFIG, CREDS, runner=fake)
        self.assertEqual([cmd[1] for cmd in fake.commands], ["snapshots"])

    def test_repository_init_runs_init_when_initial_probe_fails(self):
        class InitRunner(FakeRunner):
            first = True
            def __call__(self, command, **kwargs):
                if len(command) > 1 and command[1] == "snapshots" and self.first:
                    self.first = False
                    self.commands.append(list(command))
                    self.environments.append(dict(kwargs.get("env") or {}))
                    return subprocess.CompletedProcess(command, 1, stdout="", stderr="repository does not exist")
                return super().__call__(command, **kwargs)
        fake = InitRunner([])
        with self.patch_restic():
            runtime.repository_init(CONFIG, CREDS, runner=fake)
        self.assertEqual([cmd[1] for cmd in fake.commands], ["snapshots", "init", "snapshots"])

    def test_backup_requires_existing_source(self):
        fake = FakeRunner([])
        with self.patch_restic(), mock.patch.object(runtime, "_require_sources", side_effect=runtime.ResticRuntimeError("missing")):
            with self.assertRaises(runtime.ResticRuntimeError):
                runtime.backup_now(CONFIG, CREDS, runner=fake)
        self.assertEqual(fake.commands, [])

    def test_backup_creates_fresh_snapshot(self):
        fake = FakeRunner([])
        with self.patch_restic(), mock.patch.object(runtime, "_require_sources"):
            evidence = runtime.backup_now(CONFIG, CREDS, runner=fake)
        self.assertEqual([cmd[1] for cmd in fake.commands], ["snapshots", "backup", "snapshots"])
        self.assertLess(evidence.age_hours, 1)

    def test_check_runs_integrity_before_freshness(self):
        now = datetime.now(timezone.utc)
        fake = FakeRunner([snapshot(when=now - timedelta(hours=1))])
        with self.patch_restic():
            runtime.check_repository(CONFIG, CREDS, runner=fake)
        self.assertEqual([cmd[1] for cmd in fake.commands], ["check", "snapshots"])

    def test_restore_test_materializes_expected_tree_and_removes_temp(self):
        now = datetime.now(timezone.utc)
        fake = FakeRunner([snapshot(when=now - timedelta(hours=1))])
        created = []
        real_mkdtemp = tempfile.mkdtemp
        def tracked_mkdtemp(*args, **kwargs):
            value = real_mkdtemp(*args, **kwargs); created.append(Path(value)); return value
        with self.patch_restic(), mock.patch.object(runtime.tempfile, "mkdtemp", side_effect=tracked_mkdtemp):
            evidence = runtime.restore_test(CONFIG, CREDS, runner=fake)
        self.assertLess(evidence.age_hours, 2)
        self.assertEqual([cmd[1] for cmd in fake.commands], ["snapshots", "restore"])
        self.assertTrue(created)
        self.assertFalse(created[0].exists())


    def test_restore_staging_requires_exact_confirmation(self):
        now = datetime.now(timezone.utc)
        fake = FakeRunner([snapshot(when=now - timedelta(hours=1))])
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "recovery"
            parent.mkdir(mode=0o700)
            target = parent / "run-1"
            target.mkdir(mode=0o700)
            with self.patch_restic(), mock.patch.object(runtime, "RECOVERY_STAGING_PARENT", parent):
                with self.assertRaises(runtime.ResticRuntimeError):
                    runtime.restore_staging(CONFIG, CREDS, target=target, confirmation="wrong", runner=fake)
        self.assertEqual(fake.commands, [])

    def test_restore_staging_rejects_non_root_owned_target(self):
        now = datetime.now(timezone.utc)
        fake = FakeRunner([snapshot(when=now - timedelta(hours=1))])
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "recovery"
            parent.mkdir(mode=0o700)
            target = parent / "run-1"
            target.mkdir(mode=0o700)
            with (
                self.patch_restic(),
                mock.patch.object(runtime, "RECOVERY_STAGING_PARENT", parent),
                self.patch_staging_owner(target, uid=1000, gid=1000),
            ):
                with self.assertRaises(runtime.ResticRuntimeError) as ctx:
                    runtime.restore_staging(
                        CONFIG,
                        CREDS,
                        target=target,
                        confirmation=runtime.RECOVERY_STAGING_CONFIRMATION,
                        runner=fake,
                    )
        self.assertIn("root:root with mode 0700", str(ctx.exception))
        self.assertEqual(fake.commands, [])

    def test_restore_staging_requires_empty_private_direct_child(self):
        now = datetime.now(timezone.utc)
        fake = FakeRunner([snapshot(when=now - timedelta(hours=1))])
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "recovery"
            parent.mkdir(mode=0o700)
            target = parent / "run-1"
            target.mkdir(mode=0o700)
            (target / "existing").write_text("do not overwrite", encoding="utf-8")
            with (
                self.patch_restic(),
                mock.patch.object(runtime, "RECOVERY_STAGING_PARENT", parent),
                self.patch_staging_owner(target, uid=0, gid=0),
            ):
                with self.assertRaises(runtime.ResticRuntimeError) as ctx:
                    runtime.restore_staging(
                        CONFIG,
                        CREDS,
                        target=target,
                        confirmation=runtime.RECOVERY_STAGING_CONFIRMATION,
                        runner=fake,
                    )
        self.assertIn("must be empty before restore", str(ctx.exception))
        self.assertEqual(fake.commands, [])

    def test_restore_staging_materializes_selective_recovery_tree(self):
        now = datetime.now(timezone.utc)
        fake = FakeRunner([snapshot(when=now - timedelta(hours=1))])
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "recovery"
            parent.mkdir(mode=0o700)
            target = parent / "run-1"
            target.mkdir(mode=0o700)
            with (
                self.patch_restic(),
                mock.patch.object(runtime, "RECOVERY_STAGING_PARENT", parent),
                self.patch_staging_owner(target, uid=0, gid=0),
            ):
                evidence = runtime.restore_staging(
                    CONFIG,
                    CREDS,
                    target=target,
                    confirmation=runtime.RECOVERY_STAGING_CONFIRMATION,
                    runner=fake,
                )
            self.assertLess(evidence.age_hours, 2)
            self.assertTrue((target / "data/coolify/source/.env").is_file())
            self.assertTrue((target / "data/coolify/ssh/keys").is_dir())
            self.assertFalse((target / "data/coolify/databases").exists())
            self.assertEqual([cmd[1] for cmd in fake.commands], ["snapshots", "restore"])

    def test_restic_failure_is_bounded_and_does_not_echo_environment_secrets(self):
        fake = FakeRunner([], fail_commands={"check"})
        with self.patch_restic(), self.assertRaises(runtime.ResticRuntimeError) as ctx:
            runtime.run_restic(["check"], CONFIG, CREDS, runner=fake)
        message = str(ctx.exception)
        self.assertIn("check failed", message)
        self.assertNotIn("secret", message)
        self.assertNotIn("password", message)


if __name__ == "__main__":
    unittest.main()
