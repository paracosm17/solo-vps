from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.validate_database_backup_runtime_contract import ContractError, validate

ROOT = Path(__file__).resolve().parents[1]


class DatabaseBackupRuntimeContractTests(unittest.TestCase):
    def test_committed_contract_passes(self):
        validate(ROOT)

    def test_public_api_regression_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_contract_files(Path(tmp))
            path = root / "scripts/coolify_database_backup_api.py"
            path.write_text(path.read_text().replace("http://127.0.0.1:8000/api/v1", "https://coolify.example/api/v1", 1))
            with self.assertRaises(ContractError):
                validate(root)

    def test_restore_confirmation_regression_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_contract_files(Path(tmp))
            path = root / "scripts/postgres_restore_exercise.py"
            path.write_text(path.read_text().replace("I_HAVE_VERIFIED_A_DISPOSABLE_POSTGRES_RESTORE_TARGET", "UNSAFE", 1))
            with self.assertRaises(ContractError):
                validate(root)

    def test_read_only_restore_verification_regression_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_contract_files(Path(tmp))
            path = root / "scripts/postgres_restore_exercise.py"
            path.write_text(path.read_text().replace("-c default_transaction_read_only=on", "", 1))
            with self.assertRaises(ContractError):
                validate(root)

    def test_state_inside_source_regression_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_contract_files(Path(tmp))
            path = root / "Makefile"
            path.write_text(path.read_text().replace("DATABASE_BACKUP_STATE_DIR ?= $(SOLO_VPS_STATE_DIR)/database-backups", "DATABASE_BACKUP_STATE_DIR ?= .state/database-backups", 1))
            with self.assertRaises(ContractError):
                validate(root)

    def _copy_contract_files(self, root: Path) -> Path:
        for rel in (
            "scripts/coolify_database_backup_api.py",
            "scripts/postgres_restore_exercise.py",
            "Makefile",
            "docs/database-backups.md",
            "docs/contracts/database-backup-policy.yml",
        ):
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dest)
        return root


if __name__ == "__main__":
    unittest.main()
