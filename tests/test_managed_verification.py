"""Exercise the real phase-selection playbook with isolated, read-only stub roles."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = os.environ.get("SOLO_VPS_TEST_ANSIBLE_PLAYBOOK") or shutil.which("ansible-playbook")


@unittest.skipUnless(os.name == "posix" and ANSIBLE, "requires a Linux Ansible controller")
class ManagedVerificationTests(unittest.TestCase):
    def verify(self, markers=(), *, ssh_healthy=True, coolify_healthy=True):
        with tempfile.TemporaryDirectory(prefix="solo-vps-phase-test-") as directory:
            root = Path(directory)
            (root / "playbooks").mkdir()
            shutil.copy2(ROOT / "ansible/playbooks/verify-managed.yml", root / "playbooks/verify-managed.yml")
            paths = {name: root / "state" / name for name in ("ssh", "dropin", "data", "managed", "installing", "upgrading")}
            (root / "state").mkdir()
            for name in markers:
                paths[name].touch()
            defaults = {
                "ssh": {"solo_vps_sshd_hardened_marker": str(paths["ssh"]), "solo_vps_sshd_hardening_path": str(paths["dropin"])},
                "coolify": {
                    "solo_vps_coolify_managed_marker": str(paths["managed"]),
                    "solo_vps_coolify_data_root": str(paths["data"]),
                    "solo_vps_coolify_pending_marker": str(paths["installing"]),
                    "solo_vps_coolify_upgrade_pending_marker": str(paths["upgrading"]),
                },
            }
            for role, variables in defaults.items():
                base = root / "roles" / role
                (base / "defaults").mkdir(parents=True)
                (base / "tasks").mkdir()
                (base / "defaults/main.yml").write_text(yaml.safe_dump(variables))
                (base / "tasks/verify.yml").write_text(yaml.safe_dump([{
                    "name": f"{role.upper()}_VERIFIER_EXECUTED",
                    "ansible.builtin.assert": {"that": [f"test_{role}_healthy | bool"]},
                }]))
            extra = root / "test-vars.yml"
            extra.write_text(yaml.safe_dump({
                "ansible_become": False,
                "test_ssh_healthy": ssh_healthy,
                "test_coolify_healthy": coolify_healthy,
            }))
            environment = os.environ.copy()
            environment["ANSIBLE_ROLES_PATH"] = str(root / "roles")
            environment["ANSIBLE_CONFIG"] = str(ROOT / "ansible/ansible.cfg")
            return subprocess.run(
                [str(ANSIBLE), "-i", "localhost,", "-c", "local", str(root / "playbooks/verify-managed.yml"), "-e", f"@{extra}"],
                env=environment, text=True, capture_output=True, timeout=90, check=False,
            )

    def test_baseline_does_not_require_uninstalled_components(self):
        result = self.verify(ssh_healthy=False, coolify_healthy=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("SSH_VERIFIER_EXECUTED", result.stdout)
        self.assertNotIn("COOLIFY_VERIFIER_EXECUTED", result.stdout)

    def test_hardened_marker_detects_broken_or_deleted_dropin(self):
        result = self.verify(["ssh"], ssh_healthy=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SSH_VERIFIER_EXECUTED", result.stdout)

    def test_managed_coolify_must_be_healthy(self):
        result = self.verify(["data", "managed"], coolify_healthy=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("COOLIFY_VERIFIER_EXECUTED", result.stdout)

    def test_all_completed_phases_pass_when_healthy(self):
        result = self.verify(["ssh", "dropin", "data", "managed"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_partial_install_upgrade_and_lost_ownership_are_not_healthy(self):
        for markers in (["data", "installing"], ["data", "managed", "upgrading"], ["data"]):
            with self.subTest(markers=markers):
                result = self.verify(markers)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Coolify is incomplete or unmanaged", result.stdout)
