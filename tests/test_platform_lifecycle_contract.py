from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validate_platform_lifecycle_contract import ContractError, validate


ROOT = Path(__file__).resolve().parents[1]


class PlatformLifecycleContractTests(unittest.TestCase):
    def fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="solo-vps-platform-lifecycle-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        for relative in (
            "Makefile", "docs/contracts/platform-lifecycle-policy.yml", "docs/upgrades.md",
            "docs/release-process.md", "ansible/roles/docker/defaults/main.yml",
            "ansible/roles/docker/tasks/main.yml", "ansible/roles/docker/tasks/verify.yml",
            "ansible/roles/coolify/defaults/main.yml", "ansible/roles/coolify/tasks/upgrade-preflight.yml",
            "ansible/roles/coolify/tasks/upgrade.yml", "ansible/roles/coolify/tasks/upgrade-resume.yml",
            "ansible/roles/coolify/tasks/evaluation-preflight.yml",
            "ansible/roles/coolify/tasks/evaluate-sentinel.yml",
            "ansible/playbooks/coolify-4.3.21-evaluation-vars.yml",
            "ansible/playbooks/coolify-evaluate-4-3-21-preflight.yml",
            "ansible/playbooks/coolify-evaluate-4-3-21-upgrade.yml",
            "ansible/playbooks/coolify-evaluate-4-3-21-resume.yml",
            "ansible/playbooks/verify-coolify-4-3-21-candidate.yml",
            "scripts/inspect_coolify_sentinel.py", "docs/coolify-4.3.21-evaluation.md",
        ):
            target = temp / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        return temp

    def mutate(self, root: Path, relative: str, old: str, new: str) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_current_contract_passes(self) -> None:
        validate(ROOT)

    def test_future_docker_major_acceptance_is_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, "ansible/roles/docker/defaults/main.yml", "  - 29\n", "  - 29\n  - 30\n")
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_fresh_candidate_gate_is_rejected(self) -> None:
        root = self.fixture()
        self.mutate(
            root,
            "ansible/roles/docker/tasks/main.yml",
            "Refuse an untested Docker major before first installation",
            "Allow any Docker major before first installation",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_coolify_previous_version_drift_is_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, "ansible/roles/coolify/defaults/main.yml", 'solo_vps_coolify_previous_supported_version: "4.1.1"', 'solo_vps_coolify_previous_supported_version: "4.1.0"')
        with self.assertRaises(ContractError):
            validate(root)

    def test_upstream_installer_in_upgrade_flow_is_rejected(self) -> None:
        root = self.fixture()
        path = root / "ansible/roles/coolify/tasks/upgrade.yml"
        path.write_text(path.read_text(encoding="utf-8") + "\n# curl -fsSL https://cdn.coollabs.io/coolify/install.sh\n", encoding="utf-8")
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_instance_backup_gate_is_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, "ansible/roles/coolify/tasks/upgrade.yml", "coolify_upgrade_checkpoint.py", "missing_checkpoint.py")
        with self.assertRaises(ContractError):
            validate(root)

    def test_automatic_downgrade_policy_is_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, "docs/contracts/platform-lifecycle-policy.yml", "automatic_downgrade_on_failure: false", "automatic_downgrade_on_failure: true")
        with self.assertRaises(ContractError):
            validate(root)

    def test_lifecycle_playbook_missing_from_real_syntax_gate_is_rejected(self) -> None:
        root = self.fixture()
        line = "\t@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/coolify-upgrade.yml --syntax-check -e @$(EXAMPLE_CONFIG)\n"
        self.mutate(root, "Makefile", line, "")
        with self.assertRaises(ContractError):
            validate(root)

    def test_candidate_version_drift_is_rejected(self) -> None:
        root = self.fixture()
        self.mutate(
            root,
            "ansible/playbooks/coolify-4.3.21-evaluation-vars.yml",
            'solo_vps_coolify_version: "4.3.21"',
            'solo_vps_coolify_version: "4.3.22"',
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_candidate_sentinel_public_port_check_is_required(self) -> None:
        root = self.fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/evaluate-sentinel.yml",
            "Prove Sentinel does not publish its API to the controller",
            "Skip the Sentinel API exposure check",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_candidate_controller_state_isolation_is_required(self) -> None:
        root = self.fixture()
        self.mutate(
            root,
            "Makefile",
            "evaluation refuses the normal Solo VPS data directory",
            "evaluation may use the normal Solo VPS data directory",
        )
        with self.assertRaises(ContractError):
            validate(root)


if __name__ == "__main__":
    unittest.main()
