from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import yaml

from scripts.configure_inventory import InventoryConfigError, synchronize


ROOT = Path(__file__).resolve().parents[1]


class InventoryConfigTests(unittest.TestCase):
    def fixture(self, base: Path) -> tuple[Path, Path]:
        config = base / "config.yml"
        inventory = base / "hosts.yml"
        config.write_text(
            (ROOT / "config/config.example.yml")
            .read_text(encoding="utf-8")
            .replace("203.0.113.10", "198.51.100.25")
            .replace("solo-vps-01", "vps-01.example"),
            encoding="utf-8",
        )
        inventory.write_text(
            (ROOT / "ansible/inventories/example/hosts.yml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return config, inventory

    def test_bootstrap_syncs_host_and_explicit_user(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-inventory-") as tmp:
            config, inventory = self.fixture(Path(tmp))
            host, user, changed = synchronize(config, inventory, "bootstrap", "ubuntu")
            self.assertTrue(changed)
            self.assertEqual(host, "198.51.100.25")
            self.assertEqual(user, "ubuntu")
            data = yaml.safe_load(inventory.read_text(encoding="utf-8"))
            self.assertEqual(
                data["all"]["hosts"],
                {"solo_vps": {"ansible_host": "198.51.100.25", "ansible_user": "ubuntu"}},
            )
            self.assertEqual(inventory.stat().st_mode & 0o777, 0o600)

    def test_admin_sync_uses_config_admin_user(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-inventory-") as tmp:
            config, inventory = self.fixture(Path(tmp))
            synchronize(config, inventory, "bootstrap", "root")
            host, user, changed = synchronize(config, inventory, "admin", None)
            self.assertTrue(changed)
            self.assertEqual(host, "198.51.100.25")
            self.assertEqual(user, "ops")
            data = yaml.safe_load(inventory.read_text(encoding="utf-8"))
            vars_ = data["all"]["hosts"]["solo_vps"]
            self.assertEqual(vars_["ansible_host"], "198.51.100.25")
            self.assertEqual(vars_["ansible_user"], "ops")

    def test_admin_sync_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-inventory-") as tmp:
            config, inventory = self.fixture(Path(tmp))
            synchronize(config, inventory, "admin", None)
            before = inventory.read_bytes()
            _, _, changed = synchronize(config, inventory, "admin", None)
            self.assertFalse(changed)
            self.assertEqual(inventory.read_bytes(), before)

    def test_invalid_bootstrap_user_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-inventory-") as tmp:
            config, inventory = self.fixture(Path(tmp))
            with self.assertRaises(InventoryConfigError):
                synchronize(config, inventory, "bootstrap", "bad user")

    def test_inventory_symlink_is_rejected_on_write(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-inventory-") as tmp:
            base = Path(tmp)
            config, inventory = self.fixture(base)
            target = base / "target.yml"
            target.write_text(inventory.read_text(encoding="utf-8"), encoding="utf-8")
            inventory.unlink()
            inventory.symlink_to(target)
            with self.assertRaises(InventoryConfigError):
                synchronize(config, inventory, "admin", None)

    def test_m14_host_targets_require_managed_admin_gate(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        for target in ("backup-tooling", "verify-backup-tooling", "backup-readiness"):
            self.assertIn(f"{target}: doctor-admin-local", makefile)


if __name__ == "__main__":
    unittest.main()
