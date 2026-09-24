#!/usr/bin/env python3
"""Validate the M16 lost-VPS recovery source contract."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

try:
    import yaml
except ModuleNotFoundError:
    print("ERROR disaster recovery contract: PyYAML is required", file=sys.stderr)
    raise SystemExit(127)


class DisasterRecoveryContractError(RuntimeError):
    pass


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        raise DisasterRecoveryContractError(f"{where} missing required contract: {needle}")


def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        raise DisasterRecoveryContractError(f"{where} contains forbidden recovery behavior: {needle}")


def validate(root: Path) -> None:
    root = root.resolve()
    contract_path = root / "docs/contracts/disaster-recovery-policy.yml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    if not isinstance(contract, dict) or contract.get("version") != 1:
        raise DisasterRecoveryContractError("disaster recovery policy must be version 1")
    if contract.get("status") != "source-ready":
        raise DisasterRecoveryContractError("disaster recovery policy must remain source-ready until real V4 exercise")
    inputs = contract.get("recovery_inputs") or {}
    for key in (
        "source_release",
        "recovery_kit",
        "age_private_identity",
        "restic_repository",
        "coolify_instance_database_backup",
        "application_database_backups",
        "application_artifacts",
        "dns_provider_access",
    ):
        if key not in inputs:
            raise DisasterRecoveryContractError(f"recovery policy is missing input: {key}")
    fs = contract.get("filesystem_backup_boundary") or {}
    if fs.get("restore_mode") != "stage-and-select" or fs.get("direct_overlay_onto_fresh_coolify") != "forbidden":
        raise DisasterRecoveryContractError("filesystem recovery must stage-and-select rather than overwrite fresh Coolify")
    staging = fs.get("staging") or {}
    if staging != {
        "parent": "/var/tmp/solo-vps-disaster-recovery",
        "new_leaf_required": True,
        "owner": "root:root",
        "mode": "0700",
        "exact_confirmation": "I_HAVE_VERIFIED_A_PRIVATE_DISASTER_RECOVERY_STAGING_DIRECTORY",
    }:
        raise DisasterRecoveryContractError("filesystem recovery staging safety contract drifted")
    excludes = fs.get("excludes")
    if excludes != ["/data/coolify/ssh/mux", "/data/coolify/databases", "/data/coolify/backups"]:
        raise DisasterRecoveryContractError("M16/M14 raw recovery exclusions drifted")
    coolify = contract.get("coolify_instance_restore") or {}
    if not coolify.get("fresh_same_version_install_first") or coolify.get("old_env_wholesale_copy") != "forbidden":
        raise DisasterRecoveryContractError("Coolify restore must start from a fresh same-version install and preserve fresh env")
    if (coolify.get("previous_app_key") or {}).get("destination") != "APP_PREVIOUS_KEYS":
        raise DisasterRecoveryContractError("old APP_KEY must be installed only as APP_PREVIOUS_KEYS")
    if not coolify.get("fresh_database_credentials_preserved"):
        raise DisasterRecoveryContractError("fresh Coolify database credentials must be preserved")
    ssh_keys = coolify.get("ssh_keys") or {}
    if ssh_keys.get("localhost_private_key_resolution") != "restored-server-id-0-to-private-key-relation":
        raise DisasterRecoveryContractError("Coolify localhost key must resolve from the restored server id=0 relation")
    if not ssh_keys.get("only_database_associated_localhost_public_key_reauthorized"):
        raise DisasterRecoveryContractError("only the restored database-associated localhost key may be reauthorized")
    if ssh_keys.get("unrelated_recovered_keys_reauthorized_locally") is not False:
        raise DisasterRecoveryContractError("unrelated recovered Coolify keys must never gain local SSH authorization")

    kit = (root / "scripts/recovery_kit.py").read_text(encoding="utf-8")
    restore = (root / "scripts/coolify_instance_restore.py").read_text(encoding="utf-8")
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    docs = (root / "docs/disaster-recovery.md").read_text(encoding="utf-8")
    backup_defaults = (root / "ansible/roles/backup/defaults/main.yml").read_text(encoding="utf-8")
    backup_runtime = (root / "scripts/restic_runtime.py").read_text(encoding="utf-8")

    for needle in (
        "age private identity",
        "SSH private key",
        "off_vps_copy_verified",
        "state/database-backups/",
        "refusing private/plaintext secret material",
    ):
        require(kit, needle, "scripts/recovery_kit.py")
    forbid(kit, "hosts.yml", "scripts/recovery_kit.py")
    require(kit, "config/config.yml", "scripts/recovery_kit.py")
    require(kit, 'choices=("export", "verify", "extract")', "scripts/recovery_kit.py")
    require(kit, "refusing to overwrite existing recovery input", "scripts/recovery_kit.py")

    for needle in (
        "I_HAVE_VERIFIED_THE_REPLACEMENT_VPS_FOR_COOLIFY_RESTORE",
        "APP_PREVIOUS_KEYS",
        "--no-owner",
        "--no-acl",
        "pg_restore",
        "fresh_runtime_database_credentials_preserved",
        "old_env_will_replace_fresh_env: false",
        "/root/.solo-vps-disaster-recovery-target",
        "resolve_localhost_private_key_uuid",
        "localhost_key_uuid = resolve_localhost_private_key_uuid",
        "WHERE s.id = 0",
        "expected_local_key_name",
        "unrelated_recovered_keys_authorized_locally: false",
    ):
        require(restore, needle, "scripts/coolify_instance_restore.py")
    forbid(restore, "shutil.copyfile(_recovered_env", "scripts/coolify_instance_restore.py")

    for needle in (
        "- /data/coolify/databases",
        "- /data/coolify/backups",
    ):
        require(backup_defaults, needle, "backup defaults")
    require(backup_runtime, '"/data/coolify/databases"', "restic runtime")
    require(backup_runtime, '"/data/coolify/backups"', "restic runtime")
    require(
        backup_runtime,
        'RECOVERY_STAGING_CONFIRMATION = "I_HAVE_VERIFIED_A_PRIVATE_DISASTER_RECOVERY_STAGING_DIRECTORY"',
        "restic runtime",
    )
    require(backup_runtime, 'direct_overlay_onto_fresh_coolify: false', "restic runtime")

    for needle in (
        "validate-disaster-recovery",
        "test-disaster-recovery",
        "recovery-kit-export",
        "recovery-kit-verify",
        "recovery-kit-extract",
        "coolify-instance-restore-inspect",
        "coolify-instance-restore-plan",
        "backup-restore-staging",
    ):
        require(makefile, needle, "Makefile")

    for needle in (
        "old VPS lost",
        "fresh Ubuntu 24.04",
        "Coolify instance database backup",
        "APP_PREVIOUS_KEYS",
        "application PostgreSQL",
        "immutable",
        "make verify-coolify",
        "make audit",
        "arbitrary persistent volumes",
    ):
        require(docs, needle, "docs/disaster-recovery.md")

    print("PASS disaster recovery contract: off-VPS recovery kit + staged Coolify instance restore + PostgreSQL/app replay are explicit")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate(Path(args.root))
    except (OSError, yaml.YAMLError, DisasterRecoveryContractError) as exc:
        print(f"ERROR disaster recovery contract: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
