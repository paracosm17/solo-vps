#!/usr/bin/env python3
"""Root-only operational M14 restic runtime for Solo VPS.

The runtime keeps S3/restic secrets in the existing root-only credential file,
constructs a minimal child environment, and exposes only bounded repository,
backup, retention, freshness, temporary restore-test, and explicit DR staging operations.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable, Sequence

try:
    from scripts.backup_credentials_common import BackupCredentialError, parse_json_bytes
except ModuleNotFoundError:  # installed next to backup_credentials_common.py
    from backup_credentials_common import BackupCredentialError, parse_json_bytes

RESTIC = Path("/usr/local/bin/restic")
RUNTIME_SECRET_ROOT = Path("/run")
DEFAULT_RUNTIME_CONFIG = Path("/etc/solo-vps/backup/runtime.json")
DEFAULT_CREDENTIALS = Path("/etc/solo-vps/backup/credentials.json")
RETENTION_CONFIRMATION = "I_HAVE_REVIEWED_THE_BACKUP_RETENTION_PLAN"
RECOVERY_STAGING_CONFIRMATION = "I_HAVE_VERIFIED_A_PRIVATE_DISASTER_RECOVERY_STAGING_DIRECTORY"
RECOVERY_STAGING_PARENT = Path("/var/tmp/solo-vps-disaster-recovery")
EXPECTED_SOURCES = ["/data/coolify"]
EXPECTED_EXCLUDES = ["/data/coolify/ssh/mux", "/data/coolify/databases", "/data/coolify/backups"]
EXPECTED_RETENTION = {
    "keep_last": 3,
    "keep_daily": 14,
    "keep_weekly": 8,
    "keep_monthly": 12,
    "keep_yearly": 3,
}


class ResticRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeConfig:
    repository: str
    region: str
    host: str
    sources: tuple[str, ...]
    excludes: tuple[str, ...]
    tag: str
    group_by: str
    retention: dict[str, int]
    freshness_hours: int
    cache_dir: str


@dataclass(frozen=True)
class SnapshotEvidence:
    snapshot_id: str
    timestamp: datetime
    age_hours: float


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _require_root() -> None:
    if os.geteuid() != 0:
        raise ResticRuntimeError("run this helper as root (Solo VPS uses become/sudo -n)")


def _read_regular_private_file(path: Path, *, expected_mode: int = 0o600) -> bytes:
    try:
        meta = path.lstat()
    except FileNotFoundError as exc:
        raise ResticRuntimeError(f"required runtime file is missing: {path}") from exc
    if stat.S_ISLNK(meta.st_mode) or not stat.S_ISREG(meta.st_mode):
        raise ResticRuntimeError(f"refusing non-regular runtime file: {path}")
    if meta.st_uid != 0 or meta.st_gid != 0:
        raise ResticRuntimeError(f"runtime file must be owned by root:root: {path}")
    if stat.S_IMODE(meta.st_mode) != expected_mode:
        raise ResticRuntimeError(f"runtime file mode must be {expected_mode:04o}: {path}")
    return path.read_bytes()


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ResticRuntimeError(f"{name} must be a non-empty trimmed string")
    if any(char in value for char in ("\x00", "\r", "\n")):
        raise ResticRuntimeError(f"{name} must be a single-line value")
    return value


def load_runtime_config(path: Path = DEFAULT_RUNTIME_CONFIG) -> RuntimeConfig:
    raw = _read_regular_private_file(path)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResticRuntimeError("backup runtime config is not valid UTF-8 JSON") from exc
    if not isinstance(data, dict) or set(data) != {
        "version",
        "repository",
        "region",
        "host",
        "sources",
        "excludes",
        "tag",
        "group_by",
        "retention",
        "freshness_hours",
        "cache_dir",
    }:
        raise ResticRuntimeError("backup runtime config has unexpected keys")
    if data["version"] != 1:
        raise ResticRuntimeError("backup runtime config version must be 1")
    repository = _text(data["repository"], "repository")
    if not repository.startswith("s3:https://"):
        raise ResticRuntimeError("repository must use an HTTPS S3-compatible restic locator")
    sources = data["sources"]
    excludes = data["excludes"]
    retention = data["retention"]
    if sources != EXPECTED_SOURCES or excludes != EXPECTED_EXCLUDES:
        raise ResticRuntimeError("backup runtime scope drifted from the reviewed /data/coolify boundary")
    if retention != EXPECTED_RETENTION:
        raise ResticRuntimeError("backup runtime retention policy drifted from the reviewed baseline")
    if data["tag"] != "solo-vps" or data["group_by"] != "host,tags":
        raise ResticRuntimeError("backup runtime tag/grouping policy drifted")
    freshness = data["freshness_hours"]
    if not isinstance(freshness, int) or not 25 <= freshness <= 72:
        raise ResticRuntimeError("freshness_hours must be an integer between 25 and 72")
    cache_dir = _text(data["cache_dir"], "cache_dir")
    if cache_dir != "/var/cache/solo-vps/restic":
        raise ResticRuntimeError("restic cache directory drifted from the managed location")
    return RuntimeConfig(
        repository=repository,
        region=_text(data["region"], "region"),
        host=_text(data["host"], "host"),
        sources=tuple(sources),
        excludes=tuple(excludes),
        tag=data["tag"],
        group_by=data["group_by"],
        retention=dict(retention),
        freshness_hours=freshness,
        cache_dir=cache_dir,
    )


def load_credentials(path: Path = DEFAULT_CREDENTIALS) -> dict[str, str]:
    raw = _read_regular_private_file(path)
    try:
        return parse_json_bytes(raw)
    except BackupCredentialError as exc:
        raise ResticRuntimeError(f"backup credential schema is invalid: {exc}") from exc


def _write_private_text(path: Path, value: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


@contextmanager
def _child_environment(config: RuntimeConfig, credentials: dict[str, str]):
    temporary = Path(tempfile.mkdtemp(prefix="solo-vps-backup.", dir=RUNTIME_SECRET_ROOT))
    os.chmod(temporary, 0o700)
    password_file = temporary / "restic-password"
    aws_credentials = temporary / "aws-credentials"
    try:
        _write_private_text(password_file, credentials["RESTIC_PASSWORD"] + "\n")
        lines = [
            "[solo-vps]",
            f"aws_access_key_id = {credentials['AWS_ACCESS_KEY_ID']}",
            f"aws_secret_access_key = {credentials['AWS_SECRET_ACCESS_KEY']}",
        ]
        if credentials.get("AWS_SESSION_TOKEN"):
            lines.append(f"aws_session_token = {credentials['AWS_SESSION_TOKEN']}")
        _write_private_text(aws_credentials, "\n".join(lines) + "\n")
        env = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME": "/root",
            "LANG": "C.UTF-8",
            "RESTIC_REPOSITORY": config.repository,
            "RESTIC_PASSWORD_FILE": str(password_file),
            "RESTIC_CACHE_DIR": config.cache_dir,
            "AWS_SHARED_CREDENTIALS_FILE": str(aws_credentials),
            "AWS_PROFILE": "solo-vps",
            "AWS_DEFAULT_REGION": config.region,
        }
        yield env
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _bounded_error(text: str, *, max_lines: int = 8) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "no diagnostic output"
    return " | ".join(lines[-max_lines:])[:2000]


def _require_private_cache(config: RuntimeConfig) -> None:
    path = Path(config.cache_dir)
    try:
        meta = path.lstat()
    except FileNotFoundError as exc:
        raise ResticRuntimeError(f"managed restic cache directory is missing: {path}") from exc
    if stat.S_ISLNK(meta.st_mode) or not stat.S_ISDIR(meta.st_mode):
        raise ResticRuntimeError(f"refusing non-directory restic cache path: {path}")
    if meta.st_uid != 0 or meta.st_gid != 0 or stat.S_IMODE(meta.st_mode) != 0o700:
        raise ResticRuntimeError("managed restic cache directory must be root:root mode 0700")


def run_restic(
    args: Sequence[str],
    config: RuntimeConfig,
    credentials: dict[str, str],
    *,
    runner: Runner = subprocess.run,
    timeout: int = 3600,
    passthrough: bool = False,
) -> subprocess.CompletedProcess[str]:
    if not RESTIC.exists():
        raise ResticRuntimeError(f"managed restic binary is missing: {RESTIC}")
    _require_private_cache(config)
    command = [str(RESTIC), *args]
    try:
        with _child_environment(config, credentials) as child_env:
            result = runner(
                command,
                env=child_env,
                text=True,
                stdout=None if passthrough else subprocess.PIPE,
                stderr=None if passthrough else subprocess.PIPE,
                check=False,
                timeout=timeout,
            )
    except subprocess.TimeoutExpired as exc:
        raise ResticRuntimeError(f"restic command timed out after {timeout}s") from exc
    if result.returncode != 0:
        diagnostic = "passthrough command failed" if passthrough else _bounded_error((result.stderr or "") + "\n" + (result.stdout or ""))
        raise ResticRuntimeError(f"restic operation failed (exit {result.returncode}): {diagnostic}")
    return result


def _snapshot_rows(config: RuntimeConfig, credentials: dict[str, str], *, runner: Runner = subprocess.run) -> list[dict[str, Any]]:
    result = run_restic(
        ["snapshots", "--json", "--host", config.host, "--tag", config.tag],
        config,
        credentials,
        runner=runner,
        timeout=300,
    )
    try:
        rows = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise ResticRuntimeError("restic snapshots did not return valid JSON") from exc
    if not isinstance(rows, list):
        raise ResticRuntimeError("restic snapshots JSON must be a list")
    return [row for row in rows if isinstance(row, dict)]


def latest_snapshot(config: RuntimeConfig, credentials: dict[str, str], *, runner: Runner = subprocess.run, now: datetime | None = None) -> SnapshotEvidence:
    expected_paths = set(config.sources)
    candidates: list[tuple[datetime, str]] = []
    for row in _snapshot_rows(config, credentials, runner=runner):
        if row.get("hostname") != config.host:
            continue
        tags = row.get("tags") or []
        if config.tag not in tags:
            continue
        if set(row.get("paths") or []) != expected_paths:
            continue
        raw_time = row.get("time")
        snapshot_id = row.get("id")
        if not isinstance(raw_time, str) or not isinstance(snapshot_id, str):
            continue
        try:
            timestamp = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError:
            continue
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        candidates.append((timestamp.astimezone(timezone.utc), snapshot_id))
    if not candidates:
        raise ResticRuntimeError("no matching Solo VPS snapshot exists for this host/source/tag contract")
    timestamp, snapshot_id = max(candidates, key=lambda item: item[0])
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age_hours = (current - timestamp).total_seconds() / 3600.0
    if age_hours < -1.0:
        raise ResticRuntimeError("latest backup snapshot timestamp is unexpectedly in the future")
    return SnapshotEvidence(snapshot_id=snapshot_id, timestamp=timestamp, age_hours=max(age_hours, 0.0))


def require_fresh_snapshot(config: RuntimeConfig, credentials: dict[str, str], *, runner: Runner = subprocess.run, now: datetime | None = None) -> SnapshotEvidence:
    evidence = latest_snapshot(config, credentials, runner=runner, now=now)
    if evidence.age_hours > config.freshness_hours:
        raise ResticRuntimeError(
            f"latest Solo VPS snapshot is stale: age={evidence.age_hours:.1f}h threshold={config.freshness_hours}h"
        )
    return evidence


def _backup_args(config: RuntimeConfig) -> list[str]:
    args = ["backup", *config.sources, "--host", config.host, "--tag", config.tag, "--group-by", config.group_by]
    for path in config.excludes:
        args.extend(["--exclude", path])
    return args


def _retention_args(config: RuntimeConfig, *, dry_run: bool) -> list[str]:
    args = ["forget", "--host", config.host, "--tag", config.tag, "--group-by", config.group_by]
    if dry_run:
        args.append("--dry-run")
    else:
        args.append("--prune")
    for key in ("keep_last", "keep_daily", "keep_weekly", "keep_monthly", "keep_yearly"):
        args.extend(["--" + key.replace("_", "-"), str(config.retention[key])])
    return args


def _require_sources(config: RuntimeConfig) -> None:
    for source in config.sources:
        path = Path(source)
        if not path.is_dir():
            raise ResticRuntimeError(f"reviewed backup source is missing or not a directory: {source}")


def repository_init(config: RuntimeConfig, credentials: dict[str, str], *, runner: Runner = subprocess.run) -> None:
    # If the repository already opens, fail instead of silently treating init as adopt.
    try:
        rows = _snapshot_rows(config, credentials, runner=runner)
    except ResticRuntimeError:
        rows = None
    if rows is not None:
        raise ResticRuntimeError("repository already exists and is accessible; use repository-adopt instead of init")
    run_restic(["init"], config, credentials, runner=runner, timeout=600)
    _snapshot_rows(config, credentials, runner=runner)


def repository_adopt(config: RuntimeConfig, credentials: dict[str, str], *, runner: Runner = subprocess.run) -> None:
    _snapshot_rows(config, credentials, runner=runner)
    run_restic(["check"], config, credentials, runner=runner, timeout=3600)


def backup_now(config: RuntimeConfig, credentials: dict[str, str], *, runner: Runner = subprocess.run) -> SnapshotEvidence:
    _require_sources(config)
    _snapshot_rows(config, credentials, runner=runner)
    run_restic(_backup_args(config), config, credentials, runner=runner, timeout=7200)
    return require_fresh_snapshot(config, credentials, runner=runner)


def check_repository(config: RuntimeConfig, credentials: dict[str, str], *, runner: Runner = subprocess.run) -> SnapshotEvidence:
    run_restic(["check"], config, credentials, runner=runner, timeout=3600)
    return require_fresh_snapshot(config, credentials, runner=runner)


def restore_test(config: RuntimeConfig, credentials: dict[str, str], *, runner: Runner = subprocess.run) -> SnapshotEvidence:
    evidence = require_fresh_snapshot(config, credentials, runner=runner)
    root = Path("/var/tmp")
    temporary = Path(tempfile.mkdtemp(prefix="solo-vps-restic-restore-test.", dir=root))
    os.chmod(temporary, 0o700)
    try:
        run_restic(
            ["restore", "latest", "--target", str(temporary), "--host", config.host, "--tag", config.tag],
            config,
            credentials,
            runner=runner,
            timeout=7200,
        )
        for source in config.sources:
            restored = temporary / source.lstrip("/")
            if not restored.is_dir():
                raise ResticRuntimeError(f"restore test did not materialize expected source tree: {source}")
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return evidence


def _require_recovery_staging_target(target: Path) -> Path:
    target = target.expanduser().resolve()
    parent = RECOVERY_STAGING_PARENT.resolve()
    if target.parent != parent:
        raise ResticRuntimeError(
            f"recovery staging target must be one direct child of {RECOVERY_STAGING_PARENT}"
        )
    if not target.name or target.name in {".", ".."}:
        raise ResticRuntimeError("recovery staging target has no safe leaf name")
    try:
        meta = target.lstat()
    except FileNotFoundError as exc:
        raise ResticRuntimeError(
            "recovery staging target must already exist as an empty root-owned 0700 directory"
        ) from exc
    if stat.S_ISLNK(meta.st_mode) or not stat.S_ISDIR(meta.st_mode):
        raise ResticRuntimeError("recovery staging target must be a real directory, not a symlink")
    if meta.st_uid != 0 or meta.st_gid != 0 or stat.S_IMODE(meta.st_mode) != 0o700:
        raise ResticRuntimeError("recovery staging target must be owned by root:root with mode 0700")
    if any(target.iterdir()):
        raise ResticRuntimeError("recovery staging target must be empty before restore")
    return target


def restore_staging(
    config: RuntimeConfig,
    credentials: dict[str, str],
    *,
    target: Path,
    confirmation: str,
    runner: Runner = subprocess.run,
) -> SnapshotEvidence:
    if confirmation != RECOVERY_STAGING_CONFIRMATION:
        raise ResticRuntimeError(
            "disaster-recovery staging requires the exact private-staging confirmation"
        )
    target = _require_recovery_staging_target(target)
    evidence = require_fresh_snapshot(config, credentials, runner=runner)
    run_restic(
        ["restore", "latest", "--target", str(target), "--host", config.host, "--tag", config.tag],
        config,
        credentials,
        runner=runner,
        timeout=7200,
    )
    restored_root = target / "data/coolify"
    required = (
        restored_root / "source/.env",
        restored_root / "ssh/keys",
    )
    if not required[0].is_file() or not required[1].is_dir():
        raise ResticRuntimeError(
            "staged recovery snapshot is missing required Coolify filesystem recovery material"
        )
    for excluded in config.excludes:
        excluded_path = target / excluded.lstrip("/")
        if excluded_path.exists():
            raise ResticRuntimeError(
                f"staged recovery unexpectedly contains an excluded path: {excluded}"
            )
    return evidence


def _print_snapshot(prefix: str, evidence: SnapshotEvidence, config: RuntimeConfig) -> None:
    print(f"  {prefix}_snapshot: {evidence.snapshot_id[:12]}")
    print(f"  {prefix}_time_utc: {evidence.timestamp.astimezone(timezone.utc).isoformat()}")
    print(f"  {prefix}_age_hours: {evidence.age_hours:.2f}")
    print(f"  freshness_threshold_hours: {config.freshness_hours}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "repository-init",
            "repository-adopt",
            "repository-status",
            "status",
            "backup",
            "check",
            "retention-plan",
            "retention-apply",
            "restore-test",
            "restore-staging",
        ),
    )
    parser.add_argument("--runtime-config", type=Path, default=DEFAULT_RUNTIME_CONFIG, help=argparse.SUPPRESS)
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS, help=argparse.SUPPRESS)
    parser.add_argument("--confirm", default="", help=argparse.SUPPRESS)
    parser.add_argument("--target", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()

    try:
        _require_root()
        config = load_runtime_config(args.runtime_config)
        credentials = load_credentials(args.credentials)
        if args.command == "repository-init":
            repository_init(config, credentials)
            print("PASS restic repository initialized")
            print("  repository_accessible: true")
        elif args.command == "repository-adopt":
            repository_adopt(config, credentials)
            print("PASS existing restic repository adopted")
            print("  repository_check: pass")
        elif args.command == "repository-status":
            rows = _snapshot_rows(config, credentials)
            print("PASS restic repository accessible")
            print(f"  matching_host_tag_snapshots_seen: {len(rows)}")
        elif args.command == "status":
            evidence = require_fresh_snapshot(config, credentials)
            print("PASS Solo VPS backup freshness")
            _print_snapshot("latest", evidence, config)
        elif args.command == "backup":
            evidence = backup_now(config, credentials)
            print("PASS Solo VPS filesystem recovery-material backup")
            _print_snapshot("latest", evidence, config)
        elif args.command == "check":
            evidence = check_repository(config, credentials)
            print("PASS Solo VPS backup repository check and freshness")
            _print_snapshot("latest", evidence, config)
        elif args.command == "retention-plan":
            print("Solo VPS restic retention dry-run (no snapshots will be deleted):")
            run_restic(_retention_args(config, dry_run=True), config, credentials, passthrough=True, timeout=3600)
            print("PASS Solo VPS retention plan")
            print("  destructive_changes: false")
        elif args.command == "retention-apply":
            if args.confirm != RETENTION_CONFIRMATION:
                raise ResticRuntimeError(
                    "retention apply requires the exact reviewed-plan confirmation; run retention-plan first"
                )
            run_restic(_retention_args(config, dry_run=False), config, credentials, passthrough=True, timeout=7200)
            evidence = check_repository(config, credentials)
            print("PASS Solo VPS retention apply + repository check")
            _print_snapshot("latest", evidence, config)
        elif args.command == "restore-test":
            evidence = restore_test(config, credentials)
            print("PASS Solo VPS filesystem recovery-material restore test")
            _print_snapshot("restored", evidence, config)
            print("  production_paths_modified: false")
            print("  temporary_restore_removed: true")
        else:
            if args.target is None:
                raise ResticRuntimeError("restore-staging requires --target")
            evidence = restore_staging(
                config,
                credentials,
                target=args.target,
                confirmation=args.confirm,
            )
            print("PASS Solo VPS disaster-recovery filesystem staging")
            _print_snapshot("staged", evidence, config)
            print(f"  staging_root: {args.target}")
            print("  direct_overlay_onto_fresh_coolify: false")
            print("  staged_material_retained: true")
    except (OSError, ResticRuntimeError) as exc:
        print(f"ERROR backup runtime: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
