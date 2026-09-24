from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validate_upgrade_guide import ContractError, validate_upgrade_guide


ROOT = Path(__file__).resolve().parents[1]


class UpgradeGuideTests(unittest.TestCase):
    def make_fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="solo-vps-upgrade-guide-test-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        for path in (
            "README.md",
            "ROADMAP.md",
            "docs/upgrades.md",
            "docs/index.md",
            "docs/adr/0001-coolify-installation-boundary.md",
            "ansible/requirements.yml",
            "ansible/roles/docker/tasks/main.yml",
            "ansible/roles/docker/defaults/main.yml",
            "ansible/roles/backup/defaults/main.yml",
            "docs/contracts/platform-lifecycle-policy.yml",
            "tools/qa-requirements.txt",
            "tools/secrets-toolchain.json",
            "examples/hello-app/Dockerfile",
            "templates/github-actions/hello-app-ci.yml",
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
        validate_upgrade_guide(ROOT)

    def test_missing_recovery_boundary_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "docs/upgrades.md",
            "A previous project checkout is **not** a generic runtime rollback.",
            "A previous project checkout is the runtime rollback.",
        )
        with self.assertRaises(ContractError):
            validate_upgrade_guide(root)

    def test_docker_role_upgrade_semantics_drift_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "ansible/roles/docker/tasks/main.yml", "state: present", "state: latest")
        with self.assertRaises(ContractError):
            validate_upgrade_guide(root)

    def test_accepted_coolify_adr_requires_exact_supported_pair(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "docs/upgrades.md",
            "previous supported Coolify: `4.1.1`",
            "previous supported Coolify: `latest`",
        )
        with self.assertRaises(ContractError):
            validate_upgrade_guide(root)

    def test_future_docker_major_support_drift_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/docker/defaults/main.yml",
            "solo_vps_docker_supported_major_versions:\n  - 29",
            "solo_vps_docker_supported_major_versions:\n  - 29\n  - 30",
        )
        with self.assertRaises(ContractError):
            validate_upgrade_guide(root)

    def test_floating_ansible_collection_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "ansible/requirements.yml", 'version: "13.0.1"', 'version: ">=13,<14"')
        with self.assertRaises(ContractError):
            validate_upgrade_guide(root)

    def test_unsafe_git_pull_main_command_is_rejected(self) -> None:
        root = self.make_fixture()
        path = root / "docs" / "upgrades.md"
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n```bash\ngit pull origin main\n```\n")
        with self.assertRaises(ContractError):
            validate_upgrade_guide(root)

    def test_restic_self_update_command_is_rejected(self) -> None:
        root = self.make_fixture()
        path = root / "docs" / "upgrades.md"
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n```bash\nrestic self-update\n```\n")
        with self.assertRaises(ContractError):
            validate_upgrade_guide(root)

    def test_missing_readme_navigation_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "README.md", "](docs/upgrades.md)", "](docs/update.md)")
        with self.assertRaises(ContractError):
            validate_upgrade_guide(root)


if __name__ == "__main__":
    unittest.main()
