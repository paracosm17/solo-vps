#!/usr/bin/env python3
"""Inspect and exercise a Coolify PostgreSQL custom-format archive safely.

This is a restore verifier, not a backup scheduler. The target database must be
explicitly disposable and empty. Authentication is supplied through a private
PGPASS file path, never a password CLI argument.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
from typing import Callable, Sequence

RESTORE_CONFIRMATION = "I_HAVE_VERIFIED_A_DISPOSABLE_POSTGRES_RESTORE_TARGET"
DB_NAME_RE = re.compile(r"^solo_vps_restore_[A-Za-z0-9_]{1,48}$")
USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,62}$")
HOST_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,255}$")
EMPTY_CHECK = (
    "WITH user_relations AS ("
    "SELECT c.oid FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
    "WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast' "
    "AND c.relkind IN ('r','p','v','m','S','f')"
    "), user_functions AS ("
    "SELECT p.oid FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace "
    "WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast' "
    "AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.classid='pg_proc'::regclass "
    "AND d.objid=p.oid AND d.deptype='e')"
    "), user_types AS ("
    "SELECT t.oid FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace "
    "WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast' "
    "AND t.typtype IN ('d','e','r','m') "
    "AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.classid='pg_type'::regclass "
    "AND d.objid=t.oid AND d.deptype='e')"
    ") SELECT (SELECT count(*) FROM user_relations) + (SELECT count(*) FROM user_functions) + "
    "(SELECT count(*) FROM user_types)"
)
FORBIDDEN_VERIFY = re.compile(r"\b(?:insert|update|delete|merge|alter|drop|create|truncate|grant|revoke|copy|call|do)\b", re.I)


class RestoreExerciseError(RuntimeError):
    pass


def require_file(path: Path, name: str) -> Path:
    try:
        info = path.lstat()
    except OSError as exc:
        raise RestoreExerciseError(f"cannot inspect {name}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RestoreExerciseError(f"{name} must be a regular non-symlink file")
    return path


def _parse_pgpass_line(raw: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in raw:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        raise RestoreExerciseError("PGPASS file contains a malformed trailing escape")
    fields.append("".join(current))
    if len(fields) != 5:
        raise RestoreExerciseError("PGPASS entries must contain exactly five colon-separated fields")
    return fields


def _escape_pgpass_field(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


def validate_pgpass(path: Path) -> list[str]:
    require_file(path, "PGPASS file")
    info = path.stat()
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o077:
        raise RestoreExerciseError("PGPASS file must not be accessible by group/other; use mode 0600")
    if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
        raise RestoreExerciseError("PGPASS file must be owned by the current restore user")
    values: list[str] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw or raw.startswith("#"):
                continue
            fields = _parse_pgpass_line(raw)
            password = fields[4]
            if not password:
                raise RestoreExerciseError("PGPASS credential entry has an empty password")
            values.extend((password, _escape_pgpass_field(password)))
    except OSError as exc:
        raise RestoreExerciseError(f"cannot read PGPASS file: {exc}") from exc
    values = list(dict.fromkeys(value for value in values if value))
    if not values:
        raise RestoreExerciseError("PGPASS file does not contain a credential entry")
    return values


def validate_verify_query(query: str) -> str:
    normalized = " ".join(query.strip().split())
    if not normalized.lower().startswith("select "):
        raise RestoreExerciseError("application verification query must be a read-only SELECT")
    if ";" in normalized.rstrip(";") or FORBIDDEN_VERIFY.search(normalized):
        raise RestoreExerciseError("application verification query contains unsafe SQL")
    return normalized.rstrip(";")


def redact(text: str, secrets: Sequence[str]) -> str:
    value = text
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value


def run_command(
    command: list[str],
    *,
    pgpass: Path | None = None,
    read_only: bool = False,
    secrets: Sequence[str] = (),
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    if pgpass is not None:
        env["PGPASSFILE"] = str(pgpass)
    if read_only:
        env["PGOPTIONS"] = "-c default_transaction_read_only=on"
    try:
        result = runner(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RestoreExerciseError(f"command timed out: {shlex.join(command[:2])}") from exc
    if result.returncode != 0:
        diagnostic = redact((result.stderr or result.stdout or "no diagnostic").strip()[:1500], secrets)
        raise RestoreExerciseError(f"command failed (exit {result.returncode}): {diagnostic}")
    return result


def inspect_archive(
    archive: Path,
    *,
    pg_restore: str = "pg_restore",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, int]:
    require_file(archive, "database archive")
    binary = shutil.which(pg_restore) if "/" not in pg_restore else pg_restore
    if not binary:
        raise RestoreExerciseError("pg_restore is unavailable; install a compatible PostgreSQL client on the restore workstation")
    result = run_command([binary, "--list", str(archive)], runner=runner)
    lines = [line for line in result.stdout.splitlines() if line.strip() and not line.startswith(";")]
    if not lines:
        raise RestoreExerciseError("pg_restore --list returned no archive objects")
    return {"archive_objects": len(lines)}


def _psql_command(binary: str, host: str, port: int, user: str, database: str, query: str) -> list[str]:
    return [
        binary,
        "--host", host,
        "--port", str(port),
        "--username", user,
        "--dbname", database,
        "--no-psqlrc",
        "--set", "ON_ERROR_STOP=1",
        "--tuples-only",
        "--no-align",
        "--command", query,
    ]


def exercise_restore(
    *,
    archive: Path,
    host: str,
    port: int,
    user: str,
    database: str,
    pgpass: Path,
    verify_query: str,
    expected: str,
    pg_restore: str = "pg_restore",
    psql: str = "psql",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, str | int]:
    if os.environ.get("SOLO_VPS_DATABASE_RESTORE_CONFIRM", "") != RESTORE_CONFIRMATION:
        raise RestoreExerciseError("restore requires SOLO_VPS_DATABASE_RESTORE_CONFIRM=" + RESTORE_CONFIRMATION)
    if not DB_NAME_RE.fullmatch(database):
        raise RestoreExerciseError("restore target database must use the solo_vps_restore_ prefix")
    if not HOST_RE.fullmatch(host) or not 1 <= port <= 65535 or not USER_RE.fullmatch(user):
        raise RestoreExerciseError("restore target host/port/user is invalid")
    query = validate_verify_query(verify_query)
    secrets = validate_pgpass(pgpass)
    archive_info = inspect_archive(archive, pg_restore=pg_restore, runner=runner)
    restore_binary = shutil.which(pg_restore) if "/" not in pg_restore else pg_restore
    psql_binary = shutil.which(psql) if "/" not in psql else psql
    if not restore_binary or not psql_binary:
        raise RestoreExerciseError("pg_restore and psql are required for the restore exercise")

    empty = run_command(
        _psql_command(psql_binary, host, port, user, database, EMPTY_CHECK),
        pgpass=pgpass,
        read_only=True,
        secrets=secrets,
        runner=runner,
    ).stdout.strip()
    if empty != "0":
        raise RestoreExerciseError("disposable restore database is not empty; refusing destructive restore")

    restore_command = [
        restore_binary,
        "--exit-on-error",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-acl",
        "--host", host,
        "--port", str(port),
        "--username", user,
        "--dbname", database,
        str(archive),
    ]
    run_command(restore_command, pgpass=pgpass, secrets=secrets, runner=runner, timeout=3600)
    actual = run_command(
        _psql_command(psql_binary, host, port, user, database, query),
        pgpass=pgpass,
        read_only=True,
        secrets=secrets,
        runner=runner,
    ).stdout.strip()
    if actual != expected:
        raise RestoreExerciseError(f"application verification mismatch: expected {expected!r}, got {actual!r}")
    return {
        "archive_objects": archive_info["archive_objects"],
        "target_database": database,
        "empty_before_restore": "true",
        "application_verification": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inspect", "restore"))
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--database", default="")
    parser.add_argument("--pgpass-file", type=Path)
    parser.add_argument("--verify-query", default="")
    parser.add_argument("--expect", default="")
    args = parser.parse_args()
    try:
        if args.operation == "inspect":
            evidence = inspect_archive(args.archive)
            print("PASS PostgreSQL backup archive inspection")
            print(f"  archive_objects: {evidence['archive_objects']}")
            print("  restore_exercised: false")
            return 0
        if args.pgpass_file is None or not args.database or not args.verify_query:
            raise RestoreExerciseError("restore requires --database, --pgpass-file, --verify-query and --expect")
        evidence = exercise_restore(
            archive=args.archive,
            host=args.host,
            port=args.port,
            user=args.user,
            database=args.database,
            pgpass=args.pgpass_file,
            verify_query=args.verify_query,
            expected=args.expect,
        )
        print("PASS PostgreSQL disposable restore exercise")
        for key, value in evidence.items():
            print(f"  {key}: {value}")
        print("  password_printed: false")
        return 0
    except (OSError, RestoreExerciseError) as exc:
        print(f"ERROR PostgreSQL restore exercise: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
