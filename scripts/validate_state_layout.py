#!/usr/bin/env python3
"""Validate the Solo VPS source-tree / persistent-state boundary."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


class StateLayoutError(RuntimeError):
    pass


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        raise StateLayoutError(f"{where} missing required state-boundary contract: {needle}")


def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        raise StateLayoutError(f"{where} still contains checkout-local mutable state: {needle}")


def validate(root: Path) -> None:
    root = root.resolve()
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    init = (root / "scripts/init_local.py").read_text(encoding="utf-8")
    handoff = (root / "scripts/handoff_admin_workspace.py").read_text(encoding="utf-8")
    sops_init = (root / "scripts/init_sops_policy.py").read_text(encoding="utf-8")
    inventory_config = (root / "scripts/configure_inventory.py").read_text(encoding="utf-8")
    docs = (root / "docs/state-layout.md").read_text(encoding="utf-8")

    for needle in (
        "SOLO_VPS_DATA_BASE ?=",
        "$(HOME)/.local/share",
        "SOLO_VPS_DATA_DIR ?=",
        "SOLO_VPS_SECRET_DIR ?= $(SOLO_VPS_DATA_DIR)/secrets",
        "SOLO_VPS_EVIDENCE_DIR ?= $(SOLO_VPS_DATA_DIR)/evidence",
        "SOLO_VPS_STATE_DIR ?= $(SOLO_VPS_DATA_DIR)/state",
        "DATABASE_BACKUP_STATE_DIR ?= $(SOLO_VPS_STATE_DIR)/database-backups",
        "BACKUP_SECRET_FILE ?= $(SOLO_VPS_SECRET_DIR)/backup.enc.yaml",
        "OBSERVABILITY_SECRET_FILE ?= $(SOLO_VPS_SECRET_DIR)/observability.enc.yaml",
        "CONFIG ?= $(SOLO_VPS_CONFIG_DIR)/config.yml",
        "INVENTORY ?= $(SOLO_VPS_CONFIG_DIR)/hosts.yml",
        "QA_VENV ?= $(SOLO_VPS_TOOLCHAIN_DIR)/qa",
        "SOPS_POLICY ?= $(SOLO_VPS_SOPS_DIR)/.sops.yaml",
        "export PYTHONDONTWRITEBYTECODE := 1",
        "paths: ##",
        "run: make init",
        "use-bootstrap: controller-check",
        "use-admin: controller-check",
    ):
        require(makefile, needle, "Makefile")

    for forbidden in (
        "CONFIG ?= config/config.yml",
        "INVENTORY ?= ansible/inventories/local/hosts.yml",
        "QA_VENV ?= .venv/qa",
        "BACKUP_SECRET_FILE ?= secrets/backup.enc.yaml",
        "OBSERVABILITY_SECRET_FILE ?= secrets/observability.enc.yaml",
    ):
        forbid(makefile, forbidden, "Makefile")

    for needle in (
        "persistent state must be outside the Solo VPS source checkout",
        "legacy_config = root / \"config/config.yml\"",
        "legacy_inventory = root / \"ansible/inventories/local/hosts.yml\"",
        "source checkout mutated: no",
    ):
        require(init, needle, "scripts/init_local.py")

    for needle in ("atomic_write_yaml", "--admin", "--user", "ansible_host", "ansible_user"):
        require(inventory_config, needle, "scripts/configure_inventory.py")

    require(handoff, "--state-dir", "scripts/handoff_admin_workspace.py")
    if re.search(r"temporary\s*/\s*INCOMPLETE_MARKER", handoff) or "workspace / COMPLETE_MARKER" in handoff:
        raise StateLayoutError("admin handoff markers must not be written inside the source checkout")

    require(sops_init, "--policy", "scripts/init_sops_policy.py")
    require(sops_init, "--recipient-file", "scripts/init_sops_policy.py")
    forbid(sops_init, 'root / ".sops.yaml"', "scripts/init_sops_policy.py")

    for needle in (
        "state/",
        "database-backups/",
        "small ownership records for Solo VPS-managed Coolify backup schedules",
        "does not store database or S3 credentials there",
    ):
        require(docs, needle, "docs/state-layout.md")

    print("PASS state layout: mutable controller/operator state defaults outside the Git checkout")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate(Path(args.root))
    except (OSError, StateLayoutError) as exc:
        print(f"ERROR state layout: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
