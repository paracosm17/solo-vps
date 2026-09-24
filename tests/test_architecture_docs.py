from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validate_architecture_docs import ContractError, validate_architecture


ROOT = Path(__file__).resolve().parents[1]


class ArchitectureDocsTests(unittest.TestCase):
    def make_fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="solo-vps-architecture-test-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)

        for path in (
            "README.md",
            "PROJECT_PASSPORT.md",
            "ROADMAP.md",
            "docs/architecture.md",
            "docs/index.md",
            "docs/adr/0001-coolify-installation-boundary.md",
            "docs/adr/0002-controller-side-sops-decryption.md",
            "docs/adr/0003-coolify-native-database-backups.md",
            ".agents/skills/solo-vps-project-engineer/SKILL.md",
        ):
            src = ROOT / path
            dst = temp / path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return temp

    def mutate(self, root: Path, relative: str, old: str, new: str) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_current_contract_passes(self) -> None:
        validate_architecture(ROOT)

    def test_missing_readme_truth_source_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "docs/architecture.md", "README.md", "README-CURRENT.md")
        with self.assertRaises(ContractError):
            validate_architecture(root)

    def test_missing_passport_source_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "docs/architecture.md", "PROJECT_PASSPORT.md", "PROJECT-PASSPORT")
        with self.assertRaises(ContractError):
            validate_architecture(root)

    def test_missing_accepted_layer_is_rejected(self) -> None:
        root = self.make_fixture()
        path = root / "docs" / "architecture.md"
        path.write_text(path.read_text(encoding="utf-8").replace("GHCR", "registry"), encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_architecture(root)

    def test_accepted_adr_shown_as_proposed_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "docs/architecture.md", "| **Accepted** |", "| **Proposed** |")
        with self.assertRaises(ContractError):
            validate_architecture(root)

    def test_adr_status_change_requires_architecture_update(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "docs/adr/0002-controller-side-sops-decryption.md", "Status: Accepted", "Status: Rejected")
        with self.assertRaises(ContractError):
            validate_architecture(root)

    def test_missing_evidence_boundary_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "docs/architecture.md", "## Current evidence boundary", "## Current state")
        with self.assertRaises(ContractError):
            validate_architecture(root)

    def test_missing_docs_index_link_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "docs/index.md", "](architecture.md)", "](arch-overview.md)")
        with self.assertRaises(ContractError):
            validate_architecture(root)


if __name__ == "__main__":
    unittest.main()
