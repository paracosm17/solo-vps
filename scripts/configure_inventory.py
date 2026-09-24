#!/usr/bin/env python3
"""Synchronize persistent Solo VPS inventory connection state from config."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    print("ERROR inventory configuration: PyYAML is required (run: make setup).", file=sys.stderr)
    raise SystemExit(127)

try:
    from scripts.validate_config import ConfigError, validate_config
except ModuleNotFoundError:
    from validate_config import ConfigError, validate_config


class InventoryConfigError(RuntimeError):
    pass


SSH_USER_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*\$?$")


def load_yaml(path: Path, label: str) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InventoryConfigError(f"cannot read {label} {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise InventoryConfigError(f"invalid YAML in {label} {path}: {exc}") from exc


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InventoryConfigError(f"'{path}' must be a YAML mapping")
    return value


def require_user(value: str, label: str) -> str:
    user = value.strip()
    if not user or user != value or not SSH_USER_RE.fullmatch(user):
        raise InventoryConfigError(
            f"{label} must be a simple SSH account name containing only letters, digits, '.', '_', or '-'"
        )
    return user


def atomic_write_yaml(path: Path, data: dict[str, Any]) -> None:
    if path.is_symlink():
        raise InventoryConfigError(f"refusing symlink inventory path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass

    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, sort_keys=False, default_flow_style=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        if tmp.exists():
            tmp.unlink()


def synchronize(config_path: Path, inventory_path: Path, mode: str, explicit_user: str | None) -> tuple[str, str, bool]:
    config = load_yaml(config_path, "config")
    try:
        validate_config(config)
    except ConfigError as exc:
        raise InventoryConfigError(f"config contract: {exc}") from exc
    config_map = require_mapping(config, "config")
    server = require_mapping(config_map.get("server"), "server")
    admin = require_mapping(config_map.get("admin"), "admin")
    host = str(server.get("host", "")).strip()
    if not host:
        raise InventoryConfigError("'server.host' must be configured before inventory synchronization")

    if mode == "admin":
        user = require_user(str(admin.get("user", "")), "admin.user")
        label = "managed admin"
    else:
        if explicit_user is None:
            raise InventoryConfigError("bootstrap SSH user is required")
        user = require_user(explicit_user, "SSH_USER")
        label = "bootstrap/provider"

    inventory = load_yaml(inventory_path, "inventory")
    root = require_mapping(inventory, "inventory")
    all_group = require_mapping(root.get("all"), "all")
    hosts = require_mapping(all_group.get("hosts"), "all.hosts")
    if len(hosts) != 1:
        raise InventoryConfigError(
            f"'all.hosts' must contain exactly one VPS during single-host MVP; found {len(hosts)}"
        )
    inventory_name, raw_vars = next(iter(hosts.items()))
    host_vars = {} if raw_vars is None else require_mapping(raw_vars, f"all.hosts.{inventory_name}")

    changed = host_vars.get("ansible_host") != host or host_vars.get("ansible_user") != user
    if inventory_name == "solo_vps_example":
        inventory_name = "solo_vps"
        changed = True

    host_vars["ansible_host"] = host
    host_vars["ansible_user"] = user
    all_group["hosts"] = {inventory_name: host_vars}
    root["all"] = all_group

    if changed:
        atomic_write_yaml(inventory_path, root)
    else:
        try:
            inventory_path.chmod(0o600)
        except OSError:
            pass

    return host, user, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--admin", action="store_true", help="use config admin.user")
    group.add_argument("--user", help="use an explicit provider/bootstrap SSH account")
    args = parser.parse_args()

    mode = "admin" if args.admin else "bootstrap"
    try:
        host, user, changed = synchronize(
            args.config.expanduser().resolve(),
            args.inventory.expanduser().resolve(),
            mode,
            args.user,
        )
    except (InventoryConfigError, OSError) as exc:
        print(f"ERROR inventory configuration: {exc}", file=sys.stderr)
        return 2

    print(f"PASS inventory connection state: {'managed admin' if mode == 'admin' else 'bootstrap/provider'}")
    print(f"  ansible_host: {host}")
    print(f"  ansible_user: {user}")
    print(f"  persistent inventory changed: {'yes' if changed else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
