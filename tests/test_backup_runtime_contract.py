from __future__ import annotations

import pathlib
import tempfile
import unittest

from scripts.validate_backup_runtime_contract import ContractError, validate

ROOT = pathlib.Path(__file__).resolve().parents[1]


class BackupRuntimeContractTests(unittest.TestCase):
    def test_committed_runtime_contract_is_valid(self) -> None:
        validate(ROOT)

    def test_operation_yaml_respects_m20_line_length(self) -> None:
        operation = (ROOT / "ansible/roles/backup/tasks/operation.yml").read_text(encoding="utf-8")
        overlong = [(number, len(line)) for number, line in enumerate(operation.splitlines(), 1) if len(line) > 240]
        self.assertEqual(overlong, [])

    def test_missing_retention_confirmation_boundary_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for relative in (
                "scripts/restic_runtime.py",
                "ansible/roles/backup/defaults/main.yml",
                "ansible/roles/backup/tasks/runtime.yml",
                "ansible/roles/backup/tasks/verify-runtime.yml",
                "ansible/roles/backup/tasks/operation.yml",
                "ansible/roles/backup/templates/solo-vps-backup.service.j2",
                "ansible/roles/backup/templates/solo-vps-backup.timer.j2",
                "ansible/roles/backup/templates/solo-vps-backup-maintenance.service.j2",
                "ansible/roles/backup/templates/solo-vps-backup-maintenance.timer.j2",
                "Makefile",
            ):
                src = ROOT / relative
                dst = root / relative
                dst.parent.mkdir(parents=True, exist_ok=True)
                text = src.read_text(encoding="utf-8")
                if relative == "scripts/restic_runtime.py":
                    text = text.replace("retention apply requires the exact reviewed-plan confirmation", "unsafe")
                dst.write_text(text, encoding="utf-8")
            with self.assertRaises(ContractError):
                validate(root)


if __name__ == "__main__":
    unittest.main()
