#!/usr/bin/env python3
"""Run mutation-free local diagnostics for the Solo VPS controller contract."""

from __future__ import annotations

import argparse
import ipaddress
import pathlib
import shutil
import sys
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    print("ERROR doctor: PyYAML is required (Python module 'yaml').", file=sys.stderr)
    raise SystemExit(127)

from validate_config import ConfigError, validate_config


DOCUMENTATION_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
)
SSH_PUBLIC_KEY_PREFIXES = (
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
)


class DoctorError(ValueError):
    """Raised when local controller/access prerequisites are not satisfied."""


def load_yaml(path: pathlib.Path, label: str) -> Any:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DoctorError(f"cannot read {label} {path}: {exc}") from exc

    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise DoctorError(f"invalid YAML in {label} {path}: {exc}") from exc


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DoctorError(f"'{path}' must be a YAML mapping")
    return value


def require_nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DoctorError(f"'{path}' must be a non-empty string")
    if value != value.strip():
        raise DoctorError(f"'{path}' must not contain leading or trailing whitespace")
    return value


def check_command(command: str, label: str) -> str:
    candidate = pathlib.Path(command).expanduser()
    if candidate.parent != pathlib.Path(".") or "/" in command:
        if candidate.is_file() and candidate.exists():
            return str(candidate)
        raise DoctorError(f"required {label} command not found: {command}")

    resolved = shutil.which(command)
    if resolved is None:
        raise DoctorError(f"required {label} command not found in PATH: {command}")
    return resolved


def check_documentation_host(host: str) -> None:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return

    if any(address in network for network in DOCUMENTATION_NETWORKS):
        raise DoctorError(
            f"server.host '{host}' is a documentation-only TEST-NET address; "
            "replace the example value before contacting a real VPS"
        )


def validate_public_key(path_value: str) -> pathlib.Path:
    path = pathlib.Path(path_value).expanduser()
    if not path.is_file():
        raise DoctorError(
            f"SSH public key file does not exist or is not a file: {path}. "
            "Run `make ssh-key` (or the full first-run `make setup`) for the default key, "
            "or point admin.ssh_public_key_file at an existing public key."
        )

    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise DoctorError(f"cannot read SSH public key file {path}: {exc}") from exc

    if "PRIVATE KEY" in content:
        raise DoctorError(f"SSH key path points to private-key material, not a public key: {path}")

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) != 1:
        raise DoctorError(
            f"SSH public key file must contain exactly one non-empty public-key line: {path}"
        )

    parts = lines[0].split()
    if len(parts) < 2 or parts[0] not in SSH_PUBLIC_KEY_PREFIXES:
        raise DoctorError(
            f"SSH public key file does not look like a supported OpenSSH public key: {path}"
        )

    return path



def validate_public_key_line(value: str, path: str) -> str:
    if "PRIVATE KEY" in value:
        raise DoctorError(f"{path} contains private-key material; provide only the public key")
    if "\n" in value or "\r" in value:
        raise DoctorError(f"{path} must contain exactly one public-key line")
    parts = value.split()
    if len(parts) < 2 or parts[0] not in SSH_PUBLIC_KEY_PREFIXES:
        raise DoctorError(f"{path} is not a supported OpenSSH public key")
    return value

def validate_inventory(data: Any, configured_host: str) -> tuple[str, str, str]:
    root = require_mapping(data, "inventory")
    all_group = require_mapping(root.get("all"), "all")
    hosts = require_mapping(all_group.get("hosts"), "all.hosts")

    if len(hosts) != 1:
        raise DoctorError(
            f"'all.hosts' must contain exactly one VPS during single-host MVP; found {len(hosts)}"
        )

    inventory_name, raw_vars = next(iter(hosts.items()))
    host_vars = {} if raw_vars is None else require_mapping(raw_vars, f"all.hosts.{inventory_name}")
    ansible_host = require_nonempty_string(
        host_vars.get("ansible_host"), f"all.hosts.{inventory_name}.ansible_host"
    )
    ansible_user = require_nonempty_string(
        host_vars.get("ansible_user"), f"all.hosts.{inventory_name}.ansible_user"
    )

    if ansible_host != configured_host:
        raise DoctorError(
            "inventory ansible_host does not match server.host: "
            f"'{ansible_host}' != '{configured_host}'"
        )

    check_documentation_host(ansible_host)
    return inventory_name, ansible_host, ansible_user


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local Solo VPS doctor checks without SSH.")
    parser.add_argument("--config", required=True, type=pathlib.Path)
    parser.add_argument("--inventory", required=True, type=pathlib.Path)
    parser.add_argument("--ansible-playbook", default="ansible-playbook")
    parser.add_argument("--ssh", default="ssh")
    parser.add_argument(
        "--require-admin-inventory-user",
        action="store_true",
        help=(
            "Require inventory ansible_user to equal config admin.user; "
            "used by workflows that must connect as the managed administrator."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        config = load_yaml(args.config, "config")
        try:
            validate_config(config)
        except ConfigError as exc:
            raise DoctorError(f"config contract: {exc}") from exc

        config_map = require_mapping(config, "config")
        server = require_mapping(config_map.get("server"), "server")
        admin = require_mapping(config_map.get("admin"), "admin")
        configured_host = require_nonempty_string(server.get("host"), "server.host")
        key_value = require_nonempty_string(
            admin.get("ssh_public_key_file"), "admin.ssh_public_key_file"
        )
        admin_user = require_nonempty_string(admin.get("user"), "admin.user")
        human_key = validate_public_key_line(
            require_nonempty_string(admin.get("human_ssh_public_key"), "admin.human_ssh_public_key"),
            "admin.human_ssh_public_key",
        )

        ansible_path = check_command(args.ansible_playbook, "ansible-playbook")
        ssh_path = check_command(args.ssh, "ssh")
        public_key_path = validate_public_key(key_value)
        inventory = load_yaml(args.inventory, "inventory")
        inventory_name, ansible_host, ansible_user = validate_inventory(inventory, configured_host)
        if args.require_admin_inventory_user and ansible_user != admin_user:
            raise DoctorError(
                "this workflow requires the local inventory to connect as the managed admin: "
                f"ansible_user '{ansible_user}' != admin.user '{admin_user}'"
            )
    except DoctorError as exc:
        print(f"ERROR doctor: {exc}", file=sys.stderr)
        return 2

    print("PASS doctor local controller contract")
    print(f"  python: {sys.executable} ({sys.version.split()[0]})")
    print(f"  ansible-playbook: {ansible_path}")
    print(f"  ssh: {ssh_path}")
    print(f"  automation_public_key: {public_key_path}")
    print("  human_admin_key: CONFIGURED")
    print("  human_private_key_on_vps: NOT_REQUIRED")
    print(f"  inventory_host: {inventory_name}")
    print(f"  ansible_host: {ansible_host}")
    print(f"  ansible_user: {ansible_user}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
