from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validate_community_policy import ContractError, validate_community_policy


ROOT = Path(__file__).resolve().parents[1]


class CommunityPolicyTests(unittest.TestCase):
    def make_fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="solo-vps-community-policy-test-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        for path in (
            "SECURITY.md",
            "CONTRIBUTING.md",
            "README.md",
            "PROJECT_PASSPORT.md",
            "ROADMAP.md",
            "LICENSE",
            "docs/license-choice.md",
            "docs/index.md",
            "docs/architecture.md",
            "docs/dependency-hygiene.md",
            "docs/command-reference.md",
            ".agents/skills/solo-vps-project-engineer/ROADMAP_PROTOCOL.md",
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
        validate_community_policy(ROOT)

    def test_placeholder_security_email_is_rejected(self) -> None:
        root = self.make_fixture()
        with (root / "SECURITY.md").open("a", encoding="utf-8") as handle:
            handle.write("\nContact: security@example.com\n")
        with self.assertRaises(ContractError):
            validate_community_policy(root)

    def test_missing_private_reporting_boundary_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "SECURITY.md", "Private vulnerability reporting", "Security reports")
        with self.assertRaises(ContractError):
            validate_community_policy(root)

    def test_contributing_without_apache_terms_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "CONTRIBUTING.md", "compatible with distribution under Apache-2.0", "compatible with another license")
        with self.assertRaises(ContractError):
            validate_community_policy(root)

    def test_modified_license_file_is_rejected(self) -> None:
        root = self.make_fixture()
        with (root / "LICENSE").open("a", encoding="utf-8") as handle:
            handle.write("modified\n")
        with self.assertRaises(ContractError):
            validate_community_policy(root)

    def test_license_note_without_selected_spdx_is_rejected(self) -> None:
        root = self.make_fixture()
        path = root / "docs" / "license-choice.md"
        path.write_text(path.read_text(encoding="utf-8").replace("SPDX identifier: `Apache-2.0`", "SPDX identifier: `OTHER`"), encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_community_policy(root)

    def test_readme_without_security_link_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "README.md", "[`SECURITY.md`](SECURITY.md)", "[`security policy`](SECURITY-POLICY.md)")
        with self.assertRaises(ContractError):
            validate_community_policy(root)


if __name__ == "__main__":
    unittest.main()
