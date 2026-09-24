from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.validate_backup_credentials_contract import ContractError, validate

ROOT = Path(__file__).resolve().parents[1]


class BackupCredentialContractTests(unittest.TestCase):
    def test_repository_contract_passes(self) -> None:
        validate(ROOT)

    def test_missing_runtime_mode_contract_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            needed = (
                "Makefile",
                "scripts/backup_secret_bundle.py",
                "scripts/install_backup_credentials.py",
                "scripts/backup_credentials_common.py",
                "scripts/windows/init-backup-secrets.ps1",
                "scripts/windows/test-backup-secrets.ps1",
                "scripts/windows/push-backup-secrets.ps1",
                "docs/backups-restic.md",
                "docs/operations/offsite-backups.md",
                "docs/backup-storage-backblaze-b2.md",
                "docs/backup-storage-cloudflare-r2.md",
                "docs/secrets-sops-age.md",
            )
            for rel in needed:
                destination = root / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                text = (ROOT / rel).read_text(encoding="utf-8")
                if rel == "scripts/install_backup_credentials.py":
                    text = text.replace("os.chmod(destination, 0o600)", "os.chmod(destination, 0o644)")
                destination.write_text(text, encoding="utf-8")
            with self.assertRaises(ContractError):
                validate(root)


if __name__ == "__main__":
    unittest.main()
