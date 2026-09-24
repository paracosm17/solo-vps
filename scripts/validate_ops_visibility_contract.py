#!/usr/bin/env python3
"""Validate the M22 read-only operational status/logging contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    print("ERROR ops visibility contract: PyYAML is required (Python module 'yaml').", file=sys.stderr)
    raise SystemExit(127)


class OpsVisibilityContractError(ValueError):
    """Raised when the M22 lightweight operations contract is weakened."""


READ_ONLY_MODULES = {
    "ansible.builtin.service_facts",
    "ansible.builtin.command",
    "ansible.builtin.uri",
    "ansible.builtin.assert",
    "ansible.builtin.debug",
}


def load_yaml(path: Path, label: str) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise OpsVisibilityContractError(f"cannot read {label} {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise OpsVisibilityContractError(f"invalid YAML in {label} {path}: {exc}") from exc


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise OpsVisibilityContractError(f"{label} must be a YAML list")
    return value


def require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OpsVisibilityContractError(f"{label} must be a YAML mapping")
    return value


def validate_role_playbook(path: Path, role_name: str, gather_facts: bool) -> None:
    plays = require_list(load_yaml(path, f"{role_name} playbook"), f"{role_name} playbook")
    if len(plays) != 1:
        raise OpsVisibilityContractError(f"{path.name} must contain exactly one play")
    play = require_mapping(plays[0], f"{role_name} play")
    if play.get("hosts") != "all" or play.get("become") is not True or play.get("gather_facts") is not gather_facts:
        raise OpsVisibilityContractError(
            f"{path.name} must target all hosts with become:true and gather_facts:{str(gather_facts).lower()}"
        )
    tasks = require_list(play.get("tasks"), f"{role_name} play tasks")
    if len(tasks) != 1:
        raise OpsVisibilityContractError(f"{path.name} must contain exactly one role import task")
    task = require_mapping(tasks[0], f"{role_name} import task")
    if set(key for key in task if key.startswith("ansible.")) != {"ansible.builtin.import_role"}:
        raise OpsVisibilityContractError(f"{path.name} may import only one role")
    role = require_mapping(task["ansible.builtin.import_role"], f"{role_name} import_role")
    if role.get("name") != role_name:
        raise OpsVisibilityContractError(f"{path.name} must import role {role_name}")


def validate_read_only_tasks(path: Path, require_uri: bool = False) -> None:
    tasks = require_list(load_yaml(path, "ops role tasks"), "ops role tasks")
    seen: set[str] = set()
    for index, item in enumerate(tasks, start=1):
        task = require_mapping(item, f"ops task {index}")
        modules = [key for key in task if key.startswith("ansible.")]
        if len(modules) != 1:
            raise OpsVisibilityContractError(f"ops task {index} must contain exactly one ansible module")
        module = modules[0]
        seen.add(module)
        if module not in READ_ONLY_MODULES:
            raise OpsVisibilityContractError(f"mutating or unsupported module in M22 role: {module}")
        if module in {"ansible.builtin.command", "ansible.builtin.uri"} and task.get("changed_when") is not False:
            raise OpsVisibilityContractError(f"{module} in M22 must declare changed_when: false")
    if "ansible.builtin.debug" not in seen:
        raise OpsVisibilityContractError("M22 role must emit a human-readable debug result")
    if require_uri and "ansible.builtin.uri" not in seen:
        raise OpsVisibilityContractError("ops status must include the loopback Coolify health probe")


def validate_makefile(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    required = (
        "ops-status: doctor-admin-local",
        "ops-logs: doctor-admin-local check-ops-log-args",
        "OPS_LOG_CONTAINER ?= $(CONTAINER)",
        "OPS_LOG_TAIL ?= $(if $(TAIL),$(TAIL),100)",
        "TAIL must be an integer from 1 to 1000",
        "CONTAINER must be one exact Docker container name",
    )
    for token in required:
        if token not in text:
            raise OpsVisibilityContractError(f"Makefile missing M22 contract token: {token}")
    if "ops-logs CONTAINER=<container-name>" not in text and "ops-logs: doctor-admin-local" not in text:
        raise OpsVisibilityContractError("ops logs must require one explicit container")


def validate_docs(root: Path) -> None:
    fallback_path = root / "docs/operations/status-and-logs.md"
    fallback = fallback_path.read_text(encoding="utf-8")
    fallback_required = (
        "make ops-status",
        "make ops-logs CONTAINER=",
        "TAIL=100",
        "read-only",
        "review before sharing",
        "fallback",
        "not the normal daily",
    )
    for token in fallback_required:
        if token not in fallback:
            raise OpsVisibilityContractError(f"operations fallback docs missing: {token}")

    ui_path = root / "docs/operations/operator-ui.md"
    ui = ui_path.read_text(encoding="utf-8")
    ui_required = (
        "GitHub Actions",
        "GHCR",
        "Coolify",
        "Deployments",
        "Environment Variables",
        "Environment secrets",
        "Grafana",
        "deployment-rollback.md",
        "status-and-logs.md",
    )
    for token in ui_required:
        if token not in ui:
            raise OpsVisibilityContractError(f"operator UI docs missing: {token}")

    observability = (root / "docs/operations/observability.md").read_text(encoding="utf-8")
    for token in (
        "Grafana Alloy",
        "Grafana Cloud",
        "Absolute time range",
        "Download",
        "does **not** require a second VPS",
        "Coolify Log Drain",
        "outbound HTTPS",
        "structured logs",
        "same Solo VPS revision on both your workstation and VPS",
        r"Get-ChildItem .\scripts\windows\*.ps1 | Unblock-File",
        '<div role="listitem"><span>1</span><div><strong>Application · VPS</strong>',
        "Drilldown → Logs",
        "Line filter",
        "client-side search",
        "do not need Explore or LogQL",
    ):
        if token not in observability:
            raise OpsVisibilityContractError(f"observability docs missing: {token}")

    observability_ru = (root / "docs/operations/observability.ru.md").read_text(encoding="utf-8")
    for token in (
        "одна и та же версия Solo VPS на компьютере и VPS",
        r"Get-ChildItem .\scripts\windows\*.ps1 | Unblock-File",
        '<div role="listitem"><span>1</span><div><strong>Приложение · VPS</strong>',
        "Drilldown → Logs",
        "Line filter",
        "client-side search",
        "не нужен Explore и не нужен LogQL",
    ):
        if token not in observability_ru:
            raise OpsVisibilityContractError(f"Russian observability docs missing: {token}")

    for forbidden in (
        "1. Open **Explore**.",
        "1. Откройте **Explore**.",
    ):
        if forbidden in observability + observability_ru:
            raise OpsVisibilityContractError(f"beginner observability flow must not require Explore first: {forbidden}")

    postgres_guide = (root / "docs/operations/postgresql-backups.md").read_text(encoding="utf-8")
    for token in (
        "# 4. Back up and restore PostgreSQL",
        "Backup Now",
        "Local Storage",
        "before-backup",
        "after-backup",
        "Configuration → Import Backup",
        "Restore Database from File",
        "same PostgreSQL **major version**",
        "does **not** protect against losing the VPS",
    ):
        if token not in postgres_guide:
            raise OpsVisibilityContractError(f"guided PostgreSQL backup docs missing: {token}")

    postgres_guide_ru = (root / "docs/operations/postgresql-backups.ru.md").read_text(encoding="utf-8")
    for token in (
        "# 4. Сделайте и восстановите резервную копию PostgreSQL",
        "Backup Now",
        "Local Storage",
        "before-backup",
        "after-backup",
        "Configuration → Import Backup",
        "Restore Database from File",
        "та же PostgreSQL **major version**",
        "не защищает",
    ):
        if token not in postgres_guide_ru:
            raise OpsVisibilityContractError(f"Russian guided PostgreSQL backup docs missing: {token}")

    app_config = (root / "docs/operations/application-config-and-secrets.md").read_text(encoding="utf-8")
    for token in (
        "APP_CONFIG_JSON",
        "Multiline",
        "Build Variable",
        "Runtime",
        "Docker Build Secrets",
        "Shared variables",
        "not equivalent to Vault",
    ):
        if token not in app_config:
            raise OpsVisibilityContractError(f"application config/secrets docs missing: {token}")

    dashboard = (root / "docs/operations/coolify-dashboard-domain.md").read_text(encoding="utf-8")
    for token in (
        "6001",
        "6002",
        "websocket",
        "https://coolify.example.com",
        "raw management ports remain private",
        "make audit",
    ):
        if token not in dashboard:
            raise OpsVisibilityContractError(f"Coolify dashboard-domain docs missing: {token}")

    passport = (root / "PROJECT_PASSPORT.md").read_text(encoding="utf-8")
    for token in (
        "UI-first operations",
        "SOPS + age is not a Vault replacement",
        "application runtime secrets",
        "Coolify Environment Variables",
        "Optional modules",
        "Professional observability",
        "zero dependency from core acceptance criteria",
    ):
        if token not in passport:
            raise OpsVisibilityContractError(f"Passport missing high-level operator/optionality boundary: {token}")


def validate(root: Path) -> None:
    validate_role_playbook(root / "ansible/playbooks/ops-status.yml", "ops_status", True)
    validate_role_playbook(root / "ansible/playbooks/ops-logs.yml", "ops_logs", False)
    validate_read_only_tasks(root / "ansible/roles/ops_status/tasks/main.yml", require_uri=True)
    ops_status_text = (root / "ansible/roles/ops_status/tasks/main.yml").read_text(encoding="utf-8")
    for token in (
        'daily_ui: "GitHub Actions for CI; Coolify for deployments, runtime logs, secrets and terminals"',
        'raw_log_fallback: "make ops-logs CONTAINER=<container-name> TAIL=100"',
    ):
        if token not in ops_status_text:
            raise OpsVisibilityContractError(f"ops-status output missing UI-first boundary: {token}")
    validate_read_only_tasks(root / "ansible/roles/ops_logs/tasks/main.yml")
    validate_makefile(root / "Makefile")
    validate_docs(root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validate(args.root.expanduser().resolve())
    except (OpsVisibilityContractError, OSError) as exc:
        print(f"ERROR ops visibility contract: {exc}", file=sys.stderr)
        return 2
    print("PASS ops visibility contract: bounded read-only status/logging UX is intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
