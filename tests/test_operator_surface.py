from __future__ import annotations

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.operator_lifecycle import choose_bootstrap_user, apply_host, LifecycleError
from scripts.validate_operator_surface import ContractError, validate


ROOT = Path(__file__).resolve().parents[1]


class OperatorLifecycleTests(unittest.TestCase):
    def test_bootstrap_user_preserves_existing_provider_identity(self) -> None:
        self.assertEqual(choose_bootstrap_user("ubuntu", "ops", None), "ubuntu")
        self.assertEqual(choose_bootstrap_user("root", "ops", "ubuntu"), "ubuntu")
        self.assertIsNone(choose_bootstrap_user("ops", "ops", None))
        self.assertIsNone(choose_bootstrap_user("ops", "ops", "root"))

    def test_apply_runs_bounded_sequence_and_switches_to_admin(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-lifecycle-") as tmp:
            root = Path(tmp)
            config = root / "config.yml"
            inventory = root / "hosts.yml"
            config.write_text(
                "server:\n  host: 198.51.100.10\nadmin:\n  user: ops\n  ssh_public_key_file: ~/.ssh/id_ed25519.pub\n  human_ssh_public_key: ssh-ed25519 AAAAHUMAN test\nfirewall:\n  public_ports: [80, 443]\n",
                encoding="utf-8",
            )
            inventory.write_text(
                "all:\n  hosts:\n    solo_vps:\n      ansible_host: 198.51.100.10\n      ansible_user: root\n",
                encoding="utf-8",
            )
            calls: list[tuple[str, ...]] = []

            def fake_synchronize(config_path, inventory_path, mode, explicit_user):
                if mode == "bootstrap":
                    return "198.51.100.10", explicit_user, False
                inventory.write_text(
                    "all:\n  hosts:\n    solo_vps:\n      ansible_host: 198.51.100.10\n      ansible_user: ops\n",
                    encoding="utf-8",
                )
                return "198.51.100.10", "ops", True

            with mock.patch("scripts.operator_lifecycle.synchronize", side_effect=fake_synchronize):
                with contextlib.redirect_stdout(io.StringIO()):
                    apply_host(root, config, inventory, None, lambda argv: calls.append(tuple(argv)))

            targets = [call[2] for call in calls]
            self.assertTrue(all(call[3].startswith("CONFIG=") and call[4].startswith("INVENTORY=") for call in calls))
            self.assertEqual(targets, ["prepare-access", "doctor", "bootstrap", "doctor", "admin-handoff", "verify", "audit"])

    def test_resume_after_admin_switch_never_prepares_bootstrap_access(self) -> None:
        """An interrupted handoff is resumed using admin, even in a root shell."""
        with tempfile.TemporaryDirectory(prefix="solo-vps-resume-") as tmp:
            root = Path(tmp)
            config, inventory = root / "config.yml", root / "hosts.yml"
            config.write_text("server:\n  host: new.example.com\nadmin:\n  user: ops\n", encoding="utf-8")
            inventory.write_text("all:\n  hosts:\n    solo_vps:\n      ansible_host: old.example.com\n      ansible_user: ops\n", encoding="utf-8")
            calls = []
            with mock.patch("scripts.operator_lifecycle.synchronize", return_value=("new.example.com", "ops", True)) as sync:
                with contextlib.redirect_stdout(io.StringIO()):
                    apply_host(root, config, inventory, "root", lambda argv: calls.append(tuple(argv)))
            self.assertEqual([call[2] for call in calls], ["doctor", "bootstrap", "doctor", "admin-handoff", "verify", "audit"])
            self.assertTrue(all(call.args[2:] == ("admin", None) for call in sync.call_args_list))

    def test_failed_bootstrap_does_not_switch_inventory_or_handoff(self) -> None:
        with mock.patch("scripts.operator_lifecycle.configured_admin", return_value="ops"), \
             mock.patch("scripts.operator_lifecycle.inventory_user", return_value="root"), \
             mock.patch("scripts.operator_lifecycle.synchronize", return_value=("example.com", "root", False)) as sync:
            calls = []
            def fail_bootstrap(argv):
                calls.append(argv[2])
                if argv[2] == "bootstrap":
                    raise LifecycleError("interrupted")
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(LifecycleError):
                apply_host(ROOT, ROOT / "config.yml", ROOT / "hosts.yml", None, fail_bootstrap)
            self.assertEqual(calls, ["prepare-access", "doctor", "bootstrap"])
            self.assertEqual(sync.call_count, 1)
            self.assertEqual(sync.call_args.args[2:], ("bootstrap", "root"))


class OperatorSurfaceContractTests(unittest.TestCase):
    def fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="solo-vps-operator-surface-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        for relative in ("Makefile", "README.md", "docs/quick-start.md", "scripts/operator_lifecycle.py"):
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return temp

    def test_current_contract_passes(self) -> None:
        validate(ROOT)

    def test_default_help_rejects_internal_target_leak(self) -> None:
        root = self.fixture()
        path = root / "Makefile"
        text = path.read_text(encoding="utf-8")
        marker = "\t\t'  make help-all    Complete documented Make target catalog' \\\n"
        self.assertIn(marker, text)
        injected = "\t\t'  make validate-observability-runtime' \\\n" + marker
        path.write_text(text.replace(marker, injected, 1), encoding="utf-8")
        with self.assertRaises(ContractError):
            validate(root)

    def test_missing_primary_apply_is_rejected(self) -> None:
        root = self.fixture()
        path = root / "Makefile"
        text = path.read_text(encoding="utf-8")
        self.assertIn("apply:", text)
        path.write_text(text.replace("apply:", "apply-internal:", 1), encoding="utf-8")
        with self.assertRaises(ContractError):
            validate(root)


if __name__ == "__main__":
    unittest.main()
