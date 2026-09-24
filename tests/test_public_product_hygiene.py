from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.validate_public_product_hygiene import ContractError, validate


ROOT = Path(__file__).resolve().parents[1]


class PublicProductHygieneTests(unittest.TestCase):
    def test_repository_contract_passes(self) -> None:
        validate(ROOT)

    def _copy_minimal(self, tmp: str) -> Path:
        root = Path(tmp)
        for rel in (
            ".gitignore",
            "README.md",
            "CHANGELOG.md",
            "ROADMAP.md",
            "CONTRIBUTING.md",
            "docs/operations/first-app.md",
            "legacy/06-ci-supply-chain-ghcr.md",
        ):
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text((ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
        return root

    def test_owner_driven_diary_wording_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_minimal(tmp)
            roadmap = root / "ROADMAP.md"
            roadmap.write_text(roadmap.read_text(encoding="utf-8") + "\nowner-driven integration rerun\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                validate(root)

    def test_owner_validation_label_in_roadmap_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_minimal(tmp)
            roadmap = root / "ROADMAP.md"
            roadmap.write_text(roadmap.read_text(encoding="utf-8") + "\nM10 PASS V3 OWNER TARGET\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                validate(root)

    def test_concrete_runtime_digest_in_roadmap_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_minimal(tmp)
            roadmap = root / "ROADMAP.md"
            roadmap.write_text(roadmap.read_text(encoding="utf-8") + "\nsha256:" + "a" * 64 + "\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                validate(root)

    def test_real_age_recipient_in_docs_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_minimal(tmp)
            readme = root / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + "\nage1" + "q" * 58 + "\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                validate(root)

    def test_public_routable_ip_in_docs_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_minimal(tmp)
            readme = root / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + "\norigin: 8.8.8.8\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                validate(root)

    def test_concrete_github_identity_in_legacy_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_minimal(tmp)
            legacy = root / "legacy" / "06-ci-supply-chain-ghcr.md"
            legacy.write_text(legacy.read_text(encoding="utf-8") + '\nGITHUB_OWNER="real-user"\n', encoding="utf-8")
            with self.assertRaises(ContractError):
                validate(root)


if __name__ == "__main__":
    unittest.main()
