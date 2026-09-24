#!/usr/bin/env python3
"""Initialize persistent Solo VPS controller state outside the source checkout."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys


class InitError(RuntimeError):
    pass


def _copy_or_keep(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        destination.parent.chmod(0o700)
    except OSError:
        pass

    if destination.exists():
        if not destination.is_file() or destination.is_symlink():
            raise InitError(f"refusing non-regular state path: {destination}")
        return "kept"

    shutil.copyfile(source, destination)
    try:
        destination.chmod(0o600)
    except OSError:
        pass
    return "created"


def _migrate_or_example(legacy: Path, example: Path, destination: Path) -> tuple[str, Path]:
    if destination.exists():
        return _copy_or_keep(example, destination), example
    if legacy.is_file() and not legacy.is_symlink():
        return _copy_or_keep(legacy, destination), legacy
    return _copy_or_keep(example, destination), example


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Solo VPS source checkout")
    parser.add_argument("--data-dir", type=Path, required=True, help="persistent per-user Solo VPS data root")
    parser.add_argument("--config", type=Path, required=True, help="persistent config destination")
    parser.add_argument("--inventory", type=Path, required=True, help="persistent inventory destination")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    data_dir = args.data_dir.expanduser().resolve()
    config = args.config.expanduser().resolve()
    inventory = args.inventory.expanduser().resolve()

    try:
        if _inside(data_dir, root) or _inside(config, root) or _inside(inventory, root):
            raise InitError("persistent state must be outside the Solo VPS source checkout")

        config_example = root / "config/config.example.yml"
        inventory_example = root / "ansible/inventories/example/hosts.yml"
        legacy_config = root / "config/config.yml"
        legacy_inventory = root / "ansible/inventories/local/hosts.yml"
        for path in (config_example, inventory_example):
            if not path.is_file():
                raise InitError(f"missing public source template: {path}")

        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            data_dir.chmod(0o700)
        except OSError:
            pass

        config_status, config_source = _migrate_or_example(legacy_config, config_example, config)
        inventory_status, inventory_source = _migrate_or_example(legacy_inventory, inventory_example, inventory)
    except (InitError, OSError) as exc:
        print(f"ERROR state initialization: {exc}", file=sys.stderr)
        return 2

    print("PASS persistent Solo VPS state initialized")
    print(f"  data: {data_dir}")
    print(f"  config: {config} ({config_status})")
    print(f"  inventory: {inventory} ({inventory_status})")
    if config_source == legacy_config or inventory_source == legacy_inventory:
        print("  migration: copied legacy checkout-local operator state; source files were not deleted")
    print("  source checkout mutated: no")
    print("NEXT: edit config.yml, then run make use-bootstrap SSH_USER=<provider-user> for a fresh VPS, or make use-admin for an already-managed VPS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
