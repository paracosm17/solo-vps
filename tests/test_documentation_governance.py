from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validate_documentation_governance import ContractError, validate


ROOT = Path(__file__).resolve().parents[1]


class DocumentationGovernanceTests(unittest.TestCase):
    def make_fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="solo-vps-doc-governance-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        for rel in ("README.md", "PROJECT_PASSPORT.md", "ROADMAP.md", "docs/index.md"):
            src = ROOT / rel
            dst = temp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return temp

    def mutate(self, root: Path, rel: str, old: str, new: str) -> None:
        path = root / rel
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_current_contract_passes(self) -> None:
        validate(ROOT)

    def test_passport_current_state_heading_is_rejected(self) -> None:
        root = self.make_fixture()
        with (root / "PROJECT_PASSPORT.md").open("a", encoding="utf-8") as handle:
            handle.write("\n## Current product state\n")
        with self.assertRaises(ContractError):
            validate(root)

    def test_passport_line_budget_is_enforced(self) -> None:
        root = self.make_fixture()
        with (root / "PROJECT_PASSPORT.md").open("a", encoding="utf-8") as handle:
            handle.write("\n".join("history" for _ in range(100)))
        with self.assertRaises(ContractError):
            validate(root)

    def test_roadmap_line_budget_is_enforced(self) -> None:
        root = self.make_fixture()
        with (root / "ROADMAP.md").open("a", encoding="utf-8") as handle:
            handle.write("\n".join("old iteration transcript" for _ in range(150)))
        with self.assertRaises(ContractError):
            validate(root)

    def test_duplicate_milestone_state_is_rejected(self) -> None:
        root = self.make_fixture()
        roadmap = root / "ROADMAP.md"
        with roadmap.open("a", encoding="utf-8") as handle:
            handle.write("\n| M1 — duplicate | P1 | DONE | duplicate |\n")
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_readme_truth_ownership_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "README.md", "canonical current user contract", "current introduction")
        with self.assertRaises(ContractError):
            validate(root)

    def test_optional_command_in_quick_start_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "README.md", "## Quick Start", "## Quick Start\n\nmake observability-runtime")
        with self.assertRaises(ContractError):
            validate(root)

    def test_marketing_hero_on_homepage_is_rejected(self) -> None:
        root = self.make_fixture()
        with (root / "docs/index.md").open("a", encoding="utf-8") as handle:
            handle.write("\n<div class=\"solo-hero\">marketing</div>\n")
        with self.assertRaises(ContractError):
            validate(root)


if __name__ == "__main__":
    unittest.main()
