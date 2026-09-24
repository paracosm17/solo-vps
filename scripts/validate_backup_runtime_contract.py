#!/usr/bin/env python3
"""Validate the source-only M14 operational restic runtime contract."""
from __future__ import annotations

import pathlib
import re
import sys


class ContractError(RuntimeError):
    pass


def require(text: str, marker: str, source: str) -> None:
    if marker not in text:
        raise ContractError(f"{source} is missing required marker: {marker}")


def validate(root: pathlib.Path) -> None:
    runtime = (root / "scripts/restic_runtime.py").read_text(encoding="utf-8")
    defaults = (root / "ansible/roles/backup/defaults/main.yml").read_text(encoding="utf-8")
    runtime_tasks = (root / "ansible/roles/backup/tasks/runtime.yml").read_text(encoding="utf-8")
    verify_tasks = (root / "ansible/roles/backup/tasks/verify-runtime.yml").read_text(encoding="utf-8")
    operation_tasks = (root / "ansible/roles/backup/tasks/operation.yml").read_text(encoding="utf-8")
    service = (root / "ansible/roles/backup/templates/solo-vps-backup.service.j2").read_text(encoding="utf-8")
    timer = (root / "ansible/roles/backup/templates/solo-vps-backup.timer.j2").read_text(encoding="utf-8")
    maintenance_service = (root / "ansible/roles/backup/templates/solo-vps-backup-maintenance.service.j2").read_text(encoding="utf-8")
    maintenance_timer = (root / "ansible/roles/backup/templates/solo-vps-backup-maintenance.timer.j2").read_text(encoding="utf-8")
    makefile = (root / "Makefile").read_text(encoding="utf-8")

    for marker in (
        'RESTIC = Path("/usr/local/bin/restic")',
        'RUNTIME_SECRET_ROOT = Path("/run")',
        'DEFAULT_CREDENTIALS = Path("/etc/solo-vps/backup/credentials.json")',
        '"RESTIC_REPOSITORY": config.repository',
        '"RESTIC_PASSWORD_FILE": str(password_file)',
        '"AWS_SHARED_CREDENTIALS_FILE": str(aws_credentials)',
        '"AWS_PROFILE": "solo-vps"',
        '"backup", *config.sources',
        '"--group-by", config.group_by',
        '"--dry-run"',
        '"--prune"',
        '"restore", "latest"',
        'RECOVERY_STAGING_CONFIRMATION = "I_HAVE_VERIFIED_A_PRIVATE_DISASTER_RECOVERY_STAGING_DIRECTORY"',
        'RECOVERY_STAGING_PARENT = Path("/var/tmp/solo-vps-disaster-recovery")',
        'direct_overlay_onto_fresh_coolify: false',
        'production_paths_modified: false',
        'retention apply requires the exact reviewed-plan confirmation',
    ):
        require(runtime, marker, "restic runtime")

    if re.search(r"print\([^\n]*(RESTIC_PASSWORD|AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID)", runtime):
        raise ContractError("restic runtime must not print credential values")
    for forbidden in ('"RESTIC_PASSWORD":', '"AWS_ACCESS_KEY_ID":', '"AWS_SECRET_ACCESS_KEY":'):
        if forbidden in runtime:
            raise ContractError("restic child environment must use private credential/password files, not secret environment values")

    for marker in (
        "solo_vps_backup_freshness_hours: 36",
        "solo_vps_backup_runtime_path: /etc/solo-vps/backup/runtime.json",
        "solo_vps_backup_timer_on_calendar: '*-*-* 03:15:00'",
        "solo_vps_backup_recovery_staging_parent: /var/tmp/solo-vps-disaster-recovery",
        "solo_vps_backup_recovery_staging_confirm_required: I_HAVE_VERIFIED_A_PRIVATE_DISASTER_RECOVERY_STAGING_DIRECTORY",
        "- restore-staging",
    ):
        require(defaults, marker, "backup defaults")

    for marker in (
        "scripts/restic_runtime.py",
        "scripts/backup_credentials_common.py",
        "solo-vps-backup.service.j2",
        "solo-vps-backup.timer.j2",
        "solo-vps-backup-maintenance.service.j2",
        "solo-vps-backup-maintenance.timer.j2",
    ):
        require(runtime_tasks, marker, "backup runtime tasks")

    for marker in (
        "runtime_config_mode",
        "timer_enabled",
        "timer_active",
        "maintenance_timer_enabled",
        "maintenance_timer_active",
        "credentials_mode",
    ):
        require(verify_tasks, marker, "backup runtime verifier")

    require(operation_tasks, "solo_vps_backup_operation in", "backup operation tasks")
    require(operation_tasks, "retention-apply", "backup operation tasks")
    require(operation_tasks, "schedule-enable", "backup operation tasks")
    require(operation_tasks, "maintenance-schedule-enable", "backup operation tasks")
    require(operation_tasks, "restore-staging", "backup operation tasks")
    require(operation_tasks, "solo_vps_backup_recovery_staging_target", "backup operation tasks")
    require(operation_tasks, 'mode: "0700"', "backup operation tasks")
    for line_number, line in enumerate(operation_tasks.splitlines(), 1):
        if len(line) > 240:
            raise ContractError(
                f"backup operation tasks line {line_number} exceeds the M20 yamllint 240-character limit"
            )

    for marker in (
        "User=root",
        "ExecStart=/usr/local/libexec/solo-vps/restic-runtime backup",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "UMask=0077",
    ):
        require(service, marker, "backup systemd service")
    for marker in ("OnCalendar={{ solo_vps_backup_timer_on_calendar }}", "Persistent=true", "RandomizedDelaySec={{ solo_vps_backup_timer_randomized_delay }}"):
        require(timer, marker, "backup systemd timer")

    for marker in (
        "ExecStart=/usr/local/libexec/solo-vps/restic-runtime retention-apply --confirm",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
    ):
        require(maintenance_service, marker, "backup maintenance service")
    for marker in (
        "OnCalendar={{ solo_vps_backup_maintenance_timer_on_calendar }}",
        "Persistent=true",
        "RandomizedDelaySec={{ solo_vps_backup_maintenance_timer_randomized_delay }}",
    ):
        require(maintenance_timer, marker, "backup maintenance timer")

    for target in (
        "backup-runtime:",
        "verify-backup-runtime:",
        "backup-repository-init:",
        "backup-repository-adopt:",
        "backup-now:",
        "backup-status:",
        "backup-check:",
        "backup-retention-plan:",
        "backup-retention-apply:",
        "backup-restore-test:",
        "backup-restore-staging:",
        "backup-schedule-enable:",
        "backup-maintenance-schedule-enable:",
    ):
        require(makefile, target, "Makefile")


def main() -> int:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    try:
        validate(root)
    except (OSError, ContractError) as exc:
        print(f"ERROR backup runtime contract: {exc}", file=sys.stderr)
        return 2
    print("PASS backup runtime contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
