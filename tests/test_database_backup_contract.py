from __future__ import annotations
import copy
import pathlib
import tempfile
import unittest
import yaml
from scripts.validate_database_backup_contract import DatabaseBackupContractError, validate, validate_no_duplicate_runner
ROOT = pathlib.Path(__file__).resolve().parents[1]

class DatabaseBackupContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = yaml.safe_load((ROOT / "docs/contracts/database-backup-policy.yml").read_text())
        self.adr_text = (ROOT / "docs/adr/0003-coolify-native-database-backups.md").read_text()
        self.defaults = yaml.safe_load((ROOT / "ansible/roles/backup/defaults/main.yml").read_text())
    def test_committed_contract_is_valid(self) -> None:
        validate(self.contract, self.adr_text, self.defaults)
        validate_no_duplicate_runner(ROOT)
    def test_ansible_owner_is_rejected(self) -> None:
        c=copy.deepcopy(self.contract); c["owner"]="ansible"
        with self.assertRaises(DatabaseBackupContractError): validate(c,self.adr_text,self.defaults)
    def test_live_pgdata_boundary_cannot_be_relaxed(self) -> None:
        c=copy.deepcopy(self.contract); c["boundaries"]["raw_pgdata_backup"]="allowed"
        with self.assertRaises(DatabaseBackupContractError): validate(c,self.adr_text,self.defaults)
    def test_required_pg_dump_flags_cannot_drift(self) -> None:
        c=copy.deepcopy(self.contract); c["backup"]["required_arguments"].remove("--no-owner")
        with self.assertRaises(DatabaseBackupContractError): validate(c,self.adr_text,self.defaults)
    def test_archive_verification_must_use_pg_restore_list(self) -> None:
        c=copy.deepcopy(self.contract); c["verification"]["required_arguments"]=["--verbose"]
        with self.assertRaises(DatabaseBackupContractError): validate(c,self.adr_text,self.defaults)
    def test_credential_like_public_field_is_rejected(self) -> None:
        c=copy.deepcopy(self.contract); c["storage"]["access_key"]="not-a-real-secret"
        with self.assertRaises(DatabaseBackupContractError): validate(c,self.adr_text,self.defaults)
    def test_adr_status_mismatch_is_rejected(self) -> None:
        c=copy.deepcopy(self.contract); c["status"]="proposed"
        with self.assertRaises(DatabaseBackupContractError): validate(c,self.adr_text,self.defaults)
    def test_operational_defaults_cannot_drift(self) -> None:
        c=copy.deepcopy(self.contract); c["scheduling"]["retention_days_s3_default"]=0
        with self.assertRaises(DatabaseBackupContractError): validate(c,self.adr_text,self.defaults)
    def test_duplicate_ansible_pg_dump_runner_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp); (root/"ansible").mkdir(); (root/"ansible/tasks.yml").write_text("- command: pg_dump app\n",encoding="utf-8")
            with self.assertRaises(DatabaseBackupContractError): validate_no_duplicate_runner(root)

if __name__ == "__main__": unittest.main()
