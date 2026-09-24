from __future__ import annotations

import pathlib
import shutil
import tempfile
import unittest

import yaml

from scripts.validate_verify_contract import VerifyContractError, validate

ROOT = pathlib.Path(__file__).resolve().parents[1]


class VerifyContractTests(unittest.TestCase):
    def copy_contract(self, destination: pathlib.Path) -> pathlib.Path:
        for relative in (
            "ansible/playbooks/verify.yml",
            "ansible/playbooks/verify-platform.yml",
            "ansible/roles/platform_verify/tasks/main.yml",
            "ansible/roles/platform_verify/defaults/main.yml",
        ):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        return destination

    def test_current_contract_is_valid(self) -> None:
        validate(ROOT)

    def test_rejects_platform_summary_before_bootstrap_verifiers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/playbooks/verify.yml"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            data.insert(1, data.pop())
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            with self.assertRaises(VerifyContractError):
                validate(root)

    def test_rejects_mutating_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/platform_verify/tasks/main.yml"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            data.insert(0, {"name": "Bad mutation", "ansible.builtin.file": {"path": "/tmp/x", "state": "touch"}})
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            with self.assertRaises(VerifyContractError):
                validate(root)

    def test_rejects_command_without_changed_when_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/platform_verify/tasks/main.yml"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            for task in data:
                if "ansible.builtin.command" in task:
                    task.pop("changed_when", None)
                    break
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            with self.assertRaises(VerifyContractError):
                validate(root)

    def test_rejects_missing_evidence_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/platform_verify/defaults/main.yml"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            data["solo_vps_verify_evidence_boundaries"].pop("backup_freshness")
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            with self.assertRaises(VerifyContractError):
                validate(root)

    def test_rejects_false_pass_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/platform_verify/defaults/main.yml"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            data["solo_vps_verify_evidence_boundaries"]["coolify_runtime"] = "PASS: trust me"
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            with self.assertRaises(VerifyContractError):
                validate(root)


if __name__ == "__main__":
    unittest.main()
