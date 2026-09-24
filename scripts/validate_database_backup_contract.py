#!/usr/bin/env python3
"""Validate the source-only M15 database-backup responsibility contract."""
from __future__ import annotations
import argparse
import pathlib
import re
import sys
from typing import Any
import yaml

class DatabaseBackupContractError(ValueError):
    pass

REQUIRED_DUMP_ARGS = {"--format=custom", "--no-acl", "--no-owner"}
CREDENTIAL_KEY_RE = re.compile(r"(?:password|secret|token|access[_-]?key|private[_-]?key|credential)", re.IGNORECASE)
ADR_STATUS_RE = re.compile(r"^Status:\s*(Proposed|Accepted|Superseded|Deprecated|Rejected)\s*$", re.MULTILINE)

def load_yaml(path: pathlib.Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DatabaseBackupContractError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise DatabaseBackupContractError(f"invalid YAML in {path}: {exc}") from exc

def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DatabaseBackupContractError(f"{name} must be a mapping")
    return value

def _reject_credential_keys(value: Any, path: str = "contract") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if CREDENTIAL_KEY_RE.search(key_text) and not (key_text == "credentials_in_public_config" and child == "forbidden"):
                raise DatabaseBackupContractError(f"credential-like key is not allowed in public contract: {path}.{key_text}")
            _reject_credential_keys(child, f"{path}.{key_text}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_credential_keys(child, f"{path}[{index}]")

def validate(contract: Any, adr_text: str, backup_defaults: Any) -> None:
    contract = _mapping(contract, "contract")
    defaults = _mapping(backup_defaults, "backup defaults")
    if contract.get("version") != 1:
        raise DatabaseBackupContractError("contract version must be 1")
    match = ADR_STATUS_RE.search(adr_text)
    if not match:
        raise DatabaseBackupContractError("ADR status is missing or invalid")
    if contract.get("status") != match.group(1).lower():
        raise DatabaseBackupContractError("contract status must match ADR-0003 status")
    if contract.get("owner") != "coolify":
        raise DatabaseBackupContractError("Coolify must own the accepted application database backup lifecycle")
    scope = _mapping(contract.get("scope"), "scope")
    if scope != {"engine": "postgresql", "lifecycle": "application"}:
        raise DatabaseBackupContractError("M15 source contract must target Coolify-managed PostgreSQL application lifecycle")
    backup = _mapping(contract.get("backup"), "backup")
    if backup.get("method") != "logical" or backup.get("program") != "pg_dump" or backup.get("format") != "custom":
        raise DatabaseBackupContractError("PostgreSQL backup must be a logical custom-format pg_dump")
    args = backup.get("required_arguments")
    if not isinstance(args, list) or set(args) != REQUIRED_DUMP_ARGS or len(args) != len(REQUIRED_DUMP_ARGS):
        raise DatabaseBackupContractError("pg_dump arguments must be exactly --format=custom, --no-acl, --no-owner")
    verification = _mapping(contract.get("verification"), "verification")
    if verification.get("program") != "pg_restore" or verification.get("required_arguments") != ["--list"]:
        raise DatabaseBackupContractError("archive verification must require pg_restore --list")
    storage = _mapping(contract.get("storage"), "storage")
    if storage != {"backend": "s3-compatible", "off_site_required": True, "credentials_in_public_config": "forbidden"}:
        raise DatabaseBackupContractError("storage contract must require off-site S3-compatible storage without public credentials")
    scheduling = _mapping(contract.get("scheduling"), "scheduling")
    required_scheduling = {
        "owner": "coolify",
        "frequency_required": True,
        "retention_required": True,
        "frequency_default": "daily",
        "retention_amount_locally_default": 2,
        "retention_days_s3_default": 30,
        "freshness_hours_default": 36,
    }
    if scheduling != required_scheduling:
        raise DatabaseBackupContractError("Coolify must own explicit schedule/retention/freshness defaults")
    operation = _mapping(contract.get("operation"), "operation")
    if operation != {
        "api_transport": "loopback-only",
        "save_s3_required": True,
        "managed_state": "external-controller-state",
        "existing_schedule_adoption": "explicit",
        "mutation_confirmation": "I_HAVE_REVIEWED_THE_COOLIFY_DATABASE_BACKUP_POLICY",
        "independent_s3_object_check_required_for_v3": True,
    }:
        raise DatabaseBackupContractError("M15 operational API ownership boundary drifted")
    restore = _mapping(contract.get("restore"), "restore")
    if restore != {
        "target_database_prefix": "solo_vps_restore_",
        "empty_target_required": True,
        "authentication": "pgpass-file",
        "application_verification_required": True,
        "destructive_confirmation": "I_HAVE_VERIFIED_A_DISPOSABLE_POSTGRES_RESTORE_TARGET",
    }:
        raise DatabaseBackupContractError("M15 disposable restore safety boundary drifted")
    expected_boundaries = {
        "raw_pgdata_backup": "forbidden",
        "ansible_pg_dump_scheduler": "forbidden",
        "restic_pg_dump_scheduler": "forbidden",
        "coolify_instance_backup_covers_application_data": False,
        "restore_test_required_for_completion": True,
    }
    if _mapping(contract.get("boundaries"), "boundaries") != expected_boundaries:
        raise DatabaseBackupContractError("database backup responsibility boundaries drifted")
    _reject_credential_keys(contract)
    forbidden_sources = defaults.get("solo_vps_backup_forbidden_source_prefixes")
    if not isinstance(forbidden_sources, list) or "/var/lib/postgresql" not in forbidden_sources:
        raise DatabaseBackupContractError("M14 must keep /var/lib/postgresql forbidden as a raw restic source")

def validate_no_duplicate_runner(root: pathlib.Path) -> None:
    patterns = [re.compile(r"\bpg_dump\b"), re.compile(r"\bpg_restore\b")]
    files: list[pathlib.Path] = []
    base = root / "ansible"
    if base.exists():
        files.extend(path for path in base.rglob("*") if path.is_file())
    makefile = root / "Makefile"
    if makefile.exists():
        files.append(makefile)
    offenders: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(text) for pattern in patterns):
            offenders.append(str(path.relative_to(root)))
    if offenders:
        raise DatabaseBackupContractError("active host automation must not add a duplicate PostgreSQL dump/restore runner under accepted ADR-0003: " + ", ".join(sorted(offenders)))

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=pathlib.Path)
    parser.add_argument("adr", type=pathlib.Path)
    parser.add_argument("backup_defaults", type=pathlib.Path)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path("."))
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    try:
        adr_text = args.adr.read_text(encoding="utf-8")
        validate(load_yaml(args.contract), adr_text, load_yaml(args.backup_defaults))
        validate_no_duplicate_runner(args.root)
    except (OSError, DatabaseBackupContractError) as exc:
        print(f"ERROR database backup contract: {exc}", file=sys.stderr)
        return 2
    print("PASS database backup contract")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
