from __future__ import annotations

import copy
import pathlib
import tempfile
import unittest
from unittest import mock

import yaml

from scripts.doctor_platform import PlatformDoctorError, inspect_capabilities
from scripts.secrets_toolchain import ToolchainError

ROOT = pathlib.Path(__file__).resolve().parents[1]


class PlatformDoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = yaml.safe_load((ROOT / "config/config.example.yml").read_text())
        self.inventory = yaml.safe_load((ROOT / "ansible/inventories/example/hosts.yml").read_text())

    def write_inputs(self, directory: pathlib.Path, config: dict, inventory: dict) -> tuple[pathlib.Path, pathlib.Path]:
        config_path = directory / "config.yml"
        inventory_path = directory / "hosts.yml"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        inventory_path.write_text(yaml.safe_dump(inventory, sort_keys=False), encoding="utf-8")
        return config_path, inventory_path

    def statuses(self, config: dict | None = None, inventory: dict | None = None) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            config_path, inventory_path = self.write_inputs(
                tmp_path,
                config or self.config,
                inventory or self.inventory,
            )
            with mock.patch("scripts.doctor_platform.default_cache_root", return_value=tmp_path / "cache"):
                results = inspect_capabilities(ROOT, config_path, inventory_path)
        return {result.name: result.status for result in results}

    def test_example_optional_capabilities_reflect_clean_public_source(self) -> None:
        statuses = self.statuses()
        self.assertEqual(statuses["admin_activation_path"], "PENDING")
        self.assertEqual(statuses["backup_policy"], "NOT_CONFIGURED")
        self.assertEqual(statuses["secrets_policy"], "NOT_CONFIGURED")
        self.assertIn(statuses["secrets_toolchain"], {"NOT_INSTALLED", "UNSUPPORTED"})

    def test_admin_inventory_path_becomes_ready(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        host_vars = next(iter(inventory["all"]["hosts"].values()))
        host_vars["ansible_user"] = self.config["admin"]["user"]
        self.assertEqual(self.statuses(inventory=inventory)["admin_activation_path"], "READY")

    def test_realistic_backup_metadata_is_validated(self) -> None:
        config = copy.deepcopy(self.config)
        config["backup"]["repository"]["endpoint"] = "https://storage.example.net"
        self.assertEqual(self.statuses(config=config)["backup_policy"], "READY")

    def test_invalid_configured_backup_metadata_is_fatal(self) -> None:
        config = copy.deepcopy(self.config)
        config["backup"]["repository"]["endpoint"] = "http://storage.example.net"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            config_path, inventory_path = self.write_inputs(tmp_path, config, self.inventory)
            with mock.patch("scripts.doctor_platform.default_cache_root", return_value=tmp_path / "cache"):
                with self.assertRaises(PlatformDoctorError):
                    inspect_capabilities(ROOT, config_path, inventory_path)

    def test_missing_backup_block_is_not_an_error(self) -> None:
        config = copy.deepcopy(self.config)
        del config["backup"]
        self.assertEqual(self.statuses(config=config)["backup_policy"], "NOT_CONFIGURED")

    def test_invalid_toolchain_manifest_is_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            config_path, inventory_path = self.write_inputs(tmp_path, self.config, self.inventory)
            with mock.patch(
                "scripts.doctor_platform.load_manifest",
                side_effect=ToolchainError("manifest drift"),
            ):
                with self.assertRaisesRegex(PlatformDoctorError, "manifest drift"):
                    inspect_capabilities(ROOT, config_path, inventory_path)

    def test_corrupt_existing_toolchain_is_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            config_path, inventory_path = self.write_inputs(tmp_path, self.config, self.inventory)
            fake_target = tmp_path / "cache" / "existing"
            fake_target.mkdir(parents=True)
            with (
                mock.patch("scripts.doctor_platform.default_cache_root", return_value=tmp_path / "cache"),
                mock.patch("scripts.doctor_platform.install_dir", return_value=fake_target),
                mock.patch(
                    "scripts.doctor_platform.check_installation",
                    side_effect=ToolchainError("tampered cache"),
                ),
            ):
                with self.assertRaisesRegex(PlatformDoctorError, "tampered cache"):
                    inspect_capabilities(ROOT, config_path, inventory_path)

    def test_make_doctor_sequences_remote_preflight_after_local_report(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn(
            "doctor: doctor-platform-local ## Run platform-aware local diagnostics, then remote preflight\n",
            makefile,
        )
        self.assertIn("\t@$(MAKE) --no-print-directory preflight\n", makefile)
        self.assertNotIn("doctor: doctor-platform-local preflight", makefile)

    def test_platform_report_does_not_require_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            config_path, inventory_path = self.write_inputs(tmp_path, self.config, self.inventory)
            with (
                mock.patch("scripts.doctor_platform.default_cache_root", return_value=tmp_path / "cache"),
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("network must not be used")),
            ):
                results = inspect_capabilities(ROOT, config_path, inventory_path)
            self.assertTrue(results)


if __name__ == "__main__":
    unittest.main()
