#!/usr/bin/env python3
"""Validate the M15 Coolify-owned PostgreSQL backup/restore runtime source contract."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


class ContractError(RuntimeError):
    pass


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        raise ContractError(f"{where} missing required M15 runtime contract: {needle}")


def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        raise ContractError(f"{where} contains forbidden M15 runtime pattern: {needle}")


def validate(root: Path) -> None:
    root = root.resolve()
    api = (root / "scripts/coolify_database_backup_api.py").read_text(encoding="utf-8")
    restore = (root / "scripts/postgres_restore_exercise.py").read_text(encoding="utf-8")
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    docs = (root / "docs/database-backups.md").read_text(encoding="utf-8")
    policy = (root / "docs/contracts/database-backup-policy.yml").read_text(encoding="utf-8")

    for marker in (
        'DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"',
        'SSH_TUNNEL_BASE_URL = "http://127.0.0.1:18000/api/v1"',
        'COOLIFY_API_TOKEN',
        'I_HAVE_REVIEWED_THE_COOLIFY_DATABASE_BACKUP_POLICY',
        '"save_s3": True',
        '"backup_now": True',
        's3_object_independently_verified',
        'refuse duplicate creation',
        'os.replace(temp_name, path)',
        'os.chmod(temp_name, 0o600)',
    ):
        require(api, marker, "scripts/coolify_database_backup_api.py")
    forbid(api, 'token="', "scripts/coolify_database_backup_api.py")
    forbid(api, "[\"pg_dump\"", "scripts/coolify_database_backup_api.py")

    for marker in (
        'I_HAVE_VERIFIED_A_DISPOSABLE_POSTGRES_RESTORE_TARGET',
        'solo_vps_restore_',
        'PGPASSFILE',
        '"--list"',
        '"--clean"',
        '"--if-exists"',
        '"--no-owner"',
        '"--no-acl"',
        'empty_before_restore',
        'user_functions',
        'user_types',
        'application_verification',
        'application verification query must be a read-only SELECT',
        'default_transaction_read_only=on',
        'PGPASS entries must contain exactly five colon-separated fields',
        '[REDACTED]',
    ):
        require(restore, marker, "scripts/postgres_restore_exercise.py")
    forbid(restore, "PGPASSWORD", "scripts/postgres_restore_exercise.py")

    for marker in (
        "SOLO_VPS_STATE_DIR ?= $(SOLO_VPS_DATA_DIR)/state",
        "DATABASE_BACKUP_STATE_DIR ?= $(SOLO_VPS_STATE_DIR)/database-backups",
        "validate-database-backup-runtime:",
        "test-database-backup-runtime:",
        "database-backup-plan:",
        "database-backup-adopt:",
        "database-backup-configure:",
        "database-backup-trigger:",
        "database-backup-verify:",
        "database-restore-inspect:",
        "database-restore-exercise:",
    ):
        require(makefile, marker, "Makefile")

    for marker in (
        "owner: coolify",
        "frequency_default: daily",
        "retention_amount_locally_default: 2",
        "retention_days_s3_default: 30",
        "freshness_hours_default: 36",
        "managed_state: external-controller-state",
        "target_database_prefix: solo_vps_restore_",
        "empty_target_required: true",
        "application_verification_required: true",
    ):
        require(policy, marker, "docs/contracts/database-backup-policy.yml")

    for marker in (
        "Coolify API operational layer",
        "does not run a second database dump scheduler",
        "S3 object independently verified: no",
        "Disposable restore exercise",
        "`Application tests`",
    ):
        require(docs, marker, "docs/database-backups.md")

    print("PASS database backup runtime contract: Coolify schedule ownership + disposable logical restore source are bounded")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate(Path(args.root))
    except (OSError, ContractError) as exc:
        print(f"ERROR database backup runtime contract: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
