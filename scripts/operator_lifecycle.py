#!/usr/bin/env python3
"""Small resumable operator lifecycle wrappers for the normal Solo VPS path."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Sequence

try:
    import yaml
except ModuleNotFoundError:
    print("ERROR operator lifecycle: PyYAML is required (run: make setup).", file=sys.stderr)
    raise SystemExit(127)

try:
    from scripts.configure_inventory import InventoryConfigError, synchronize
except ModuleNotFoundError:
    from configure_inventory import InventoryConfigError, synchronize


class LifecycleError(RuntimeError):
    pass


RunStep = Callable[[Sequence[str]], None]


def load_mapping(path: Path, label: str) -> dict:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LifecycleError(f"cannot read {label} {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise LifecycleError(f"invalid YAML in {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LifecycleError(f"{label} must be a YAML mapping")
    return value


def configured_admin(config_path: Path) -> str:
    data = load_mapping(config_path, "config")
    admin = data.get("admin")
    if not isinstance(admin, dict) or not isinstance(admin.get("user"), str) or not admin["user"].strip():
        raise LifecycleError("config admin.user must be configured")
    return admin["user"].strip()


def inventory_user(inventory_path: Path) -> str:
    data = load_mapping(inventory_path, "inventory")
    try:
        hosts = data["all"]["hosts"]
    except (KeyError, TypeError) as exc:
        raise LifecycleError("inventory must contain all.hosts") from exc
    if not isinstance(hosts, dict) or len(hosts) != 1:
        raise LifecycleError("inventory must contain exactly one host")
    raw = next(iter(hosts.values()))
    if not isinstance(raw, dict):
        raise LifecycleError("inventory host variables must be a mapping")
    user = raw.get("ansible_user")
    if not isinstance(user, str) or not user.strip():
        raise LifecycleError("inventory ansible_user must be configured")
    return user.strip()


def choose_bootstrap_user(current_user: str, admin_user: str, requested: str | None) -> str | None:
    if current_user == admin_user:
        return None
    if requested is not None and requested.strip():
        return requested.strip()
    return current_user


def default_runner(root: Path) -> RunStep:
    def run(argv: Sequence[str]) -> None:
        try:
            subprocess.run(list(argv), cwd=root, check=True, env=os.environ.copy())
        except (OSError, subprocess.CalledProcessError) as exc:
            raise LifecycleError(f"lifecycle step failed: {' '.join(argv)}") from exc

    return run


def apply_host(
    root: Path,
    config_path: Path,
    inventory_path: Path,
    bootstrap_user: str | None,
    run_step: RunStep | None = None,
) -> None:
    root = root.resolve()
    config_path = config_path.expanduser().resolve()
    inventory_path = inventory_path.expanduser().resolve()
    admin_user = configured_admin(config_path)
    current_user = inventory_user(inventory_path)
    selected_bootstrap = choose_bootstrap_user(current_user, admin_user, bootstrap_user)
    runner = run_step or default_runner(root)

    if selected_bootstrap is not None:
        try:
            host, user, changed = synchronize(
                config_path,
                inventory_path,
                "bootstrap",
                selected_bootstrap,
            )
        except InventoryConfigError as exc:
            raise LifecycleError(f"cannot prepare bootstrap inventory: {exc}") from exc
        print("==> Stage 1/3: bootstrap/provider access")
        print(f"    target: {host}")
        print(f"    ssh user: {user}")
        print(f"    inventory changed: {'yes' if changed else 'no'}")
    else:
        print("==> Stage 1/3: managed-admin inventory already active; bootstrap identity switch skipped")
        # Resume using the proven admin connection, including from a retained
        # provider session. Never re-authorize a different local account or
        # silently fall back to root after SSH hardening.
        try:
            synchronize(config_path, inventory_path, "admin", None)
        except InventoryConfigError as exc:
            raise LifecycleError(f"cannot synchronize managed inventory: {exc}") from exc

    targets = ("prepare-access", "doctor", "bootstrap") if selected_bootstrap is not None else ("doctor", "bootstrap")
    for target in targets:
        print(f"==> Running: make {target}")
        runner(("make", "--no-print-directory", target, f"CONFIG={config_path}", f"INVENTORY={inventory_path}"))

    try:
        host, user, changed = synchronize(config_path, inventory_path, "admin", None)
    except InventoryConfigError as exc:
        raise LifecycleError(f"cannot switch inventory to managed admin: {exc}") from exc
    print("==> Stage 2/3: managed administrator")
    print(f"    target: {host}")
    print(f"    ssh user: {user}")
    print(f"    inventory changed: {'yes' if changed else 'no'}")

    for target in ("doctor", "admin-handoff", "verify", "audit"):
        print(f"==> Running: make {target}")
        runner(("make", "--no-print-directory", target, f"CONFIG={config_path}", f"INVENTORY={inventory_path}"))

    print("==> Stage 3/3: host baseline complete")
    print("PASS Solo VPS host apply")
    print("NEXT: prove a fresh workstation login as admin.user and provider recovery access, then run make secure with both confirmations.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    apply_parser = subparsers.add_parser("apply", help="apply/resume the host baseline and switch inventory to admin.user")
    apply_parser.add_argument("--root", type=Path, default=Path.cwd())
    apply_parser.add_argument("--config", type=Path, required=True)
    apply_parser.add_argument("--inventory", type=Path, required=True)
    apply_parser.add_argument("--bootstrap-user", default="")
    args = parser.parse_args()

    try:
        if args.command == "apply":
            apply_host(
                args.root,
                args.config,
                args.inventory,
                args.bootstrap_user or None,
            )
    except (LifecycleError, OSError) as exc:
        print(f"ERROR operator lifecycle: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
