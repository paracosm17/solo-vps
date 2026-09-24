#!/usr/bin/env python3
"""Validate the M19 read-only security-audit orchestration contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    print("ERROR audit contract: PyYAML is required (Python module 'yaml').", file=sys.stderr)
    raise SystemExit(127)


class AuditContractError(ValueError):
    """Raised when the M19 audit source contract is weakened."""


EXPECTED_AUDIT_IMPORTS = [
    "preflight.yml",
    "verify-users.yml",
    "verify-firewall.yml",
    "verify-updates.yml",
    "verify-docker.yml",
]

READ_ONLY_MODULES = {
    "ansible.builtin.stat",
    "ansible.builtin.command",
    "ansible.builtin.set_fact",
    "ansible.builtin.debug",
    "ansible.builtin.assert",
}

EXPECTED_BOUNDARIES = {
    "external_reachability",
    "coolify_runtime",
    "backup_repository",
    "database_restore",
}

EXPECTED_DATA_PORTS = [5432, 6379]
EXPECTED_SENSITIVE_HOST_PORTS = [2375, 2376, 5432, 6379]
EXPECTED_DOCKER_PORT_KEY_PATTERN = r"^[0-9]+/(tcp|udp)$"


def load_yaml(path: Path, label: str) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AuditContractError(f"cannot read {label} {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise AuditContractError(f"invalid YAML in {label} {path}: {exc}") from exc


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise AuditContractError(f"{label} must be a YAML list")
    return value


def require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuditContractError(f"{label} must be a YAML mapping")
    return value


def validate_audit_playbook(path: Path) -> None:
    items = require_list(load_yaml(path, "audit playbook"), "audit playbook")
    if len(items) != len(EXPECTED_AUDIT_IMPORTS) + 1:
        raise AuditContractError("audit.yml must contain the reviewed verifier imports plus one audit play")

    imports: list[str] = []
    for index, item in enumerate(items[:-1], start=1):
        mapping = require_mapping(item, f"audit import item {index}")
        if set(mapping) != {"name", "ansible.builtin.import_playbook"}:
            raise AuditContractError("audit verifier prefix may contain only named import_playbook entries")
        name = mapping["name"]
        if not isinstance(name, str) or not name.strip():
            raise AuditContractError("audit import_playbook name must be a non-empty string")
        value = mapping["ansible.builtin.import_playbook"]
        if not isinstance(value, str):
            raise AuditContractError("audit import_playbook value must be a string")
        imports.append(value)

    if imports != EXPECTED_AUDIT_IMPORTS:
        raise AuditContractError(
            "audit verifier order drift: expected " + " -> ".join(EXPECTED_AUDIT_IMPORTS)
        )
    if "verify-ssh.yml" in imports:
        raise AuditContractError("default audit must not require staged SSH hardening activation")

    play = require_mapping(items[-1], "security audit play")
    if play.get("hosts") != "all" or play.get("become") is not True or play.get("gather_facts") is not True:
        raise AuditContractError("security audit play must target all hosts with become:true and gather_facts:true")
    tasks = require_list(play.get("tasks"), "security audit play tasks")
    if len(tasks) != 1:
        raise AuditContractError("security audit play must contain exactly one security_audit role import")
    task = require_mapping(tasks[0], "security audit role import")
    role = require_mapping(task.get("ansible.builtin.import_role"), "security audit import_role")
    if role.get("name") != "security_audit":
        raise AuditContractError("security audit play must import only the security_audit role")


def validate_defaults(audit_path: Path, ssh_path: Path) -> None:
    audit = require_mapping(load_yaml(audit_path, "audit defaults"), "audit defaults")
    ssh = require_mapping(load_yaml(ssh_path, "SSH defaults"), "SSH defaults")

    expected = audit.get("solo_vps_audit_expected_ssh_options")
    ssh_expected = ssh.get("solo_vps_sshd_expected_effective_options")
    if expected != ssh_expected:
        raise AuditContractError("audit SSH expectations must exactly match the M4 SSH hardening contract")

    if audit.get("solo_vps_audit_data_service_ports") != EXPECTED_DATA_PORTS:
        raise AuditContractError("audit data-service ports must remain exactly PostgreSQL 5432 and Redis 6379")
    if audit.get("solo_vps_audit_sensitive_host_ports") != EXPECTED_SENSITIVE_HOST_PORTS:
        raise AuditContractError("audit sensitive host ports must include Docker API and canonical data ports")

    if audit.get("solo_vps_audit_docker_port_key_pattern") != EXPECTED_DOCKER_PORT_KEY_PATTERN:
        raise AuditContractError("audit Docker container-port key pattern drifted from the reviewed contract")

    boundaries = require_mapping(
        audit.get("solo_vps_audit_evidence_boundaries"),
        "solo_vps_audit_evidence_boundaries",
    )
    if set(boundaries) != EXPECTED_BOUNDARIES:
        raise AuditContractError(
            "audit evidence boundaries must be exactly: " + ", ".join(sorted(EXPECTED_BOUNDARIES))
        )
    for key, value in boundaries.items():
        if not isinstance(value, str) or not value.startswith("UNAVAILABLE:"):
            raise AuditContractError(f"audit boundary '{key}' must explicitly start with UNAVAILABLE:")
        if "PASS" in value:
            raise AuditContractError(f"unavailable audit boundary '{key}' must not claim PASS")


def validate_read_only_tasks(path: Path) -> None:
    tasks = require_list(load_yaml(path, "security audit tasks"), "security audit tasks")
    seen_modules: set[str] = set()
    docker_container_ids_probe = False
    docker_full_inspect_probe = False
    docker_human_ports_probe = False
    ssh_effective_probe = False
    final_failure_assert = False

    for index, item in enumerate(tasks, start=1):
        task = require_mapping(item, f"security audit task {index}")
        modules = [key for key in task if key.startswith("ansible.")]
        if len(modules) != 1:
            raise AuditContractError(f"security audit task {index} must contain exactly one ansible module")
        module = modules[0]
        seen_modules.add(module)
        if module not in READ_ONLY_MODULES:
            raise AuditContractError(f"mutating or unsupported module in security audit role: {module}")
        if module == "ansible.builtin.command":
            if task.get("changed_when") is not False:
                raise AuditContractError("every audit command must declare changed_when: false")
            command = require_mapping(task[module], f"audit command task {index}")
            argv = command.get("argv")
            if isinstance(argv, list):
                rendered = " ".join(str(part) for part in argv)
                if " ps --quiet" in f" {rendered}":
                    docker_container_ids_probe = True
                if " container inspect " in f" {rendered} ":
                    docker_full_inspect_probe = True
                if "{{.Ports}}" in rendered:
                    docker_human_ports_probe = True
                if " -T" in f" {rendered}" or rendered.endswith(" -T"):
                    ssh_effective_probe = True
        if module == "ansible.builtin.assert":
            assertion = require_mapping(task[module], f"audit assert task {index}")
            that = assertion.get("that")
            if isinstance(that, list) and any("solo_vps_audit_failures | length == 0" in str(x) for x in that):
                final_failure_assert = True

    if "ansible.builtin.debug" not in seen_modules:
        raise AuditContractError("security audit must emit a structured debug summary")
    if not docker_container_ids_probe:
        raise AuditContractError("security audit must enumerate running Docker containers before publication inspection")
    if not docker_full_inspect_probe:
        raise AuditContractError("security audit must read full structured Docker container inspect state separately from UFW")
    if docker_human_ports_probe:
        raise AuditContractError("security audit must not parse human-oriented docker ps .Ports output")
    if not ssh_effective_probe:
        raise AuditContractError("security audit must inspect effective sshd -T policy")
    if not final_failure_assert:
        raise AuditContractError("security audit must fail closed on explicit solo_vps_audit_failures")

    text = path.read_text(encoding="utf-8")
    for marker in ("PENDING", "WARN", "UNAVAILABLE"):
        if marker not in text:
            raise AuditContractError(f"security audit source must preserve explicit {marker} semantics")
    required_source_markers = {
        ".NetworkSettings.Ports": "read Docker port bindings from full structured inspect state",
        "| dict2items": "convert Docker port maps into explicit structured items",
        "subelements('value')": "enumerate every structured Docker host binding",
        "Validate structured Docker host-binding objects": "fail closed on malformed Docker binding objects",
        "solo_vps_audit_docker_bindings": "report normalized Docker binding evidence",
        "item.protocol != 'tcp'": "reject non-TCP Docker publications outside loopback",
        "firewall.public_ports": "reuse the reviewed public edge-port config",
        "solo_vps_audit_docker_server_major | int < 28": "preserve the Docker <28 localhost publication warning",
    }
    for marker, reason in required_source_markers.items():
        if marker not in text:
            raise AuditContractError(f"security audit must {reason}")


def validate_makefile(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    required = [
        "AUDIT_CONTRACT_VALIDATOR := scripts/validate_audit_contract.py",
        "validate-audit-contract:",
        "test-audit-contract:",
        "audit: doctor-platform-local",
        "$(PLAYBOOK_DIR)/audit.yml",
    ]
    for marker in required:
        if marker not in text:
            raise AuditContractError(f"Makefile is missing M19 audit contract marker: {marker}")

    validate_line = next((line for line in text.splitlines() if line.startswith("validate:")), "")
    for target in ("validate-audit-contract", "test-audit-contract"):
        if target not in validate_line:
            raise AuditContractError(f"make validate must include {target}")


def validate(root: Path) -> None:
    validate_audit_playbook(root / "ansible/playbooks/audit.yml")
    validate_defaults(
        root / "ansible/roles/security_audit/defaults/main.yml",
        root / "ansible/roles/ssh/defaults/main.yml",
    )
    validate_read_only_tasks(root / "ansible/roles/security_audit/tasks/main.yml")
    validate_makefile(root / "Makefile")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validate(args.root.expanduser().resolve())
    except (AuditContractError, OSError) as exc:
        print(f"ERROR audit contract: {exc}", file=sys.stderr)
        return 2
    print("PASS audit contract: read-only security interpretation and evidence boundaries are intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
