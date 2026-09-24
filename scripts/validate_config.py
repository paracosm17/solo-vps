#!/usr/bin/env python3
"""Validate the minimal public Solo VPS configuration contract."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    print(
        "ERROR config contract: PyYAML is required (Python module 'yaml').",
        file=sys.stderr,
    )
    raise SystemExit(127)


ADMIN_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
HOSTNAME_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
TIMEZONE_RE = re.compile(r"^[A-Za-z0-9_+.-]+(?:/[A-Za-z0-9_+.-]+)*$")
SUPPORTED_PUBLIC_PORTS = {80, 443}
BACKUP_CREDENTIAL_KEY_RE = re.compile(r"(?:password|secret|token|credential|access[_-]?key)", re.I)
SSH_PUBLIC_KEY_RE = re.compile(
    r"^(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com)[ \t]+[A-Za-z0-9+/=]+(?:[ \t]+.*)?$"
)


class ConfigError(ValueError):
    """Raised when the public config violates the current contract."""


def require_mapping(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"'{key}' must be a YAML mapping")
    return value


def require_string(parent: dict[str, Any], key: str, path: str) -> str:
    if key not in parent:
        raise ConfigError(f"missing required value '{path}'")

    value = parent[key]
    if not isinstance(value, str):
        raise ConfigError(f"'{path}' must be a string")

    normalized = value.strip()
    if not normalized:
        raise ConfigError(f"'{path}' must not be empty")
    if normalized != value:
        raise ConfigError(f"'{path}' must not contain leading or trailing whitespace")
    if "CHANGE_ME" in normalized.upper():
        raise ConfigError(f"'{path}' still contains a CHANGE_ME placeholder")

    return normalized


def reject_backup_credential_keys(value: Any, path: str = "backup") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if BACKUP_CREDENTIAL_KEY_RE.search(str(key)):
                raise ConfigError(
                    f"'{path}.{key}' looks like backup credential material; public config is metadata-only"
                )
            reject_backup_credential_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_backup_credential_keys(child, f"{path}[{index}]")


def validate_config(data: Any) -> None:
    if not isinstance(data, dict):
        raise ConfigError("top-level YAML value must be a mapping")

    server = require_mapping(data, "server")
    admin = require_mapping(data, "admin")
    firewall = require_mapping(data, "firewall")
    if "evaluation" in data:
        evaluation = data["evaluation"]
        if not isinstance(evaluation, dict):
            raise ConfigError("'evaluation' must be a YAML mapping when present")
        if set(evaluation) != {"allow_small_vps"} or type(evaluation["allow_small_vps"]) is not bool:
            raise ConfigError(
                "'evaluation.allow_small_vps' must be an explicit boolean and the only evaluation setting"
            )

    if "backup" in data:
        backup = data["backup"]
        if not isinstance(backup, dict):
            raise ConfigError("'backup' must be a YAML mapping when present")
        reject_backup_credential_keys(backup)

    if "ci_deploy" in data:
        ci_deploy = data["ci_deploy"]
        if not isinstance(ci_deploy, dict):
            raise ConfigError("'ci_deploy' must be a YAML mapping when present")
        ci_key_file = require_string(
            ci_deploy, "ssh_public_key_file", "ci_deploy.ssh_public_key_file"
        )
        if not (ci_key_file.startswith("/") or ci_key_file.startswith("~/")):
            raise ConfigError(
                "'ci_deploy.ssh_public_key_file' must be an absolute controller path "
                "or start with '~/'; never place a private key in public config"
            )

    host = require_string(server, "host", "server.host")
    hostname = require_string(server, "hostname", "server.hostname")
    timezone = require_string(server, "timezone", "server.timezone")
    admin_user = require_string(admin, "user", "admin.user")
    ssh_public_key_file = require_string(
        admin, "ssh_public_key_file", "admin.ssh_public_key_file"
    )
    human_ssh_public_key = admin.get("human_ssh_public_key", "")
    if not isinstance(human_ssh_public_key, str):
        raise ConfigError("'admin.human_ssh_public_key' must be a string")
    if human_ssh_public_key != human_ssh_public_key.strip():
        raise ConfigError("'admin.human_ssh_public_key' must not contain leading/trailing whitespace")
    if "PRIVATE KEY" in human_ssh_public_key:
        raise ConfigError("'admin.human_ssh_public_key' must contain only a public key")
    if "\n" in human_ssh_public_key or "\r" in human_ssh_public_key:
        raise ConfigError("'admin.human_ssh_public_key' must contain exactly one public-key line")
    if human_ssh_public_key and not SSH_PUBLIC_KEY_RE.fullmatch(human_ssh_public_key):
        raise ConfigError("'admin.human_ssh_public_key' is not a supported OpenSSH public key")

    if "public_ports" not in firewall:
        raise ConfigError("missing required value 'firewall.public_ports'")
    public_ports = firewall["public_ports"]
    if not isinstance(public_ports, list):
        raise ConfigError("'firewall.public_ports' must be a YAML list")
    if any(type(port) is not int for port in public_ports):
        raise ConfigError("'firewall.public_ports' entries must be integer TCP ports")
    if len(public_ports) != len(set(public_ports)):
        raise ConfigError("'firewall.public_ports' must not contain duplicates")
    unsupported_ports = sorted(set(public_ports) - SUPPORTED_PUBLIC_PORTS)
    if unsupported_ports:
        raise ConfigError(
            "'firewall.public_ports' currently supports only TCP ports 80 and 443; "
            f"unsupported: {unsupported_ports}"
        )

    if any(char.isspace() for char in host):
        raise ConfigError("'server.host' must not contain whitespace")

    if len(hostname) > 253 or any(
        not HOSTNAME_LABEL_RE.fullmatch(label) for label in hostname.split(".")
    ):
        raise ConfigError(
            "'server.hostname' must be a lowercase DNS-style hostname "
            "with labels up to 63 characters"
        )

    timezone_parts = timezone.split("/")
    if (
        not TIMEZONE_RE.fullmatch(timezone)
        or timezone.startswith("/")
        or any(part in {".", ".."} for part in timezone_parts)
    ):
        raise ConfigError(
            "'server.timezone' must be a safe zoneinfo name such as 'UTC' "
            "or 'Europe/Riga'"
        )

    if not ADMIN_USER_RE.fullmatch(admin_user):
        raise ConfigError(
            "'admin.user' must use a Linux-style lowercase account name "
            "(letters, digits, '_' or '-', max 32 characters)"
        )

    if admin_user == "root":
        raise ConfigError("'admin.user' must name a non-root administrative account")

    if not (ssh_public_key_file.startswith("/") or ssh_public_key_file.startswith("~/")):
        raise ConfigError(
            "'admin.ssh_public_key_file' must be an absolute controller path "
            "or start with '~/'; relative paths are ambiguous in Ansible lookups"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the current Solo VPS non-secret configuration contract."
    )
    parser.add_argument("config", type=pathlib.Path, help="Path to a YAML config file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        raw = args.config.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR config contract: cannot read {args.config}: {exc}", file=sys.stderr)
        return 2

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        print(f"ERROR config contract: invalid YAML in {args.config}: {exc}", file=sys.stderr)
        return 2

    try:
        validate_config(data)
    except ConfigError as exc:
        print(f"ERROR config contract: {exc}", file=sys.stderr)
        return 2

    print(f"PASS config contract: {args.config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
