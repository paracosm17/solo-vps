#!/usr/bin/env python3
"""Prepare safe first SSH access when Solo VPS is run on the target VPS itself."""

from __future__ import annotations

import argparse
import ipaddress
import os
import pathlib
import pwd
import socket
import subprocess
import sys
from typing import Any

import yaml

SSH_PUBLIC_KEY_PREFIXES = (
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
)


class AccessError(RuntimeError):
    pass


def load_yaml(path: pathlib.Path, label: str) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise AccessError(f"cannot read valid {label} YAML {path}: {exc}") from exc


def extract_inputs(config: Any, inventory: Any) -> tuple[str, str, pathlib.Path, str]:
    try:
        host = str(config["server"]["host"]).strip()
        key_path = pathlib.Path(str(config["admin"]["ssh_public_key_file"])).expanduser()
        human_key = str(config["admin"].get("human_ssh_public_key", "")).strip()
        hosts = inventory["all"]["hosts"]
    except (KeyError, TypeError) as exc:
        raise AccessError("config/inventory shape is incomplete; run make validate-config and review local files") from exc
    if not isinstance(hosts, dict) or len(hosts) != 1:
        raise AccessError("inventory must contain exactly one host")
    _, host_vars = next(iter(hosts.items()))
    if not isinstance(host_vars, dict):
        raise AccessError("inventory host variables must be a mapping")
    ansible_host = str(host_vars.get("ansible_host", "")).strip()
    ansible_user = str(host_vars.get("ansible_user", "")).strip()
    if not host or host != ansible_host or not ansible_user:
        raise AccessError("server.host and inventory ansible_host/ansible_user must be filled and consistent")
    return host, ansible_user, key_path, human_key


def local_addresses() -> set[ipaddress._BaseAddress]:
    addresses: set[ipaddress._BaseAddress] = {
        ipaddress.ip_address("127.0.0.1"),
        ipaddress.ip_address("::1"),
    }
    try:
        result = subprocess.run(
            ["ip", "-o", "addr", "show"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return addresses
    for line in result.stdout.splitlines():
        parts = line.split()
        for index, token in enumerate(parts[:-1]):
            if token not in {"inet", "inet6"}:
                continue
            candidate = parts[index + 1].split("/", 1)[0]
            try:
                addresses.add(ipaddress.ip_address(candidate))
            except ValueError:
                pass
    return addresses


def resolve_host(host: str) -> set[ipaddress._BaseAddress]:
    try:
        return {ipaddress.ip_address(host)}
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise AccessError(f"cannot resolve server.host '{host}': {exc}") from exc
    resolved: set[ipaddress._BaseAddress] = set()
    for info in infos:
        try:
            resolved.add(ipaddress.ip_address(info[4][0]))
        except ValueError:
            pass
    return resolved


def public_key_line(path: pathlib.Path) -> str:
    if not path.is_file():
        raise AccessError(f"configured SSH public key does not exist: {path}; run make ssh-key or make setup")
    content = path.read_text(encoding="utf-8").strip()
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) != 1:
        raise AccessError(f"configured SSH public key must contain exactly one non-empty line: {path}")
    parts = lines[0].split()
    if len(parts) < 2 or parts[0] not in SSH_PUBLIC_KEY_PREFIXES:
        raise AccessError(f"configured SSH public key is not a supported OpenSSH key: {path}")
    return lines[0]


def require_distinct_same_vps_keys(automation_key: str, human_key: str) -> None:
    if automation_key == human_key:
        raise AccessError(
            "same-VPS onboarding requires a distinct human workstation public key; "
            "the VPS-created automation key cannot prove workstation recovery access"
        )


def append_unique(path: pathlib.Path, line: str, mode: int) -> bool:
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    if line in (item.strip() for item in existing):
        os.chmod(path, mode)
        return False
    with path.open("a", encoding="utf-8") as handle:
        if existing and existing[-1].strip():
            handle.write("\n")
        handle.write(line + "\n")
    os.chmod(path, mode)
    return True


def prepare_local_current_user_access(host: str, ansible_user: str, key_path: pathlib.Path) -> str:
    current_user = pwd.getpwuid(os.geteuid()).pw_name
    if ansible_user != current_user:
        raise AccessError(
            f"same-VPS access preparation expects inventory ansible_user '{current_user}'; found '{ansible_user}'"
        )

    key = public_key_line(key_path)
    private_path = pathlib.Path(str(key_path)[:-4]) if str(key_path).endswith(".pub") else None
    if private_path is None or not private_path.is_file():
        raise AccessError(
            "same-VPS access preparation needs the matching private key on this controller; "
            "use the default key created by make setup or configure another usable controller identity"
        )

    account = pwd.getpwnam(ansible_user)
    ssh_dir = pathlib.Path(account.pw_dir) / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    os.chown(ssh_dir, account.pw_uid, account.pw_gid)
    os.chmod(ssh_dir, 0o700)

    authorized_keys = ssh_dir / "authorized_keys"
    changed_auth = append_unique(authorized_keys, key, 0o600)
    os.chown(authorized_keys, account.pw_uid, account.pw_gid)

    host_key_path = pathlib.Path("/etc/ssh/ssh_host_ed25519_key.pub")
    if not host_key_path.is_file():
        raise AccessError(f"local SSH host public key is unavailable: {host_key_path}")
    host_key_parts = host_key_path.read_text(encoding="utf-8").strip().split()
    if len(host_key_parts) < 2:
        raise AccessError(f"local SSH host public key is malformed: {host_key_path}")
    known_line = f"{host} {host_key_parts[0]} {host_key_parts[1]}"
    known_hosts = ssh_dir / "known_hosts"
    changed_known = append_unique(known_hosts, known_line, 0o600)
    os.chown(known_hosts, account.pw_uid, account.pw_gid)

    changes = []
    if changed_auth:
        changes.append(f"authorized controller key for {current_user} SSH")
    if changed_known:
        changes.append("trusted this VPS's local Ed25519 host key")
    return ", ".join(changes) if changes else "already prepared"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare first controller-to-target access without weakening SSH policy.")
    parser.add_argument("--config", required=True, type=pathlib.Path)
    parser.add_argument("--inventory", required=True, type=pathlib.Path)
    args = parser.parse_args()

    try:
        config = load_yaml(args.config, "config")
        inventory = load_yaml(args.inventory, "inventory")
        host, ansible_user, key_path, human_key = extract_inputs(config, inventory)
        target_addresses = resolve_host(host)
        is_local = bool(target_addresses & local_addresses())
        if not human_key:
            raise AccessError(
                "admin.human_ssh_public_key is not configured; install the workstation public key with "
                "the documented human-admin-key helper before bootstrap"
            )
        if "PRIVATE KEY" in human_key or "\n" in human_key or "\r" in human_key:
            raise AccessError("admin.human_ssh_public_key must contain exactly one public OpenSSH key line")
        if not is_local:
            print("PASS access preparation: target is remote from this controller")
            print("  no local authorized_keys or known_hosts files were changed")
            print("  ensure the provider/bootstrap SSH identity is already usable from this controller")
            return 0
        automation_key = public_key_line(key_path)
        require_distinct_same_vps_keys(automation_key, human_key)
        result = prepare_local_current_user_access(host, ansible_user, key_path)
    except (AccessError, OSError, KeyError) as exc:
        print(f"ERROR access preparation: {exc}", file=sys.stderr)
        return 2

    print("PASS access preparation: controller and target are this same VPS")
    print(f"  result: {result}")
    print("  automation_admin_access: PREPARED")
    print("  human_admin_key: CONFIGURED_DISTINCT_WORKSTATION_KEY")
    print("  boundary: this prepares the same-VPS automation identity; the human private key remains on the workstation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
