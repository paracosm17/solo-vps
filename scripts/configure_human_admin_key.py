#!/usr/bin/env python3
"""Configure the human workstation SSH public key in persistent Solo VPS config."""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import tempfile
from typing import Any

import yaml

SUPPORTED_PREFIXES = (
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
)
MAX_PUBLIC_KEY_BYTES = 16384


class HumanKeyError(ValueError):
    pass


def validate_public_key(raw: str) -> str:
    if len(raw.encode("utf-8")) > MAX_PUBLIC_KEY_BYTES:
        raise HumanKeyError("SSH public key input is unexpectedly large")
    if "PRIVATE KEY" in raw:
        raise HumanKeyError("refusing private-key material; provide only the workstation .pub key")
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) != 1:
        raise HumanKeyError("expected exactly one non-empty OpenSSH public-key line")
    parts = lines[0].split()
    if len(parts) < 2 or parts[0] not in SUPPORTED_PREFIXES:
        raise HumanKeyError("unsupported or malformed OpenSSH public key")
    return lines[0]


def load_config(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise HumanKeyError(f"cannot read valid config YAML {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("admin"), dict):
        raise HumanKeyError("config must contain an admin mapping; run make init and edit config.yml first")
    return data


def write_config_atomic(path: pathlib.Path, data: dict[str, Any]) -> None:
    try:
        current_mode = path.stat().st_mode & 0o777
    except OSError as exc:
        raise HumanKeyError(f"cannot stat config {path}: {exc}") from exc
    rendered = yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = pathlib.Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, current_mode or 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def configure(config_path: pathlib.Path, raw_key: str) -> str:
    key = validate_public_key(raw_key)
    data = load_config(config_path)
    admin = data["admin"]
    previous = admin.get("human_ssh_public_key")
    if previous == key:
        return "already-configured"
    admin["human_ssh_public_key"] = key
    write_config_atomic(config_path, data)
    return "configured"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=pathlib.Path)
    parser.add_argument("--public-key-file", type=pathlib.Path)
    parser.add_argument("--stdin", action="store_true")
    args = parser.parse_args()
    if bool(args.public_key_file) == bool(args.stdin):
        parser.error("choose exactly one of --public-key-file or --stdin")
    return args


def main() -> int:
    args = parse_args()
    try:
        if args.stdin:
            raw = sys.stdin.read(MAX_PUBLIC_KEY_BYTES + 1)
        else:
            raw = args.public_key_file.expanduser().read_text(encoding="utf-8")
        result = configure(args.config.expanduser().resolve(), raw)
    except (OSError, HumanKeyError) as exc:
        print(f"ERROR human admin key: {exc}", file=sys.stderr)
        return 2

    print("PASS human admin workstation key configuration")
    print(f"  human_admin_key: {result}")
    print("  private_key_received: false")
    print("  next: run make doctor, then make bootstrap to authorize the key")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
