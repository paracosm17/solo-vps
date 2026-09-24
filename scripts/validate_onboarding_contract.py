#!/usr/bin/env python3
"""Validate the guided first-run onboarding contract."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


class ContractError(ValueError):
    pass


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ContractError(f"{label} missing required onboarding contract: {needle}")


def validate(root: Path) -> None:
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    setup = (root / "scripts/controller_setup.sh").read_text(encoding="utf-8")
    key_script = (root / "scripts/ensure_ssh_key.py").read_text(encoding="utf-8")
    access = (root / "scripts/prepare_access.py").read_text(encoding="utf-8")
    handoff = (root / "scripts/handoff_admin_workspace.py").read_text(encoding="utf-8")
    human_key = (root / "scripts/configure_human_admin_key.py").read_text(encoding="utf-8")
    config = (root / "config/config.example.yml").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    quick_starts = [
        (root / path).read_text(encoding="utf-8")
        for path in ("docs/quick-start.md", "docs/quick-start.ru.md")
    ]
    runbook = (root / "docs/clean-vps-test.md").read_text(encoding="utf-8")
    doctor = (root / "scripts/doctor.py").read_text(encoding="utf-8")
    users_assert = (root / "ansible/roles/users/tasks/assert-config.yml").read_text(encoding="utf-8")
    users_load = (root / "ansible/roles/users/tasks/load-public-key.yml").read_text(encoding="utf-8")
    users_main = (root / "ansible/roles/users/tasks/main.yml").read_text(encoding="utf-8")
    users_verify = (root / "ansible/roles/users/tasks/verify.yml").read_text(encoding="utf-8")
    ssh_main = (root / "ansible/roles/ssh/tasks/main.yml").read_text(encoding="utf-8")

    for target in ("setup", "controller-check", "ssh-key", "init", "human-admin-key-file", "human-admin-key-stdin", "use-bootstrap", "use-admin", "prepare-access", "admin-handoff", "apply", "secure", "platform"):
        if not re.search(rf"(?m)^{re.escape(target)}:.*## ", makefile):
            raise ContractError(f"Makefile missing documented onboarding target: {target}")

    require(makefile, "setup: ##", "Makefile")
    require(makefile, "bash $(CONTROLLER_SETUP)", "Makefile setup")
    require(makefile, "$(MAKE) --no-print-directory runtime-tools", "Makefile setup")
    require(makefile, "$(MAKE) --no-print-directory init", "Makefile setup persistent state")
    require(makefile, "qa-tools: controller-check", "Makefile qa-tools")

    for package in ("python3", "python3-yaml", "python3-venv", "openssh-client", "ca-certificates"):
        require(setup, package, "controller setup")
    if "python3.12-venv" in setup:
        raise ContractError("controller setup must use the Ubuntu python3-venv package instead of a patch-version package")
    require(setup, "scripts/ensure_ssh_key.py", "controller setup")

    require(key_script, 'default="~/.ssh/id_ed25519"', "SSH key setup")
    require(key_script, "if not private_exists and not public_exists", "SSH key setup")
    if "rm -f" in key_script or "unlink(" in key_script:
        raise ContractError("SSH key setup must not delete existing key material")

    require(access, 'pathlib.Path("/etc/ssh/ssh_host_ed25519_key.pub")', "same-VPS access preparation")
    require(access, "same-VPS onboarding requires a distinct human workstation public key", "same-VPS access preparation")
    require(access, "admin.human_ssh_public_key is not configured", "same-VPS access preparation")
    require(access, "target is remote from this controller", "same-VPS access preparation")
    if "StrictHostKeyChecking=no" in access or "PasswordAuthentication yes" in access:
        raise ContractError("access preparation must not weaken SSH verification/authentication policy")

    for phrase in (
        'IGNORED_NAMES = {',
        '".venv"',
        'admin_home / "solo-vps"',
        '--state-dir',
        'copy_operator_state(',
        '["make", "setup"]',
        '["make", "prepare-access"]',
        '["make", "doctor"]',
        '"sudo", "-n", "--", sys.executable',
    ):
        require(handoff, phrase, "admin workspace handoff")
    require(makefile, "$(MAKE) --no-print-directory admin-handoff", "ssh-harden handoff")
    handoff_pos = makefile.find("$(MAKE) --no-print-directory admin-handoff")
    harden_run_pos = makefile.find("$(PLAYBOOK_DIR)/ssh-harden.yml -e @$(CONFIG)")
    if not (0 <= handoff_pos < harden_run_pos):
        raise ContractError("same-VPS admin workspace handoff must complete before SSH hardening mutation")
    handoff_steps = [
        handoff.find('["make", "setup"]'),
        handoff.find('["make", "prepare-access"]'),
        handoff.find('["make", "doctor"]'),
    ]
    if any(position < 0 for position in handoff_steps) or handoff_steps != sorted(handoff_steps):
        raise ContractError("admin handoff must run setup -> prepare-access -> doctor before finalization")
    if '["make", "validate"]' in handoff:
        raise ContractError("admin handoff must not require the developer source test suite")
    if "copytree(source, temporary" not in handoff:
        raise ContractError("admin handoff must copy source into an admin-owned workspace before rebuilding tools")
    require(
        handoff,
        "ensure_admin_data_parents(admin_home, account.pw_uid, account.pw_gid)",
        "admin workspace handoff XDG ownership",
    )
    require(handoff, "source checkout state: none generated", "admin workspace handoff")
    if "workspace / COMPLETE_MARKER" in handoff or "temporary / INCOMPLETE_MARKER" in handoff:
        raise ContractError("admin handoff markers must stay outside the source checkout")

    for phrase in ("--stdin", "--public-key-file", "private_key_received: false", "os.replace", "human_ssh_public_key"):
        require(human_key, phrase, "human workstation key helper")
    require(makefile, "HUMAN_ADMIN_KEY_CONFIGURE := scripts/configure_human_admin_key.py", "Makefile human key helper")
    require(makefile, "SSH_HARDENING_ADMIN_LOGIN_CONFIRM_REQUIRED := I_HAVE_VERIFIED_WORKSTATION_ADMIN_LOGIN", "SSH hardening workstation gate")
    require(makefile, "SSH_HARDENING_ADMIN_LOGIN_CONFIRM=$(SSH_HARDENING_ADMIN_LOGIN_CONFIRM_REQUIRED)", "SSH hardening workstation gate")

    require(config, "timezone: UTC", "public config example")
    require(config, "human_ssh_public_key", "public config example")
    for text, label in ((users_assert, "users config gate"), (users_load, "users key loader"), (users_main, "users key apply"), (users_verify, "users key verify")):
        require(text, "human_ssh_public_key" if text is users_assert else "solo_vps_human_admin_authorized_key", label)
    require(users_main, "solo_vps_admin_authorized_key", "users automation key apply")
    require(users_verify, "solo_vps_admin_authorized_key", "users automation key verify")
    require(ssh_main, "solo_vps_ssh_human_login_confirm == solo_vps_ssh_human_login_confirm_required", "SSH role workstation-login gate")
    if re.search(r"(?m)^\s*timezone:\s*Europe/", config):
        raise ContractError("public config example must default to UTC")

    readme_quick = readme[readme.index("## Quick Start"):]
    for command in ("make setup", "make apply", "make secure", "make platform", "make verify"):
        require(readme_quick, command, "README")
    positions = [readme_quick.index(command) for command in ("make setup", "make apply", "make secure", "make platform", "make verify")]
    if positions != sorted(positions):
        raise ContractError("README must order setup -> apply -> secure -> platform -> verify")
    for page in ("docs/quick-start.md", "docs/operations/first-app.md"):
        require(readme_quick, page, "README runbook links")
    # Detailed commands live in the canonical runbook, not a second README copy.
    for quick in quick_starts:
        ordered = (
            "make setup", "make human-admin-key-stdin", "make apply",
            "sudo -n id -u", "make secure", "make platform", "make verify", "Skip Setup",
        )
        for command in ordered:
            require(quick, command, "EN/RU Quick Start")
        if [quick.index(command) for command in ordered] != sorted(quick.index(command) for command in ordered):
            raise ContractError("Quick Start must verify admin login before hardening, then install and register Coolify")
        for phrase in ("UTC", "~/.local/share/solo-vps", "config.yml", "private_key_received: false", "~/solo-vps", "operations/first-app.md"):
            require(quick, phrase, "EN/RU Quick Start")

    clean_runbook = runbook[runbook.index("## Phase 0"):]
    for command in ("make setup", "make validate", "make init", "make human-admin-key-stdin", "make use-bootstrap", "make use-admin", "make prepare-access", "make doctor"):
        require(clean_runbook, command, "clean-VPS runbook")
    positions = [clean_runbook.index(command) for command in ("make setup", "make init", "make prepare-access", "make doctor")]
    if positions != sorted(positions):
        raise ContractError("clean-VPS runbook must order setup -> init -> prepare-access -> doctor")
    for phrase in ("UTC", "~/.local/share/solo-vps", "make qa-static", "config.yml"):
        require(clean_runbook, phrase, "clean-VPS runbook")

    require(runbook, "make admin-handoff", "clean-VPS admin handoff")
    require(runbook, "~/solo-vps", "clean-VPS admin workspace")
    require(doctor, "Run `make ssh-key`", "doctor remediation")
    require(doctor, "human_admin_key: CONFIGURED", "doctor human-key status")
    print("PASS onboarding contract: explicit workstation human key + separate same-VPS automation identity + hardening gate + guided command order are consistent")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate(Path(args.root).resolve())
    except (OSError, ContractError) as exc:
        print(f"ERROR onboarding contract: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
