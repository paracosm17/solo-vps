from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.validate_disposable_clean_target_contract import ContractError, validate


ROOT = Path(__file__).resolve().parents[1]


class DisposableCleanTargetContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def mutate(self, relative: str, old: str, new: str) -> None:
        path = self.root / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_current_contract_passes(self) -> None:
        validate(self.root)

    def test_rejects_disabled_host_key_checking(self) -> None:
        self.mutate(
            "scripts/prove_disposable_clean_target.py",
            '"StrictHostKeyChecking=yes"',
            '"StrictHostKeyChecking=no"',
        )
        with self.assertRaises(ContractError):
            validate(self.root)

    def test_rejects_missing_production_target_refusal(self) -> None:
        self.mutate("scripts/prove_disposable_clean_target.py", "refuse_production_or_local_target(args.target)", "# removed")
        with self.assertRaises(ContractError):
            validate(self.root)

    def test_rejects_visible_destructive_proof_target(self) -> None:
        self.mutate("Makefile", "prove-disposable-clean-target: validate-disposable-clean-target test-disposable-clean-target\n", "prove-disposable-clean-target: validate-disposable-clean-target test-disposable-clean-target ## run it\n")
        with self.assertRaises(ContractError):
            validate(self.root)

    def test_rejects_missing_idempotency_assertion(self) -> None:
        self.mutate(
            "scripts/prove_disposable_clean_target.py",
            'if second_recap["changed"] != 0:',
            'if second_recap["changed"] < 0:',
        )
        with self.assertRaises(ContractError):
            validate(self.root)

    def test_rejects_provider_specific_destroy_automation(self) -> None:
        self.mutate(
            "scripts/prove_disposable_clean_target.py",
            '"provider_resource_destroyed_by_harness": False,',
            '"provider_resource_destroyed_by_harness": False,\n                # aws ec2 terminate',
        )
        with self.assertRaises(ContractError):
            validate(self.root)

    def test_rejects_missing_external_evidence_state_doc(self) -> None:
        self.mutate("docs/state-layout.md", "evidence/disposable-clean-target/", "evidence/clean/target/")
        with self.assertRaises(ContractError):
            validate(self.root)


if __name__ == "__main__":
    unittest.main()
