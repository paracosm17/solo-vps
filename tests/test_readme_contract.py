from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validate_readme_contract import ContractError, validate_readme


ROOT = Path(__file__).resolve().parents[1]


class ReadmeContractTests(unittest.TestCase):
    def make_fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="solo-vps-readme-test-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)

        seed_paths = (
            "README.md",
            "Makefile",
            "docs/quick-start.md",
            "docs/command-reference.md",
        )
        for relative in seed_paths:
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        # Copy the direct local link targets used by the three documents that the
        # validator checks. The fixture stays representative as navigation evolves.
        for relative in seed_paths[:1] + seed_paths[2:]:
            source_path = ROOT / relative
            for target in re.findall(r"\]\(([^)]+)\)", source_path.read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                clean = target.split("#", 1)[0]
                if not clean:
                    continue
                src = (source_path.parent / clean).resolve()
                try:
                    rel = src.relative_to(ROOT)
                except ValueError:
                    continue
                if not src.is_file():
                    continue
                dst = temp / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        return temp

    def mutate(self, root: Path, relative: str, old: str, new: str, *, all_matches: bool = False) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, -1 if all_matches else 1), encoding="utf-8")

    def test_current_contract_passes(self) -> None:
        validate_readme(ROOT)

    def test_missing_pre_alpha_status_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "README.md", "PRE-ALPHA", "EARLY", all_matches=True)
        with self.assertRaises(ContractError):
            validate_readme(root)

    def test_unknown_make_target_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "README.md", "make platform", "make imaginary-target")
        with self.assertRaises(ContractError):
            validate_readme(root)

    def test_missing_automated_setup_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "README.md", "make setup", "make help")
        with self.assertRaises(ContractError):
            validate_readme(root)

    def test_missing_apply_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "README.md", "make apply", "make help", all_matches=True)
        with self.assertRaises(ContractError):
            validate_readme(root)

    def test_missing_canonical_quick_start_link_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "README.md", "docs/quick-start.md", "docs/preflight.md")
        with self.assertRaises(ContractError):
            validate_readme(root)

    def test_primary_lifecycle_order_is_enforced(self) -> None:
        root = self.make_fixture()
        path = root / "README.md"
        text = path.read_text(encoding="utf-8")
        start = text.index("## Quick Start")
        end = text.index("## Safety boundaries")
        section = text[start:end]
        apply = section.index("make apply")
        secure = section.index("make secure")
        section = section[:apply] + "make secure" + section[apply + len("make apply"):secure] + "make apply" + section[secure + len("make secure"):]
        path.write_text(text[:start] + section + text[end:], encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_readme(root)

    def test_missing_detailed_admin_key_step_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "docs/quick-start.md", "make human-admin-key-stdin", "make help", all_matches=True)
        with self.assertRaises(ContractError):
            validate_readme(root)

    def test_missing_coolify_boundary_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "README.md", "does not install Coolify", "does not install the application platform")
        with self.assertRaises(ContractError):
            validate_readme(root)


if __name__ == "__main__":
    unittest.main()
