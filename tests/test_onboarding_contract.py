from __future__ import annotations

import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from scripts.ensure_ssh_key import ensure_key
from scripts.prepare_access import AccessError, append_unique, require_distinct_same_vps_keys
from scripts.configure_human_admin_key import HumanKeyError, configure
from scripts.handoff_admin_workspace import (
    admin_data_parents_need_repair,
    copy_operator_state,
    copy_workspace,
    ensure_admin_data_parents,
    ignore_workspace,
)
from scripts.validate_onboarding_contract import ContractError, validate


ROOT = pathlib.Path(__file__).resolve().parents[1]


class OnboardingContractTests(unittest.TestCase):
    def fixture(self) -> pathlib.Path:
        temp = pathlib.Path(tempfile.mkdtemp(prefix="solo-vps-onboarding-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        for relative in (
            "Makefile",
            "README.md",
            "docs/quick-start.md",
            "docs/quick-start.ru.md",
            "config/config.example.yml",
            "docs/clean-vps-test.md",
            "scripts/controller_setup.sh",
            "scripts/ensure_ssh_key.py",
            "scripts/prepare_access.py",
            "scripts/handoff_admin_workspace.py",
            "scripts/configure_human_admin_key.py",
            "scripts/doctor.py",
            "ansible/roles/users/tasks/assert-config.yml",
            "ansible/roles/users/tasks/load-public-key.yml",
            "ansible/roles/users/tasks/main.yml",
            "ansible/roles/users/tasks/verify.yml",
            "ansible/roles/ssh/tasks/main.yml",
        ):
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return temp

    def mutate(self, root: pathlib.Path, relative: str, old: str, new: str) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_current_contract_passes(self) -> None:
        validate(ROOT)

    def test_default_key_is_created_once_and_reused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-key-") as tmp:
            private = pathlib.Path(tmp) / ".ssh/id_ed25519"

            def fake_run(argv, **kwargs):
                self.assertEqual(argv[0], "ssh-keygen")
                target = pathlib.Path(argv[argv.index("-f") + 1])
                target.write_text("test-private-key-material\n", encoding="utf-8")
                pathlib.Path(f"{target}.pub").write_text(
                    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestOnlyKey solo-vps-test\n",
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0)

            with mock.patch("scripts.ensure_ssh_key.subprocess.run", side_effect=fake_run) as run:
                public, action = ensure_key(private)
                self.assertEqual(action, "created")
                private_bytes = private.read_bytes()
                public_bytes = public.read_bytes()
                public2, action2 = ensure_key(private)

            self.assertEqual(run.call_count, 1)
            self.assertEqual(action2, "existing")
            self.assertEqual(public2, public)
            self.assertEqual(private.read_bytes(), private_bytes)
            self.assertEqual(public.read_bytes(), public_bytes)

    def test_same_vps_human_key_must_differ_from_automation_key(self) -> None:
        key = "ssh-ed25519 AAAATEST distinct-boundary"
        with self.assertRaises(AccessError):
            require_distinct_same_vps_keys(key, key)
        require_distinct_same_vps_keys(key, "ssh-ed25519 AAAAHUMAN workstation")

    def test_append_unique_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-access-") as tmp:
            path = pathlib.Path(tmp) / "authorized_keys"
            self.assertTrue(append_unique(path, "ssh-ed25519 AAAATEST user@example", 0o600))
            self.assertFalse(append_unique(path, "ssh-ed25519 AAAATEST user@example", 0o600))
            self.assertEqual(path.read_text(encoding="utf-8").count("AAAATEST"), 1)



    def test_human_admin_key_helper_is_atomic_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-human-key-") as tmp:
            config = pathlib.Path(tmp) / "config.yml"
            config.write_text("admin:\n  user: ops\n  ssh_public_key_file: ~/.ssh/id_ed25519.pub\n  human_ssh_public_key: ''\n", encoding="utf-8")
            config.chmod(0o600)
            key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestOnlyHumanKey workstation@test"
            self.assertEqual(configure(config, key + "\n"), "configured")
            self.assertEqual(configure(config, key + "\n"), "already-configured")
            self.assertIn(key, config.read_text(encoding="utf-8"))
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)

    def test_human_admin_key_helper_rejects_private_key_material(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-human-key-") as tmp:
            config = pathlib.Path(tmp) / "config.yml"
            config.write_text("admin: {}\n", encoding="utf-8")
            with self.assertRaises(HumanKeyError):
                configure(config, "-----BEGIN OPENSSH " + "PRIVATE" + chr(32) + "KEY-----\nsecret\n")


    def test_missing_human_key_authorized_keys_apply_is_rejected(self) -> None:
        root = self.fixture()
        self.mutate(
            root,
            "ansible/roles/users/tasks/main.yml",
            '    - "{{ solo_vps_human_admin_authorized_key }}"\n',
            "",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_workstation_login_gate_is_rejected(self) -> None:
        root = self.fixture()
        self.mutate(
            root,
            "Makefile",
            "SSH_HARDENING_ADMIN_LOGIN_CONFIRM_REQUIRED := I_HAVE_VERIFIED_WORKSTATION_ADMIN_LOGIN\n",
            "",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_admin_handoff_copy_keeps_checkout_source_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-handoff-") as tmp:
            base = pathlib.Path(tmp)
            source = base / "source"
            destination = base / "admin" / "solo-vps"
            (source / ".venv/qa").mkdir(parents=True)
            (source / ".venv/qa/should-not-copy").write_text("x", encoding="utf-8")
            (source / "config").mkdir(parents=True)
            (source / "config/config.yml").write_text("server: {}\n", encoding="utf-8")
            (source / "ansible/inventories/local").mkdir(parents=True)
            (source / "ansible/inventories/local/hosts.yml").write_text("all: {}\n", encoding="utf-8")
            (source / ".sops.yaml").write_text("legacy\n", encoding="utf-8")
            (source / "secrets/recipients").mkdir(parents=True)
            (source / "secrets/recipients/production.txt").write_text("legacy\n", encoding="utf-8")
            destination.parent.mkdir(parents=True)

            with mock.patch("scripts.handoff_admin_workspace.chown_tree"):
                copy_workspace(source, destination, 1000, 1000)

            self.assertFalse((destination / ".venv").exists())
            self.assertFalse((destination / "config/config.yml").exists())
            self.assertFalse((destination / "ansible/inventories/local").exists())
            self.assertFalse((destination / ".sops.yaml").exists())
            self.assertFalse((destination / "secrets/recipients/production.txt").exists())
            self.assertFalse(any(path.name.startswith(".admin-workspace") for path in destination.rglob("*")))

    def test_admin_handoff_copies_operator_state_outside_checkout(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-handoff-state-") as tmp:
            base = pathlib.Path(tmp)
            config = base / "root-state/config/config.yml"
            inventory = base / "root-state/config/hosts.yml"
            admin_state = base / "admin-state"
            config.parent.mkdir(parents=True)
            config.write_text("server: {}\n", encoding="utf-8")
            inventory.write_text("all: {}\n", encoding="utf-8")
            with mock.patch("scripts.handoff_admin_workspace.os.chown"):
                config_action, inventory_action = copy_operator_state(config, inventory, admin_state, 1000, 1000)
            self.assertEqual(config_action, "copied")
            self.assertEqual(inventory_action, "copied")
            self.assertEqual((admin_state / "config/config.yml").read_text(), "server: {}\n")
            self.assertEqual((admin_state / "config/hosts.yml").read_text(), "all: {}\n")

    def test_admin_handoff_keeps_default_xdg_parents_owned_by_admin(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-admin-xdg-") as tmp:
            admin_home = pathlib.Path(tmp) / "home/ops"
            admin_home.mkdir(parents=True)
            local = admin_home / ".local"
            share = local / "share"
            local.mkdir()
            share.mkdir()

            observed: list[tuple[pathlib.Path, int, int]] = []
            real_stat = pathlib.Path.stat

            def fake_chown(path, uid, gid):
                observed.append((pathlib.Path(path), uid, gid))

            def fake_stat(path, *args, **kwargs):
                current = real_stat(path, *args, **kwargs)
                if pathlib.Path(path) in (local, share):
                    return mock.Mock(st_mode=current.st_mode, st_uid=0, st_gid=0)
                return current

            with mock.patch("scripts.handoff_admin_workspace.os.chown", side_effect=fake_chown):
                with mock.patch("pathlib.Path.stat", side_effect=fake_stat, autospec=True):
                    ensure_admin_data_parents(admin_home, 1000, 1000)

            self.assertTrue(local.is_dir())
            self.assertTrue(share.is_dir())
            self.assertEqual(observed, [(local, 1000, 1000), (share, 1000, 1000)])

    def test_admin_handoff_detects_legacy_root_owned_xdg_parent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-admin-xdg-check-") as tmp:
            admin_home = pathlib.Path(tmp) / "home/ops"
            local = admin_home / ".local"
            share = local / "share"
            share.mkdir(parents=True)
            real_stat = pathlib.Path.stat

            def fake_stat(path, *args, **kwargs):
                current = real_stat(path, *args, **kwargs)
                if pathlib.Path(path) == share:
                    return mock.Mock(st_mode=current.st_mode, st_uid=0, st_gid=0)
                return mock.Mock(st_mode=current.st_mode, st_uid=1000, st_gid=1000)

            with mock.patch("pathlib.Path.stat", side_effect=fake_stat, autospec=True):
                self.assertTrue(admin_data_parents_need_repair(admin_home, 1000, 1000))

    def test_admin_handoff_excludes_non_relocatable_venv(self) -> None:
        ignored = ignore_workspace("/tmp/source", [".venv", "README.md", "__pycache__", "file.pyc"])
        self.assertIn(".venv", ignored)
        self.assertIn("__pycache__", ignored)
        self.assertIn("file.pyc", ignored)
        self.assertNotIn("README.md", ignored)

    def test_missing_admin_handoff_from_ssh_harden_is_rejected(self) -> None:
        root = self.fixture()
        self.mutate(
            root,
            "Makefile",
            "\t@$(MAKE) --no-print-directory admin-handoff\n",
            "",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_admin_handoff_must_prepare_new_workspace_before_access_and_doctor(self) -> None:
        root = self.fixture()
        self.mutate(
            root,
            "scripts/handoff_admin_workspace.py",
            '        run_as_admin(admin_user, workspace, ["make", "setup"])\n',
            "",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_setup_target_is_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, "Makefile", "setup: ##", "first-run: ##")
        with self.assertRaises(ContractError):
            validate(root)

    def test_version_specific_venv_package_is_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, "scripts/controller_setup.sh", "python3-venv", "python3.12-venv")
        with self.assertRaises(ContractError):
            validate(root)

    def test_non_utc_default_is_rejected(self) -> None:
        root = self.fixture()
        self.mutate(root, "config/config.example.yml", "timezone: UTC", "timezone: Europe/Moscow")
        with self.assertRaises(ContractError):
            validate(root)

    def test_access_policy_weakening_is_rejected(self) -> None:
        root = self.fixture()
        path = root / "scripts/prepare_access.py"
        path.write_text(path.read_text(encoding="utf-8") + "\n# StrictHostKeyChecking=no\n", encoding="utf-8")
        with self.assertRaises(ContractError):
            validate(root)


if __name__ == "__main__":
    unittest.main()
