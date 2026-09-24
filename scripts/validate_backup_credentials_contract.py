#!/usr/bin/env python3
"""Validate the source-only M14 workstation-to-VPS backup credential boundary."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


class ContractError(RuntimeError):
    pass


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        raise ContractError(f"{where} missing backup credential contract: {needle}")


def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        raise ContractError(f"{where} contains forbidden backup credential behavior: {needle}")


def validate(root: Path) -> None:
    root = root.resolve()
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    bundle = (root / "scripts/backup_secret_bundle.py").read_text(encoding="utf-8")
    installer = (root / "scripts/install_backup_credentials.py").read_text(encoding="utf-8")
    common = (root / "scripts/backup_credentials_common.py").read_text(encoding="utf-8")
    windows_init = (root / "scripts/windows/init-backup-secrets.ps1").read_text(encoding="utf-8")
    windows_check = (root / "scripts/windows/test-backup-secrets.ps1").read_text(encoding="utf-8")
    windows_push = (root / "scripts/windows/push-backup-secrets.ps1").read_text(encoding="utf-8")
    docs = (root / "docs/backups-restic.md").read_text(encoding="utf-8")
    offsite_docs = (root / "docs/operations/offsite-backups.md").read_text(encoding="utf-8")
    provider_docs = (root / "docs/backup-storage-backblaze-b2.md").read_text(encoding="utf-8")
    alternative_provider_docs = (root / "docs/backup-storage-cloudflare-r2.md").read_text(encoding="utf-8")
    secrets_docs = (root / "docs/secrets-sops-age.md").read_text(encoding="utf-8")

    for needle in (
        "SOLO_VPS_SECRET_DIR ?= $(SOLO_VPS_DATA_DIR)/secrets",
        "BACKUP_SECRET_FILE ?= $(SOLO_VPS_SECRET_DIR)/backup.enc.yaml",
        "backup-secrets-init:",
        "backup-secrets-check:",
        "backup-secrets-push:",
        "verify-backup-credentials:",
    ):
        require(makefile, needle, "Makefile")

    for needle in (
        'SOPS_FILENAME_OVERRIDE = "secrets/backup.enc.yaml"',
        "secrets.token_urlsafe(32)",
        "SOPS_AGE_KEY_FILE",
        "SSH stdin",
        "source checkout mutated: no",
        "secret-bearing stderr was suppressed",
        "refusing symlink backup ciphertext destination",
        "encrypted = _absolute_unresolved(args.encrypted)",
        "key_file = _absolute_unresolved(args.key_file)",
    ):
        require(bundle, needle, "scripts/backup_secret_bundle.py")

    for needle in (
        'DEFAULT_DIRECTORY = Path("/etc/solo-vps/backup")',
        '"credentials.json"',
        "os.chmod(directory, 0o700)",
        "os.chmod(destination, 0o600)",
        "refusing non-regular credential path",
        "plaintext printed: no",
        "_absolute_unresolved(args.path)",
    ):
        require(installer, needle, "scripts/install_backup_credentials.py")

    for needle in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "RESTIC_PASSWORD", "AWS_SESSION_TOKEN"):
        require(common, needle, "scripts/backup_credentials_common.py")

    for text, where in (
        (windows_init, "scripts/windows/init-backup-secrets.ps1"),
        (windows_check, "scripts/windows/test-backup-secrets.ps1"),
        (windows_push, "scripts/windows/push-backup-secrets.ps1"),
    ):
        require(text, "LOCALAPPDATA", where)
        require(text, "secret-bearing stderr was suppressed", where)
        forbid(text, "AGE-SECRET-KEY-", where)

    require(windows_init, "already exists; reusing it", "scripts/windows/init-backup-secrets.ps1")
    require(bundle, "already exists; reusing it", "scripts/backup_secret_bundle.py")

    for needle in (
        ".\\scripts\\windows\\init-sops-policy.ps1",
        ".\\scripts\\windows\\init-backup-secrets.ps1",
        ".\\scripts\\windows\\push-backup-secrets.ps1",
        "/etc/solo-vps/backup/credentials.json",
        "make backup-secrets-init",
        "make backup-secrets-push",
        "make verify-backup-credentials",
    ):
        require(docs, needle, "docs/backups-restic.md")

    for needle in (
        "Backblaze B2",
        "does not require a credit card",
        "first 10 GB",
        "https://s3.<REGION>.backblazeb2.com",
        "Read and Write",
        "Allow List All Bucket Names",
        "keyID",
        "applicationKey",
    ):
        require(provider_docs, needle, "docs/backup-storage-backblaze-b2.md")

    for needle in (
        "Alternative provider",
        "Backblaze B2",
        "Cloudflare R2",
    ):
        require(alternative_provider_docs, needle, "docs/backup-storage-cloudflare-r2.md")

    require(docs, "Off-site storage does not mean a second VPS", "docs/backups-restic.md")
    require(docs, "backup-storage-backblaze-b2.md", "docs/backups-restic.md")
    require(docs, "backup-storage-cloudflare-r2.md", "docs/backups-restic.md")

    for required in (
        "Backblaze B2",
        "Allow List All Bucket Names",
        "Validate Connection & Continue",
        "S3 Storage",
        "Settings → Backup",
        "APP_KEY",
        "make backup-repository-init",
        "make backup-restore-test",
        "make backup-schedule-enable",
        "age-key.txt",
    ):
        require(offsite_docs, required, "docs/operations/offsite-backups.md")

    require(secrets_docs, "backup.enc.yaml", "docs/secrets-sops-age.md")
    require(secrets_docs, "age private key remains on the workstation", "docs/secrets-sops-age.md")

    for forbidden in (
        "RESTIC_PASSWORD=example",
        "AWS_SECRET_ACCESS_KEY=example",
        "copy the age private key to the VPS",
    ):
        forbid(docs + secrets_docs, forbidden, "backup/secrets documentation")

    print("PASS M14 backup credential contract: workstation SOPS ciphertext -> SSH stdin -> root-only VPS runtime file")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate(Path(args.root))
    except (OSError, ContractError) as exc:
        print(f"ERROR backup credential contract: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
