#!/usr/bin/env python3
"""Operate one Coolify-owned PostgreSQL backup schedule through loopback API.

This helper deliberately does not run pg_dump itself. Coolify owns the database
lifecycle and scheduled logical backup. Solo VPS only configures/verifies one
explicitly owned schedule and records its UUID outside the source checkout.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"
SSH_TUNNEL_BASE_URL = "http://127.0.0.1:18000/api/v1"
_ALLOWED_BASE_URLS = {DEFAULT_BASE_URL, SSH_TUNNEL_BASE_URL}
UUID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
DATABASE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,63}$")
APPLY_CONFIRMATION = "I_HAVE_REVIEWED_THE_COOLIFY_DATABASE_BACKUP_POLICY"
SUCCESS_STATUSES = {"success", "successful", "succeeded", "finished", "completed"}
FAILURE_STATUSES = {"failed", "failure", "error", "cancelled", "canceled"}


class DatabaseBackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupPlan:
    base_url: str
    database_uuid: str
    s3_storage_uuid: str
    frequency: str
    databases_to_backup: str
    dump_all: bool
    enabled: bool
    retention_amount_locally: int
    retention_days_s3: int
    freshness_hours: int

    @property
    def backups_url(self) -> str:
        return f"{self.base_url}/databases/{quote(self.database_uuid, safe='')}/backups"

    def schedule_url(self, backup_uuid: str) -> str:
        return f"{self.backups_url}/{quote(backup_uuid, safe='')}"

    def executions_url(self, backup_uuid: str) -> str:
        return f"{self.schedule_url(backup_uuid)}/executions"

    @property
    def desired_payload(self) -> dict[str, Any]:
        return {
            "frequency": self.frequency,
            "enabled": self.enabled,
            "save_s3": True,
            "s3_storage_uuid": self.s3_storage_uuid,
            "databases_to_backup": self.databases_to_backup,
            "dump_all": self.dump_all,
            "database_backup_retention_amount_locally": self.retention_amount_locally,
            "database_backup_retention_days_s3": self.retention_days_s3,
        }

    def public_summary(self) -> dict[str, Any]:
        return {
            "database_uuid": self.database_uuid,
            "frequency": self.frequency,
            "enabled": self.enabled,
            "save_s3": True,
            "s3_storage_uuid": self.s3_storage_uuid,
            "databases_to_backup": self.databases_to_backup,
            "dump_all": self.dump_all,
            "retention_amount_locally": self.retention_amount_locally,
            "retention_days_s3": self.retention_days_s3,
            "freshness_hours": self.freshness_hours,
        }


def normalize_base_url(value: str) -> str:
    if value != value.strip():
        raise DatabaseBackupError("Coolify API base URL must not contain surrounding whitespace")
    normalized = value.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
        raise DatabaseBackupError("database backup API access must stay on loopback HTTP")
    if parsed.path != "/api/v1" or parsed.params or parsed.query or parsed.fragment:
        raise DatabaseBackupError("Coolify API base URL must end exactly at /api/v1")
    if normalized not in _ALLOWED_BASE_URLS:
        raise DatabaseBackupError("Coolify API base URL must use the managed 8000 endpoint or fixed 18000 SSH tunnel")
    return normalized


def _positive_int(value: int, name: str, *, maximum: int = 3650) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise DatabaseBackupError(f"{name} must be between 1 and {maximum}")
    return value


def build_plan(
    *,
    base_url: str,
    database_uuid: str,
    s3_storage_uuid: str,
    frequency: str,
    databases_to_backup: str,
    dump_all: bool,
    enabled: bool,
    retention_amount_locally: int,
    retention_days_s3: int,
    freshness_hours: int,
) -> BackupPlan:
    for name, value in (("database UUID", database_uuid), ("S3 storage UUID", s3_storage_uuid)):
        if not UUID_RE.fullmatch(value):
            raise DatabaseBackupError(f"{name} must be an 8-128 character Coolify identifier")
    if not frequency or frequency != frequency.strip() or any(ch in frequency for ch in "\r\n"):
        raise DatabaseBackupError("backup frequency must be one non-empty line")
    names = [part.strip() for part in databases_to_backup.split(",") if part.strip()]
    if dump_all:
        if names:
            raise DatabaseBackupError("use either dump_all or databases_to_backup, not both")
        normalized_names = ""
    else:
        if not names:
            raise DatabaseBackupError("databases_to_backup is required when dump_all is false")
        if len(names) != len(set(names)) or any(DATABASE_NAME_RE.fullmatch(name) is None for name in names):
            raise DatabaseBackupError("databases_to_backup must be unique simple database names")
        normalized_names = ",".join(names)
    return BackupPlan(
        base_url=normalize_base_url(base_url),
        database_uuid=database_uuid,
        s3_storage_uuid=s3_storage_uuid,
        frequency=frequency,
        databases_to_backup=normalized_names,
        dump_all=dump_all,
        enabled=bool(enabled),
        retention_amount_locally=_positive_int(retention_amount_locally, "local retention amount", maximum=100),
        retention_days_s3=_positive_int(retention_days_s3, "S3 retention days"),
        freshness_hours=_positive_int(freshness_hours, "freshness hours", maximum=720),
    )


class CoolifyApiClient:
    def __init__(self, token: str, *, timeout: float = 15.0, opener: Callable[..., Any] = urlopen):
        if not token or token != token.strip():
            raise DatabaseBackupError("Coolify API token is empty or contains surrounding whitespace")
        self._token = token
        self._timeout = timeout
        self._opener = opener

    def request(self, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
        body = None
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self._token}"}
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with self._opener(request, timeout=self._timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000].replace(self._token, "[REDACTED]")
            raise DatabaseBackupError(f"Coolify API {method} failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise DatabaseBackupError(f"Coolify API {method} failed: {exc.reason}") from exc
        except OSError as exc:
            raise DatabaseBackupError(f"Coolify API {method} failed: {exc}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DatabaseBackupError(f"Coolify API {method} returned invalid JSON") from exc


def _objects(value: Any, *container_keys: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = None
        for key in container_keys:
            candidate = value.get(key)
            if isinstance(candidate, list):
                items = candidate
                break
        if items is None and "uuid" in value:
            items = [value]
        if items is None:
            raise DatabaseBackupError("Coolify API response does not contain the expected object list")
    else:
        raise DatabaseBackupError("Coolify API returned an unsupported response shape")
    if not all(isinstance(item, dict) for item in items):
        raise DatabaseBackupError("Coolify API object list contains a non-object item")
    return list(items)


def _uuid(item: dict[str, Any], name: str = "object") -> str:
    value = str(item.get("uuid", "")).strip()
    if not UUID_RE.fullmatch(value):
        raise DatabaseBackupError(f"Coolify {name} is missing a valid UUID")
    return value


def _schedule_by_uuid(payload: Any, backup_uuid: str) -> dict[str, Any]:
    matches = [item for item in _objects(payload, "backups", "scheduled_backups", "data") if str(item.get("uuid", "")) == backup_uuid]
    if len(matches) != 1:
        raise DatabaseBackupError("managed backup UUID is not present exactly once in Coolify")
    return matches[0]


def validate_schedule(schedule: dict[str, Any], plan: BackupPlan, backup_uuid: str) -> None:
    if _uuid(schedule, "backup schedule") != backup_uuid:
        raise DatabaseBackupError("Coolify returned a different backup schedule UUID")
    expected = plan.desired_payload
    for key, wanted in expected.items():
        if key not in schedule:
            raise DatabaseBackupError(f"Coolify backup schedule response is missing {key}")
        actual = schedule[key]
        if isinstance(wanted, bool):
            actual = bool(actual)
        elif isinstance(wanted, int):
            try:
                actual = int(actual)
            except (TypeError, ValueError) as exc:
                raise DatabaseBackupError(f"Coolify backup schedule field {key} is not an integer") from exc
        else:
            actual = "" if actual is None else str(actual).strip()
        if actual != wanted:
            raise DatabaseBackupError(f"Coolify backup schedule drifted at {key}: expected {wanted!r}, got {actual!r}")


def _secure_state_dir(state_dir: Path, *, create: bool) -> Path:
    if create:
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        info = state_dir.lstat()
    except FileNotFoundError:
        return state_dir
    except OSError as exc:
        raise DatabaseBackupError(f"cannot inspect database backup state directory: {exc}") from exc
    if state_dir.is_symlink() or not state_dir.is_dir():
        raise DatabaseBackupError("database backup state directory must be a regular directory, not a symlink")
    if info.st_mode & 0o077:
        raise DatabaseBackupError("database backup state directory must not be accessible by group/other; use mode 0700")
    if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
        raise DatabaseBackupError("database backup state directory must be owned by the current controller user")
    return state_dir


def _state_path(state_dir: Path, database_uuid: str) -> Path:
    return state_dir / f"{database_uuid}.json"


def load_state(state_dir: Path, database_uuid: str) -> dict[str, str] | None:
    _secure_state_dir(state_dir, create=False)
    path = _state_path(state_dir, database_uuid)
    if not path.exists():
        return None
    try:
        info = path.lstat()
        if path.is_symlink() or not path.is_file():
            raise DatabaseBackupError("managed database backup state must be a regular file")
        if info.st_mode & 0o077:
            raise DatabaseBackupError("managed database backup state must not be accessible by group/other; use mode 0600")
        if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
            raise DatabaseBackupError("managed database backup state must be owned by the current controller user")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatabaseBackupError(f"cannot read managed database backup state: {exc}") from exc
    if not isinstance(data, dict) or data.get("database_uuid") != database_uuid:
        raise DatabaseBackupError("managed database backup state does not match the requested database")
    backup_uuid = str(data.get("backup_uuid", ""))
    if not UUID_RE.fullmatch(backup_uuid):
        raise DatabaseBackupError("managed database backup state is missing a valid backup UUID")
    return {"database_uuid": database_uuid, "backup_uuid": backup_uuid}


def write_state(state_dir: Path, database_uuid: str, backup_uuid: str) -> Path:
    if not UUID_RE.fullmatch(backup_uuid):
        raise DatabaseBackupError("refusing to persist an invalid backup UUID")
    _secure_state_dir(state_dir, create=True)
    os.chmod(state_dir, 0o700)
    path = _state_path(state_dir, database_uuid)
    payload = {"version": 1, "database_uuid": database_uuid, "backup_uuid": backup_uuid}
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=state_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return path


def require_confirmation() -> None:
    if os.environ.get("COOLIFY_DATABASE_BACKUP_CONFIRM", "") != APPLY_CONFIRMATION:
        raise DatabaseBackupError("mutation requires COOLIFY_DATABASE_BACKUP_CONFIRM=" + APPLY_CONFIRMATION)


def configure_schedule(client: CoolifyApiClient, plan: BackupPlan, state_dir: Path) -> tuple[str, str]:
    schedules_payload = client.request("GET", plan.backups_url)
    schedules = _objects(schedules_payload, "backups", "scheduled_backups", "data")
    state = load_state(state_dir, plan.database_uuid)
    if state is None:
        if schedules:
            raise DatabaseBackupError(
                "Coolify already has backup schedules for this database; refuse duplicate creation. "
                "Adopt the intended schedule explicitly before mutation."
            )
        created = client.request("POST", plan.backups_url, plan.desired_payload)
        if not isinstance(created, dict):
            raise DatabaseBackupError("Coolify create-backup response must be an object")
        backup_uuid = _uuid(created, "create-backup response")
        write_state(state_dir, plan.database_uuid, backup_uuid)
        schedule = _schedule_by_uuid(client.request("GET", plan.backups_url), backup_uuid)
        validate_schedule(schedule, plan, backup_uuid)
        return backup_uuid, "created"

    backup_uuid = state["backup_uuid"]
    _schedule_by_uuid(schedules_payload, backup_uuid)
    client.request("PATCH", plan.schedule_url(backup_uuid), plan.desired_payload)
    schedule = _schedule_by_uuid(client.request("GET", plan.backups_url), backup_uuid)
    validate_schedule(schedule, plan, backup_uuid)
    return backup_uuid, "updated"


def adopt_schedule(client: CoolifyApiClient, plan: BackupPlan, state_dir: Path, backup_uuid: str) -> None:
    if load_state(state_dir, plan.database_uuid) is not None:
        raise DatabaseBackupError("managed database backup state already exists; adoption is only for an unmanaged existing schedule")
    schedule = _schedule_by_uuid(client.request("GET", plan.backups_url), backup_uuid)
    validate_schedule(schedule, plan, backup_uuid)
    write_state(state_dir, plan.database_uuid, backup_uuid)


def _parse_created_at(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise DatabaseBackupError("backup execution is missing created_at")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DatabaseBackupError("backup execution created_at is not ISO-8601") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def validate_execution(execution: dict[str, Any], plan: BackupPlan, *, now: datetime | None = None) -> dict[str, Any]:
    execution_uuid = _uuid(execution, "backup execution")
    status = str(execution.get("status", "")).strip().lower()
    message = str(execution.get("message", "")).strip()
    if status not in SUCCESS_STATUSES:
        raise DatabaseBackupError(f"latest database backup execution is not successful: {status or 'missing'}")
    lowered = message.lower()
    if "s3" in lowered and ("warning" in lowered or "fail" in lowered or "error" in lowered):
        raise DatabaseBackupError("latest database backup reports an S3 upload warning/failure")
    try:
        size = int(execution.get("size", 0))
    except (TypeError, ValueError) as exc:
        raise DatabaseBackupError("backup execution size is invalid") from exc
    if size <= 0:
        raise DatabaseBackupError("latest database backup execution has no positive archive size")
    created = _parse_created_at(execution.get("created_at"))
    current = now or datetime.now(timezone.utc)
    age_hours = (current - created).total_seconds() / 3600
    if age_hours < -0.1 or age_hours > plan.freshness_hours:
        raise DatabaseBackupError(f"latest database backup is stale ({age_hours:.1f}h > {plan.freshness_hours}h)")
    filename = str(execution.get("filename", "")).strip()
    if not filename or any(ch in filename for ch in "\r\n"):
        raise DatabaseBackupError("backup execution is missing a safe filename")
    return {
        "execution_uuid": execution_uuid,
        "status": status,
        "filename": filename,
        "size": size,
        "created_at": created.isoformat(),
        "age_hours": round(age_hours, 2),
    }


def verify_schedule(client: CoolifyApiClient, plan: BackupPlan, state_dir: Path, *, now: datetime | None = None) -> dict[str, Any]:
    state = load_state(state_dir, plan.database_uuid)
    if state is None:
        raise DatabaseBackupError("no managed database backup schedule state exists")
    backup_uuid = state["backup_uuid"]
    schedule = _schedule_by_uuid(client.request("GET", plan.backups_url), backup_uuid)
    validate_schedule(schedule, plan, backup_uuid)
    executions = _objects(client.request("GET", plan.executions_url(backup_uuid)), "executions", "data")
    if not executions:
        raise DatabaseBackupError("managed database backup has no execution evidence")
    ordered = sorted(executions, key=lambda item: _parse_created_at(item.get("created_at")), reverse=True)
    latest = validate_execution(ordered[0], plan, now=now)
    return {
        "database_uuid": plan.database_uuid,
        "backup_uuid": backup_uuid,
        "schedule": "MATCHED",
        "latest_execution": latest,
        "s3_schedule_enabled": True,
        "s3_object_independently_verified": False,
    }


def trigger_backup(
    client: CoolifyApiClient,
    plan: BackupPlan,
    state_dir: Path,
    *,
    poll_interval: float = 5.0,
    timeout: float = 900.0,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    state = load_state(state_dir, plan.database_uuid)
    if state is None:
        raise DatabaseBackupError("configure or adopt a managed database backup schedule before triggering it")
    backup_uuid = state["backup_uuid"]
    schedule = _schedule_by_uuid(client.request("GET", plan.backups_url), backup_uuid)
    validate_schedule(schedule, plan, backup_uuid)
    before = _objects(client.request("GET", plan.executions_url(backup_uuid)), "executions", "data")
    before_ids = {str(item.get("uuid", "")) for item in before}
    client.request("PATCH", plan.schedule_url(backup_uuid), {"backup_now": True})
    deadline = monotonic() + timeout
    while True:
        executions = _objects(client.request("GET", plan.executions_url(backup_uuid)), "executions", "data")
        candidates = [item for item in executions if str(item.get("uuid", "")) not in before_ids]
        if candidates:
            newest = sorted(candidates, key=lambda item: _parse_created_at(item.get("created_at")), reverse=True)[0]
            status = str(newest.get("status", "")).strip().lower()
            if status in FAILURE_STATUSES:
                raise DatabaseBackupError(f"triggered database backup failed with status {status}")
            if status in SUCCESS_STATUSES:
                return validate_execution(newest, plan)
        if monotonic() >= deadline:
            raise DatabaseBackupError("timed out waiting for the triggered database backup execution")
        sleeper(poll_interval)


def _token() -> str:
    token = os.environ.get("COOLIFY_API_TOKEN", "")
    if not token:
        raise DatabaseBackupError("COOLIFY_API_TOKEN is required; load it interactively and do not put it in command arguments")
    return token


def _bool_text(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes"}:
        return True
    if lowered in {"0", "false", "no"}:
        return False
    raise argparse.ArgumentTypeError("expected true/false")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=("plan", "adopt", "configure", "trigger", "verify"))
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--database-uuid", required=True)
    p.add_argument("--s3-storage-uuid", required=True)
    p.add_argument("--frequency", default="daily")
    p.add_argument("--databases-to-backup", default="")
    p.add_argument("--dump-all", type=_bool_text, default=False)
    p.add_argument("--enabled", type=_bool_text, default=True)
    p.add_argument("--retention-amount-locally", type=int, default=2)
    p.add_argument("--retention-days-s3", type=int, default=30)
    p.add_argument("--freshness-hours", type=int, default=36)
    p.add_argument("--state-dir", type=Path, required=True)
    p.add_argument("--backup-uuid", default="", help="existing Coolify schedule UUID for explicit adopt")
    p.add_argument("--poll-interval", type=float, default=5.0)
    p.add_argument("--timeout", type=float, default=900.0)
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        plan = build_plan(
            base_url=args.base_url,
            database_uuid=args.database_uuid,
            s3_storage_uuid=args.s3_storage_uuid,
            frequency=args.frequency,
            databases_to_backup=args.databases_to_backup,
            dump_all=args.dump_all,
            enabled=args.enabled,
            retention_amount_locally=args.retention_amount_locally,
            retention_days_s3=args.retention_days_s3,
            freshness_hours=args.freshness_hours,
        )
        if args.operation == "plan":
            print(json.dumps({"operation": "plan", "desired": plan.public_summary()}, indent=2, sort_keys=True))
            print("token_required: false")
            print("mutation: false")
            return 0
        client = CoolifyApiClient(_token())
        if args.operation == "adopt":
            if not args.backup_uuid or not UUID_RE.fullmatch(args.backup_uuid):
                raise DatabaseBackupError("adopt requires --backup-uuid with an existing schedule UUID")
            adopt_schedule(client, plan, args.state_dir, args.backup_uuid)
            print("PASS Coolify PostgreSQL backup schedule adopted")
            print(f"  database_uuid: {plan.database_uuid}")
            print(f"  backup_uuid: {args.backup_uuid}")
            print("  mutation: false")
            return 0
        if args.operation == "configure":
            require_confirmation()
            backup_uuid, outcome = configure_schedule(client, plan, args.state_dir)
            print("PASS Coolify PostgreSQL backup schedule configured")
            print(f"  outcome: {outcome}")
            print(f"  database_uuid: {plan.database_uuid}")
            print(f"  backup_uuid: {backup_uuid}")
            print("  save_s3: true")
            return 0
        if args.operation == "trigger":
            require_confirmation()
            evidence = trigger_backup(
                client,
                plan,
                args.state_dir,
                poll_interval=args.poll_interval,
                timeout=args.timeout,
            )
            print("PASS Coolify PostgreSQL backup execution")
            for key in ("execution_uuid", "status", "filename", "size", "created_at", "age_hours"):
                print(f"  {key}: {evidence[key]}")
            print("  s3_object_independently_verified: false")
            return 0
        evidence = verify_schedule(client, plan, args.state_dir)
        print("PASS Coolify PostgreSQL backup schedule and freshness")
        print(f"  database_uuid: {evidence['database_uuid']}")
        print(f"  backup_uuid: {evidence['backup_uuid']}")
        print(f"  latest_status: {evidence['latest_execution']['status']}")
        print(f"  latest_age_hours: {evidence['latest_execution']['age_hours']}")
        print("  s3_schedule_enabled: true")
        print("  s3_object_independently_verified: false")
        return 0
    except (DatabaseBackupError, OSError) as exc:
        print(f"ERROR Coolify database backup: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
