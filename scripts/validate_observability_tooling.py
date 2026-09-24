#!/usr/bin/env python3
"""Validate the source-only M24 pinned Grafana Alloy host-tooling contract."""

from __future__ import annotations

import pathlib
import re
import sys
from typing import Any
from urllib.parse import urlparse

try:
    import yaml
except ModuleNotFoundError:
    print("ERROR observability tooling contract: PyYAML is required.", file=sys.stderr)
    raise SystemExit(127)

EXPECTED_VERSION = "1.18.1"
EXPECTED_ARCHES = {"x86_64": "amd64", "aarch64": "arm64"}
EXPECTED_SHA256 = {
    "x86_64": "7d7b8211ac97f5cda63f908325f64d52aa4bbaeb496897d8234f75bad87d9cb2",
    "aarch64": "4d360ba922fdeb7b3ad65c6c73283d2eb65d9cb5f83c9809f23db7b85a108b54",
}
EXPECTED_INSTALL_PATH = "/usr/local/bin/alloy"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    pass


def load_yaml(path: pathlib.Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"cannot read/parse {path}: {exc}") from exc


def validate_defaults(data: Any) -> None:
    if not isinstance(data, dict):
        raise ContractError("observability defaults must be a YAML mapping")

    if data.get("solo_vps_alloy_version") != EXPECTED_VERSION:
        raise ContractError(f"Alloy version must be exact {EXPECTED_VERSION}")
    if data.get("solo_vps_alloy_install_path") != EXPECTED_INSTALL_PATH:
        raise ContractError("Alloy install path must remain /usr/local/bin/alloy")
    if data.get("solo_vps_alloy_dpkg_deb_binary") != "/usr/bin/dpkg-deb":
        raise ContractError("Alloy extraction must use the explicit dpkg-deb path")

    artifacts = data.get("solo_vps_alloy_artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(EXPECTED_ARCHES):
        raise ContractError("Alloy artifacts must cover exactly x86_64 and aarch64")

    for ansible_arch, release_arch in EXPECTED_ARCHES.items():
        item = artifacts[ansible_arch]
        if not isinstance(item, dict):
            raise ContractError(f"Alloy artifact {ansible_arch} must be a mapping")
        url = item.get("url")
        digest = item.get("sha256")
        if not isinstance(url, str):
            raise ContractError(f"Alloy artifact {ansible_arch} URL must be a string")
        parsed = urlparse(url)
        expected_path = (
            f"/grafana/alloy/releases/download/v{EXPECTED_VERSION}/"
            f"alloy-{EXPECTED_VERSION}-1.{release_arch}.deb"
        )
        if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.path != expected_path:
            raise ContractError(f"Alloy artifact {ansible_arch} must use the exact official GitHub release URL")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ContractError(f"Alloy artifact {ansible_arch} must have an exact SHA-256 pin")
        if digest != EXPECTED_SHA256[ansible_arch]:
            raise ContractError(f"Alloy artifact {ansible_arch} SHA-256 does not match the reviewed pin")

    if data.get("solo_vps_alloy_conflicting_paths") != ["/usr/bin/alloy"]:
        raise ContractError("vendor/distro Alloy migration guard must remain explicit")


def validate_task_policy(role_dir: pathlib.Path) -> None:
    install_text = (role_dir / "tasks" / "install-alloy.yml").read_text(encoding="utf-8")
    inspect_text = (role_dir / "tasks" / "inspect-existing.yml").read_text(encoding="utf-8")
    verify_text = (role_dir / "tasks" / "verify-tooling.yml").read_text(encoding="utf-8")

    for marker in [
        "ansible.builtin.get_url:",
        "checksum:",
        "--extract",
        "ansible.builtin.copy:",
        "remote_src: true",
        "ansible.builtin.import_tasks: inspect-existing.yml",
        "always:",
        "without installing or starting a service",
    ]:
        if marker not in install_text:
            raise ContractError(f"Alloy install task is missing required safety marker: {marker}")

    for marker in [
        "ansible.builtin.apt:",
        "ansible.builtin.package:",
        "ansible.builtin.systemd",
        "ansible.builtin.systemd_service",
        "ansible.builtin.service:",
        "docker.sock",
        "loki.write",
        "prometheus.remote_write",
        "state: latest",
        "ansible.builtin.shell:",
        "ansible.builtin.raw:",
    ]:
        if marker in install_text:
            raise ContractError(f"Alloy tooling slice contains out-of-scope behavior: {marker}")

    if "Refuse implicit migration or replacement" not in inspect_text:
        raise ContractError("Alloy tooling must fail closed around pre-existing installations")

    allowed_verify_modules = {
        "ansible.builtin.import_tasks",
        "ansible.builtin.stat",
        "ansible.builtin.command",
        "ansible.builtin.assert",
        "ansible.builtin.debug",
    }
    modules = set(re.findall(r"^\s+(ansible\.builtin\.[a-zA-Z0-9_]+):\s*$", verify_text, flags=re.MULTILINE))
    unexpected = sorted(modules - allowed_verify_modules)
    if unexpected:
        raise ContractError(f"verify-tooling contains non-read-only modules: {unexpected}")

    for required_boundary in [
        "service_configured: false",
        "docker_socket_access_configured: false",
        "public_listener_configured: false",
        "remote_backend_configured: false",
        "telemetry_delivery_claimed: false",
    ]:
        if required_boundary not in verify_text:
            raise ContractError(f"Alloy verifier is missing explicit evidence boundary: {required_boundary}")


def validate_playbooks(root: pathlib.Path) -> None:
    apply_text = (root / "ansible/playbooks/observability-tooling.yml").read_text(encoding="utf-8")
    verify_text = (root / "ansible/playbooks/verify-observability-tooling.yml").read_text(encoding="utf-8")
    if "role: observability" not in apply_text:
        raise ContractError("observability-tooling playbook must use the observability role")
    if "tasks_from: verify-tooling.yml" not in verify_text:
        raise ContractError("verify-observability-tooling must invoke the read-only verifier")



def validate_makefile(root: pathlib.Path) -> None:
    text = (root / "Makefile").read_text(encoding="utf-8")
    required = [
        "validate-observability-tooling:",
        "test-observability-tooling:",
        "observability-tooling: doctor-admin-local",
        "verify-observability-tooling: doctor-admin-local",
        "$(PLAYBOOK_DIR)/observability-tooling.yml --syntax-check",
        "$(PLAYBOOK_DIR)/verify-observability-tooling.yml --syntax-check",
    ]
    for marker in required:
        if marker not in text:
            raise ContractError(f"Makefile is missing M24 tooling wiring: {marker}")

    match = re.search(r"^validate:\s+([^#\n]+)", text, flags=re.MULTILINE)
    if not match:
        raise ContractError("Makefile is missing the aggregate validate target")
    aggregate = set(match.group(1).split())
    for target in (
        "validate-ops-visibility",
        "test-ops-visibility",
        "validate-observability-tooling",
        "test-observability-tooling",
        "validate-observability-credentials",
        "test-observability-credentials",
        "validate-observability-log-drain",
        "test-observability-log-drain",
        "validate-qa-contract",
    ):
        if target not in aggregate:
            raise ContractError(f"aggregate validate is missing M24 dependency: {target}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_observability_tooling.py <repository-root>", file=sys.stderr)
        return 2
    root = pathlib.Path(sys.argv[1])
    role_dir = root / "ansible/roles/observability"
    try:
        validate_defaults(load_yaml(role_dir / "defaults/main.yml"))
        validate_task_policy(role_dir)
        validate_playbooks(root)
        validate_makefile(root)
    except (ContractError, OSError) as exc:
        print(f"ERROR observability tooling contract: {exc}", file=sys.stderr)
        return 2
    print("PASS observability tooling contract: pinned Alloy binary slice is source-safe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
