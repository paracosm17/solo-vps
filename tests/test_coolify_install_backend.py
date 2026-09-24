from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validate_coolify_install_backend import ContractError, validate


ROOT = Path(__file__).resolve().parents[1]


class CoolifyInstallBackendTests(unittest.TestCase):
    def make_fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="solo-vps-coolify-install-test-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        for relative in (
            "Makefile",
            "ansible/roles/coolify/defaults/main.yml",
            "ansible/roles/coolify/tasks/install.yml",
            "ansible/roles/coolify/tasks/reconcile-runtime-access.yml",
            "ansible/roles/coolify/tasks/verify.yml",
            "ansible/roles/coolify/tasks/verify-runtime.yml",
            "ansible/roles/coolify/tasks/recover.yml",
            "ansible/playbooks/coolify.yml",
            "ansible/playbooks/recover-coolify.yml",
            "ansible/playbooks/verify-coolify.yml",
        ):
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return temp

    def mutate(self, root: Path, relative: str, old: str, new: str) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_current_backend_passes(self) -> None:
        self.assertTrue(validate(ROOT))

    def test_floating_quick_installer_is_rejected(self) -> None:
        root = self.make_fixture()
        with (root / "ansible/roles/coolify/tasks/install.yml").open("a", encoding="utf-8") as handle:
            handle.write("\n# curl -fsSL https://cdn.coollabs.io/coolify/install.sh\n")
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_checksum_enforcement_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(root, "ansible/roles/coolify/tasks/install.yml", 'checksum: "{{ item.checksum }}"', 'checksum: ""')
        with self.assertRaises(ContractError):
            validate(root)

    def test_public_exposure_verification_drift_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/verify-runtime.yml",
            "HostIp == solo_vps_coolify_management_bind_address",
            "HostIp == '0.0.0.0'",
        )
        with self.assertRaises(ContractError):
            validate(root)



    def test_non_root_parent_mode_drift_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/defaults/main.yml",
            'solo_vps_coolify_non_root_parent_mode: "0711"',
            'solo_vps_coolify_non_root_parent_mode: "0755"',
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_non_root_parent_group_drift_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/reconcile-runtime-access.yml",
            'group: root\n    mode: "{{ solo_vps_coolify_non_root_parent_mode }}"',
            'group: "{{ solo_vps_coolify_admin_gid }}"\n    mode: "{{ solo_vps_coolify_non_root_parent_mode }}"',
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_non_root_proxy_mode_drift_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/defaults/main.yml",
            'solo_vps_coolify_non_root_proxy_mode: "0700"',
            'solo_vps_coolify_non_root_proxy_mode: "0750"',
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_explicit_data_parent_creation_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/install.yml",
            "Create the host-owned Coolify data parent explicitly",
            "Let nested directory creation implicitly create the data parent",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_proxy_owner_forced_back_to_9999_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/reconcile-runtime-access.yml",
            'owner: "{{ admin.user }}"',
            'owner: "9999"',
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_non_root_runtime_reconciliation_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/playbooks/coolify.yml",
            "tasks_from: reconcile-runtime-access",
            "tasks_from: verify",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_non_root_proxy_verification_owner_drift_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/verify.yml",
            "solo_vps_coolify_proxy_state.stat.uid == solo_vps_coolify_verify_admin_uid",
            "solo_vps_coolify_proxy_state.stat.uid == 9999",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_real_admin_chdir_probe_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/verify.yml",
            'chdir: "{{ solo_vps_coolify_data_root }}/proxy"',
            'chdir: "/tmp"',
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_non_root_resource_root_mode_drift_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/defaults/main.yml",
            'solo_vps_coolify_non_root_resource_root_mode: "0710"',
            'solo_vps_coolify_non_root_resource_root_mode: "0750"',
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_applications_resource_root_cannot_be_omitted(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/defaults/main.yml",
            "solo_vps_coolify_non_root_resource_roots:\n  - /data/coolify/applications\n",
            "solo_vps_coolify_non_root_resource_roots:\n",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_sensitive_source_root_cannot_join_non_root_resource_roots(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/defaults/main.yml",
            "solo_vps_coolify_non_root_resource_roots:\n",
            "solo_vps_coolify_non_root_resource_roots:\n  - /data/coolify/source\n",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_resource_root_reconciliation_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/reconcile-runtime-access.yml",
            'loop: "{{ solo_vps_coolify_non_root_resource_roots }}"',
            'loop: []',
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_resource_root_real_chdir_probe_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/verify.yml",
            'register: solo_vps_coolify_resource_root_chdir_probes',
            'register: ignored_resource_root_probe',
        )
        with self.assertRaises(ContractError):
            validate(root)


    def test_non_root_backup_root_mode_drift_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/defaults/main.yml",
            'solo_vps_coolify_non_root_backup_root_mode: "0730"',
            'solo_vps_coolify_non_root_backup_root_mode: "0770"',
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_backup_root_reconciliation_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/reconcile-runtime-access.yml",
            'mode: "{{ solo_vps_coolify_non_root_backup_root_mode }}"',
            'mode: "0700"',
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_backup_root_access_probe_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/verify.yml",
            "Prove admin.user can write and traverse but cannot list the Coolify backup root",
            "Do not prove backup root access",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_terminal_readiness_probe_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/verify-runtime.yml",
            "http://127.0.0.1:6002/ready",
            "http://127.0.0.1:6002/not-ready",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_realtime_health_assertion_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/verify-runtime.yml",
            "solo_vps_coolify_verify_realtime.State.Health.Status == 'healthy'",
            "solo_vps_coolify_verify_realtime.State.Health.Status != 'healthy'",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_stale_pre_wait_inspect_evidence_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/verify-runtime.yml",
            "Re-inspect the Coolify application container after health wait",
            "Inspect the Coolify application container without post-wait refresh",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_explicit_unmarked_recovery_gate_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "Makefile",
            "COOLIFY_RECOVERY_CONFIRM_REQUIRED := I_HAVE_REVIEWED_THE_PARTIAL_SOLO_VPS_INSTALL",
            "COOLIFY_RECOVERY_CONFIRM_REQUIRED :=",
        )
        with self.assertRaises(ContractError):
            validate(root)


    def test_recovery_without_post_seed_key_normalization_support_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/recover.yml",
            "Find Coolify-normalized localhost private-key files after production seeding",
            "Ignore Coolify-normalized localhost private-key files after production seeding",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_recovery_without_authorized_key_proof_is_rejected(self) -> None:
        root = self.make_fixture()
        self.mutate(
            root,
            "ansible/roles/coolify/tasks/recover.yml",
            "solo_vps_coolify_recovery_authorized_keys.content | b64decode",
            "solo_vps_coolify_recovery_env_state.mode",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_marker_before_runtime_verification_is_rejected(self) -> None:
        root = self.make_fixture()
        path = root / "ansible/roles/coolify/tasks/install.yml"
        text = path.read_text(encoding="utf-8")
        marker = text[text.rfind("- name: Record successful Solo VPS ownership"):]
        text = text[:text.rfind("- name: Record successful Solo VPS ownership")]
        insert_at = text.find("- name: Verify the newly installed Coolify runtime")
        path.write_text(text[:insert_at] + marker + "\n" + text[insert_at:], encoding="utf-8")
        with self.assertRaises(ContractError):
            validate(root)


if __name__ == "__main__":
    unittest.main()
