#!/usr/bin/env python3
"""Validate the M18 read-only verification orchestration contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    print("ERROR verify contract: PyYAML is required (Python module 'yaml').", file=sys.stderr)
    raise SystemExit(127)


class VerifyContractError(ValueError):
    """Raised when the M18 verification source contract is weakened."""


EXPECTED_VERIFY_IMPORTS = [
    "preflight.yml",
    "verify-base.yml",
    "verify-users.yml",
    "verify-firewall.yml",
    "verify-updates.yml",
    "verify-docker.yml",
    "verify-managed.yml",
    "verify-platform.yml",
]

READ_ONLY_MODULES = {
    "ansible.builtin.service_facts",
    "ansible.builtin.command",
    "ansible.builtin.stat",
    "ansible.builtin.set_fact",
    "ansible.builtin.debug",
    "ansible.builtin.assert",
}

EXPECTED_BOUNDARIES = {
    "ssh_hardening",
    "coolify_runtime",
    "backup_freshness",
    "database_restore",
}


def load_yaml(path: Path, label: str) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise VerifyContractError(f"cannot read {label} {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise VerifyContractError(f"invalid YAML in {label} {path}: {exc}") from exc


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise VerifyContractError(f"{label} must be a YAML list")
    return value


def require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VerifyContractError(f"{label} must be a YAML mapping")
    return value


def playbook_imports(path: Path) -> list[str]:
    items = require_list(load_yaml(path, "verify playbook"), "verify playbook")
    imports: list[str] = []
    for item in items:
        mapping = require_mapping(item, "verify playbook item")
        if set(mapping) != {"name", "ansible.builtin.import_playbook"}:
            raise VerifyContractError("verify.yml may contain only named ansible.builtin.import_playbook entries")
        name = mapping.get("name")
        if not isinstance(name, str) or not name.strip():
            raise VerifyContractError("verify.yml imported playbooks must have non-empty names")
        value = mapping.get("ansible.builtin.import_playbook")
        if not isinstance(value, str):
            raise VerifyContractError("verify.yml import_playbook value must be a string")
        imports.append(value)
    return imports


def validate_platform_playbook(path: Path) -> None:
    plays = require_list(load_yaml(path, "platform verify playbook"), "platform verify playbook")
    if len(plays) != 1:
        raise VerifyContractError("verify-platform.yml must contain exactly one play")
    play = require_mapping(plays[0], "platform verify play")
    if play.get("hosts") != "all" or play.get("become") is not True or play.get("gather_facts") is not True:
        raise VerifyContractError("verify-platform.yml must target all hosts with become:true and gather_facts:true")
    tasks = require_list(play.get("tasks"), "platform verify tasks")
    if len(tasks) != 1:
        raise VerifyContractError("verify-platform.yml must contain exactly one role import task")
    task = require_mapping(tasks[0], "platform verify role import")
    role = require_mapping(task.get("ansible.builtin.import_role"), "platform verify import_role")
    if role.get("name") != "platform_verify":
        raise VerifyContractError("verify-platform.yml must import only the platform_verify role")


def validate_read_only_tasks(path: Path) -> None:
    tasks = require_list(load_yaml(path, "platform verify tasks"), "platform verify tasks")
    seen_modules: set[str] = set()
    for index, item in enumerate(tasks, start=1):
        task = require_mapping(item, f"platform verify task {index}")
        modules = [key for key in task if key.startswith("ansible.")]
        if len(modules) != 1:
            raise VerifyContractError(f"platform verify task {index} must contain exactly one ansible module")
        module = modules[0]
        seen_modules.add(module)
        if module not in READ_ONLY_MODULES:
            raise VerifyContractError(f"mutating or unsupported module in platform verify role: {module}")
        if module == "ansible.builtin.command" and task.get("changed_when") is not False:
            raise VerifyContractError("every command in platform verification must declare changed_when: false")
    if "ansible.builtin.debug" not in seen_modules:
        raise VerifyContractError("platform verification must emit a structured debug summary")


def validate_boundaries(path: Path) -> None:
    defaults = require_mapping(load_yaml(path, "platform verify defaults"), "platform verify defaults")
    boundaries = require_mapping(
        defaults.get("solo_vps_verify_evidence_boundaries"),
        "solo_vps_verify_evidence_boundaries",
    )
    if set(boundaries) != EXPECTED_BOUNDARIES:
        raise VerifyContractError(
            "verification evidence boundaries must be exactly: " + ", ".join(sorted(EXPECTED_BOUNDARIES))
        )
    for key, value in boundaries.items():
        if not isinstance(value, str) or not value.strip():
            raise VerifyContractError(f"verification evidence boundary '{key}' must be a non-empty string")
        if value.startswith("PASS"):
            raise VerifyContractError(f"unavailable evidence boundary '{key}' must not claim PASS")


def validate(root: Path) -> None:
    imports = playbook_imports(root / "ansible/playbooks/verify.yml")
    if imports != EXPECTED_VERIFY_IMPORTS:
        raise VerifyContractError(
            "verify.yml import order drift: expected " + " -> ".join(EXPECTED_VERIFY_IMPORTS)
        )
    validate_platform_playbook(root / "ansible/playbooks/verify-platform.yml")
    validate_read_only_tasks(root / "ansible/roles/platform_verify/tasks/main.yml")
    validate_boundaries(root / "ansible/roles/platform_verify/defaults/main.yml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validate(args.root.expanduser().resolve())
    except VerifyContractError as exc:
        print(f"ERROR verify contract: {exc}", file=sys.stderr)
        return 2
    print("PASS verify contract: read-only orchestration and evidence boundaries are intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
