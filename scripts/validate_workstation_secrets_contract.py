#!/usr/bin/env python3
"""Validate the simple Solo VPS M13 workstation secrets contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


class ContractError(RuntimeError):
    pass


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        raise ContractError(f"{where} must contain {needle!r}")


def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        raise ContractError(f"{where} must not contain obsolete concept {needle!r}")


def validate(root: Path) -> None:
    root = root.resolve()
    passport = (root / "PROJECT_PASSPORT.md").read_text(encoding="utf-8")
    roadmap = (root / "ROADMAP.md").read_text(encoding="utf-8")
    secrets = (root / "docs" / "secrets-sops-age.md").read_text(encoding="utf-8")
    adr = (root / "docs" / "adr" / "0002-controller-side-sops-decryption.md").read_text(encoding="utf-8")
    makefile = (root / "Makefile").read_text(encoding="utf-8")

    require(passport, "one Ubuntu VPS", "PROJECT_PASSPORT.md")
    require(passport, "Windows or Linux workstation", "PROJECT_PASSPORT.md")
    require(roadmap, "home workstation (Windows or Linux)", "ROADMAP.md")
    require(roadmap, "There is exactly one VPS", "ROADMAP.md")
    require(secrets, "## Windows workstation", "docs/secrets-sops-age.md")
    require(secrets, "## Linux workstation", "docs/secrets-sops-age.md")
    require(secrets, "one age private key", "docs/secrets-sops-age.md")
    require(adr, "operator workstation", "ADR-0002")
    require(adr, "does not require a second server", "ADR-0002")
    require(makefile, "init-sops-policy", "Makefile")
    require(makefile, "secrets-crypto-proof", "Makefile")
    require(makefile, "verify-vps-secrets-boundary", "Makefile")
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    require(gitignore, "/.sops.yaml", ".gitignore")
    require(gitignore, "/secrets/recipients/production.txt", ".gitignore")
    windows_helpers = (
        "scripts/windows/install-secrets-tools.ps1",
        "scripts/windows/new-age-key.ps1",
        "scripts/windows/test-age-key.ps1",
        "scripts/windows/init-sops-policy.ps1",
    )
    if not (root / "scripts/verify_vps_secrets_boundary.py").is_file():
        raise ContractError("M13 VPS private-key absence verifier is missing")
    for rel in windows_helpers:
        if not (root / rel).is_file():
            raise ContractError(f"Windows-first M13 helper is missing: {rel}")
    install_ps = (root / windows_helpers[0]).read_text(encoding="utf-8")
    create_ps = (root / windows_helpers[1]).read_text(encoding="utf-8")
    smoke_ps = (root / windows_helpers[2]).read_text(encoding="utf-8")
    init_policy_ps = (root / windows_helpers[3]).read_text(encoding="utf-8")
    for needle in (
        "https://github.com/FiloSottile/age/releases/download/v$AgeVersion/age-v$AgeVersion-windows-amd64.zip",
        "c56e8ce22f7e80cb85ad946cc82d198767b056366201d3e1a2b93d865be38154",
        "https://github.com/getsops/sops/releases/download/v$SopsVersion/sops-v$SopsVersion.amd64.exe",
        "a4a9a398858fe8b2ef72d9686d930bf7c5cece9be74ad83ac3b53cfdd70e6b1c",
        "Get-FileHash",
        "LOCALAPPDATA",
        "--version 2>$null",
    ):
        require(install_ps, needle, windows_helpers[0])
    for needle in (
        "age-keygen.exe",
        "install-secrets-tools.ps1",
        "PASS Solo VPS age key already exists",
        "existing key replaced: no",
        ".config\\solo-vps\\age-key.txt",
        '$ErrorActionPreference = "Continue"',
        "2>$null",
        "SetAccessRuleProtection($true, $false)",
        "S-1-5-18",
        "S-1-5-32-544",
        "init-sops-policy.ps1",
    ):
        require(create_ps, needle, windows_helpers[1])
    forbid(create_ps, 'throw "Refusing to overwrite existing age key', windows_helpers[1])
    for needle in ("sops.exe", "install-secrets-tools.ps1", "solo-vps-m13-workstation-proof-v1", "Remove-Item -LiteralPath $tempDir -Recurse -Force", "2>$null"):
        require(smoke_ps, needle, windows_helpers[2])
    for needle in ("Resolve-SoloVpsTool -Name \"age-keygen\"", "$StateRoot", "sops\\.sops.yaml", "sops\\production.txt", "Refusing to overwrite existing public SOPS policy file", "LegacyContent", "migrated", ".backup.", "[System.IO.File]::Replace($temporary, $Path, $backup)", "[switch]$ResetPublicPolicy", "[switch]$StartFresh", "*.enc.yaml", "encrypted bundles found:", "Refusing -ResetPublicPolicy because encrypted state bundles exist", "archive\\workstation-secrets", "Archive-And-RemoveLocalSecretState", "previous local secret state archived", "Private age key copied here: no", "secrets/policy-probe.enc.yaml", "cross-platform SOPS policy probe: PASS", "source checkout mutated: no", "Get-Content"):
        require(init_policy_ps, needle, windows_helpers[3])
    forbid(init_policy_ps, "[System.IO.File]::Replace($temporary, $Path, $null)", windows_helpers[3])
    require(secrets, "Get-ChildItem .\\scripts\\windows\\*.ps1 | Unblock-File", "docs/secrets-sops-age.md")
    require(secrets, ".\\scripts\\windows\\install-secrets-tools.ps1", "docs/secrets-sops-age.md")
    require(secrets, ".\\scripts\\windows\\init-sops-policy.ps1", "docs/secrets-sops-age.md")
    require(secrets, "-StartFresh", "docs/secrets-sops-age.md")
    require(secrets, "archive\\workstation-secrets", "docs/secrets-sops-age.md")
    require(secrets, "RemoteSigned", "docs/secrets-sops-age.md")
    require(secrets, "Get-ExecutionPolicy -List", "docs/secrets-sops-age.md")
    forbid(secrets, "Set-ExecutionPolicy", "docs/secrets-sops-age.md")
    require(secrets, "make secrets-tools", "docs/secrets-sops-age.md")
    for forbidden in ("ssh.exe", "scp.exe", "wsl.exe", "choco", "winget"):
        forbid(install_ps + create_ps + smoke_ps + init_policy_ps, forbidden, "Windows M13 helpers")

    obsolete_files = [
        "scripts/offvps_controller_access.py",
        "scripts/check_m13_offvps_controller.py",
        "scripts/materialize_sops_secret.py",
        "ansible/playbooks/authorize-offvps-controller.yml",
        "ansible/playbooks/materialize-secret.yml",
    ]
    for rel in obsolete_files:
        if (root / rel).exists():
            raise ContractError(f"obsolete M13 complexity must be absent: {rel}")

    for needle in (
        "plan-offvps-controller-access",
        "authorize-offvps-controller-access",
        "m13-offvps-controller-ready",
        "materialize-m13-secret-proof",
        "I_AM_RUNNING_ON_AN_OFF_VPS_SECRET_CONTROLLER",
    ):
        forbid(makefile, needle, "Makefile")

    print("PASS M13 workstation secrets contract: one home workstation + one VPS, simple age key workflow")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate(Path(args.root))
    except (OSError, ContractError) as exc:
        print(f"ERROR workstation secrets contract: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
