from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from scripts import validate_disaster_recovery_contract as contract

ROOT = Path(__file__).resolve().parents[1]


class DisasterRecoveryContractTests(unittest.TestCase):
    def test_repository_contract_passes(self):
        contract.validate(ROOT)

    def copy_repo_slice(self, target: Path) -> None:
        for rel in (
            "docs/contracts/disaster-recovery-policy.yml",
            "docs/disaster-recovery.md",
            "scripts/recovery_kit.py",
            "scripts/coolify_instance_restore.py",
            "scripts/restic_runtime.py",
            "ansible/roles/backup/defaults/main.yml",
            "Makefile",
        ):
            source = ROOT / rel
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)

    def test_contract_rejects_raw_database_tree_reintroduction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.copy_repo_slice(root)
            path = root / "docs/contracts/disaster-recovery-policy.yml"
            text = path.read_text(encoding="utf-8").replace("    - /data/coolify/databases\n", "")
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(contract.DisasterRecoveryContractError):
                contract.validate(root)

    def test_contract_rejects_old_env_wholesale_restore_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.copy_repo_slice(root)
            path = root / "docs/contracts/disaster-recovery-policy.yml"
            path.write_text(path.read_text(encoding="utf-8").replace("old_env_wholesale_copy: forbidden", "old_env_wholesale_copy: allowed"), encoding="utf-8")
            with self.assertRaises(contract.DisasterRecoveryContractError):
                contract.validate(root)

    def test_contract_rejects_missing_private_restic_staging_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.copy_repo_slice(root)
            path = root / "scripts/restic_runtime.py"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "I_HAVE_VERIFIED_A_PRIVATE_DISASTER_RECOVERY_STAGING_DIRECTORY",
                    "REMOVED_STAGING_CONFIRM",
                ),
                encoding="utf-8",
            )
            with self.assertRaises(contract.DisasterRecoveryContractError):
                contract.validate(root)

    def test_contract_rejects_missing_target_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.copy_repo_slice(root)
            path = root / "scripts/coolify_instance_restore.py"
            path.write_text(path.read_text(encoding="utf-8").replace("I_HAVE_VERIFIED_THE_REPLACEMENT_VPS_FOR_COOLIFY_RESTORE", "REMOVED_CONFIRM"), encoding="utf-8")
            with self.assertRaises(contract.DisasterRecoveryContractError):
                contract.validate(root)

    def test_rejects_broad_local_authorization_of_recovered_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.copy_repo_slice(root)
            policy = root / "docs/contracts/disaster-recovery-policy.yml"
            text = policy.read_text(encoding="utf-8").replace(
                "unrelated_recovered_keys_reauthorized_locally: false",
                "unrelated_recovered_keys_reauthorized_locally: true",
            )
            policy.write_text(text, encoding="utf-8")
            with self.assertRaises(contract.DisasterRecoveryContractError):
                contract.validate(root)


if __name__ == "__main__":
    unittest.main()
