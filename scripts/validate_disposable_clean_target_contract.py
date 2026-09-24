#!/usr/bin/env python3
"""Validate the CRIT-004 provider-neutral disposable clean-target harness contract."""

from __future__ import annotations

from pathlib import Path
import re
import sys


class ContractError(RuntimeError):
    pass


SCRIPT = Path("scripts/prove_disposable_clean_target.py")
DOC = Path("docs/disposable-clean-target.md")
TESTING = Path("docs/testing.md")
RELEASE = Path("docs/release-process.md")
STATE = Path("docs/state-layout.md")
MAKEFILE = Path("Makefile")


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        raise ContractError(f"{where} missing required disposable-target contract: {needle}")


def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        raise ContractError(f"{where} contains forbidden disposable-target behavior: {needle}")


def target_body(makefile: str, target: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(target)}:[^\n]*\n((?:\t.*\n|\n)*)", makefile)
    if not match:
        raise ContractError(f"Makefile target is missing: {target}")
    return match.group(0)


def validate(root: Path) -> None:
    script = (root / SCRIPT).read_text(encoding="utf-8")
    makefile = (root / MAKEFILE).read_text(encoding="utf-8")
    doc = (root / DOC).read_text(encoding="utf-8")
    testing = (root / TESTING).read_text(encoding="utf-8")
    release = (root / RELEASE).read_text(encoding="utf-8")
    state = (root / STATE).read_text(encoding="utf-8")

    for needle in (
        'CONFIRMATION = "I_HAVE_REVIEWED_THE_DISPOSABLE_CLEAN_TARGET"',
        'PROVIDER_RECOVERY_CONFIRMATION = "I_HAVE_VERIFIED_DISPOSABLE_PROVIDER_RECOVERY"',
        'MARKER_PATH = "/root/.solo-vps-disposable-clean-target"',
        "refuse_production_or_local_target(args.target)",
        'facts.get("OS_ID") != "ubuntu"',
        'facts.get("OS_VERSION") != "24.04"',
        'facts.get("OS_CODENAME") != "noble"',
        "DIRTY=docker-command",
        "DIRTY=coolify-marker",
        "DIRTY=managed-admin-exists",
        "StrictHostKeyChecking=yes",
        "host-key fingerprint",
        "TemporaryDirectory",
        "generated_private_keys_retained",
        "raw_command_logs_retained",
        '"production_config_reused": False',
        "fresh exact human-key admin login before hardening",
        "proof-gated SSH hardening",
        "fresh exact human-key admin login after hardening",
        "direct root SSH is denied after hardening",
        "idempotency bootstrap rerun",
        "second_recap[\"changed\"] != 0",
        '"coolify_installation": "NOT_RUN"',
        '"backup_restore": "NOT_RUN"',
        '"provider_resource_destroyed_by_harness": False',
        '"operator_must_destroy_target_after_evidence": True',
    ):
        require(script, needle, str(SCRIPT))

    for forbidden in (
        "StrictHostKeyChecking=no",
        "ANSIBLE_HOST_KEY_CHECKING",
        "terraform",
        "cloudflare_api_token",
        "hcloud",
        "doctl",
        "aws ec2 terminate",
    ):
        forbid(script, forbidden, str(SCRIPT))

    for target in ("validate-disposable-clean-target", "test-disposable-clean-target"):
        target_body(makefile, target)
    proof = target_body(makefile, "prove-disposable-clean-target")
    if "##" in proof.splitlines()[0]:
        raise ContractError("destructive disposable-target proof must stay hidden from normal make help")
    for needle in (
        "DISPOSABLE_TARGET_HOST",
        "DISPOSABLE_TARGET_BOOTSTRAP_USER",
        "DISPOSABLE_TARGET_BOOTSTRAP_IDENTITY_FILE",
        "DISPOSABLE_TARGET_HOST_KEY_SHA256",
        "DISPOSABLE_TARGET_ID",
        "DISPOSABLE_TARGET_CONFIRM",
        "DISPOSABLE_TARGET_PROVIDER_RECOVERY_CONFIRM",
        "$(DISPOSABLE_CLEAN_TARGET_PROOF)",
    ):
        require(proof, needle, "Makefile prove-disposable-clean-target")

    fast = target_body(makefile, "ci-fast-source")
    for target in ("validate-disposable-clean-target", "test-disposable-clean-target"):
        require(fast, target, "Makefile ci-fast-source")

    for needle in (
        "provider-neutral",
        "fresh Ubuntu 24.04",
        "one-shot",
        "0600",
        "host-key fingerprint",
        "changed=0",
        "sanitized evidence",
        "does not create or destroy",
        "destroy the VPS",
        "Coolify is not part of this core proof",
    ):
        require(doc, needle, str(DOC))

    for needle in (
        "disposable clean-target core proof",
        "sanitized evidence",
        "does not satisfy the deferred self-repository `fast-source` proof",
    ):
        require(testing, needle, str(TESTING))

    for needle in (
        "latest disposable clean-target core evidence",
        "changed=0",
        "does not replace the self-repository `fast-source` prerequisite",
    ):
        require(release, needle, str(RELEASE))

    require(state, "evidence/disposable-clean-target/", str(STATE))


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    try:
        validate(root)
    except (OSError, ContractError) as exc:
        print(f"ERROR disposable clean-target contract: {exc}", file=sys.stderr)
        return 2
    print("PASS disposable clean-target contract: explicit marked Ubuntu 24.04 target -> hardened host -> changed=0 with sanitized evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
