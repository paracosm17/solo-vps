#!/usr/bin/env python3
"""Validate the CRIT-006/CRIT-007 primary operator command surface."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess


class ContractError(ValueError):
    pass


PRIMARY_PATH = ("setup", "apply", "secure", "platform", "verify")
DEFAULT_REQUIRED = (
    "setup",
    "doctor",
    "apply",
    "bootstrap",
    "secure",
    "platform",
    "verify",
    "backup",
    "recover",
    "update",
    "help-ops",
    "help-dev",
    "help-all",
)


def run_help(root: Path, target: str) -> str:
    result = subprocess.run(
        ["make", "--no-print-directory", "-s", target],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise ContractError(f"make {target} failed during contract validation: {result.stderr.strip()}")
    return result.stdout


def validate(root: Path) -> None:
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    runbook = (root / "docs/quick-start.md").read_text(encoding="utf-8")
    lifecycle = (root / "scripts/operator_lifecycle.py").read_text(encoding="utf-8")

    for target in (*DEFAULT_REQUIRED, "help"):
        if not re.search(rf"(?m)^{re.escape(target)}:", makefile):
            raise ContractError(f"Makefile missing operator target: {target}")

    if "$(MAKE) --no-print-directory init" not in makefile:
        raise ContractError("make setup must initialize persistent state idempotently")
    if "$(OPERATOR_LIFECYCLE) apply" not in makefile:
        raise ContractError("make apply must use the resumable operator lifecycle helper")
    if "secure: check-local-files check-ssh-hardening-confirm" not in makefile:
        raise ContractError("make secure must retain the existing dual SSH hardening confirmation gate")
    for needle in (
        "$(MAKE) --no-print-directory ssh-harden",
        "$(MAKE) --no-print-directory verify-ssh",
        "$(MAKE) --no-print-directory coolify",
        "$(MAKE) --no-print-directory verify-coolify",
        "$(MAKE) --no-print-directory backup-now",
        "$(MAKE) --no-print-directory backup-check",
    ):
        if needle not in makefile:
            raise ContractError(f"operator wrapper missing required lower-level stage: {needle}")
    platform_body = makefile.split("\nplatform:", 1)[1].split("\nbackup:", 1)[0]
    if "coolify-readiness" in platform_body:
        raise ContractError("platform must let the Coolify playbook select first-install readiness by state")
    recover_body = makefile.split("recover:", 1)[1].split("\nupdate:", 1)[0]
    if "$(ANSIBLE_PLAYBOOK)" in recover_body or "coolify-instance-restore-apply" in recover_body or "backup-restore-staging" in recover_body:
        raise ContractError("make recover must remain a non-mutating recovery entry point")
    for stage in ("prepare-access", "doctor", "bootstrap", "verify", "audit"):
        if f'"{stage}"' not in lifecycle:
            raise ContractError(f"operator lifecycle missing apply stage: {stage}")
    if "synchronize(config_path, inventory_path, \"admin\", None)" not in lifecycle:
        raise ContractError("operator lifecycle must switch inventory to managed admin after bootstrap")
    if "from configure_inventory import InventoryConfigError, synchronize" not in lifecycle:
        raise ContractError("operator lifecycle must support direct scripts/operator_lifecycle.py execution from the repository root")

    help_text = run_help(root, "help")
    command_lines = [line for line in help_text.splitlines() if line.startswith("  make ")]
    if not (10 <= len(command_lines) <= 15):
        raise ContractError(f"default make help must expose 10-15 commands; found {len(command_lines)}")
    for target in DEFAULT_REQUIRED:
        if f"make {target}" not in help_text:
            raise ContractError(f"default make help missing required operator command: {target}")
    for forbidden in ("validate-observability", "test-public-product", "check-ssh-hardening", "database-backup-configure"):
        if forbidden in help_text:
            raise ContractError(f"default make help leaks internal/advanced target: {forbidden}")

    all_help = run_help(root, "help-all")
    if "validate-observability-runtime" not in all_help or "test-public-product-hygiene" not in all_help:
        raise ContractError("help-all must keep internal validators/tests discoverable")
    dev_help = run_help(root, "help-dev")
    if "ci-fast-source" not in dev_help or "qa-static" not in dev_help or "validate" not in dev_help:
        raise ContractError("help-dev must expose the supported developer validation surface")
    ops_help = run_help(root, "help-ops")
    if "ops-status" not in ops_help or "backup-status" not in ops_help or "audit" not in ops_help:
        raise ContractError("help-ops must expose operational diagnostics")

    quick_start = readme.split("## Quick Start", 1)[1].split("## Safety boundaries", 1)[0]
    make_commands = re.findall(r"(?m)(?:^|[|&;]\s*)make\s+([A-Za-z0-9_.-]+)", quick_start)
    intentional = [name for name in make_commands if name != "human-admin-key-stdin"]
    if len(intentional) > 8:
        raise ContractError(f"Quick Start exceeds eight intentional primary make commands: {intentional}")
    for target in PRIMARY_PATH:
        if target not in quick_start:
            raise ContractError(f"Quick Start missing primary lifecycle command: make {target}")
    positions = [quick_start.index(f"make {target}") for target in PRIMARY_PATH]
    if positions != sorted(positions):
        raise ContractError("Quick Start primary path must order setup -> apply -> secure -> platform -> verify")
    explicit_edit_commands = re.findall(r"(?m)^\s*(?:nano|vim|vi)\s+\S+", runbook)
    if len(explicit_edit_commands) != 1:
        raise ContractError(
            f"Quick Start must require exactly one explicit config edit; found {explicit_edit_commands}"
        )
    if "authorized_keys" in runbook and "do not edit" not in runbook:
        raise ContractError("Quick Start must not require manual authorized_keys surgery")

    print("PASS operator surface: five-command lifecycle + bounded help tiers are consistent")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate(Path(args.root).resolve())
    except (OSError, ContractError) as exc:
        print(f"ERROR operator surface: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
