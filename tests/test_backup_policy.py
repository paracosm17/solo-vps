from __future__ import annotations

import copy
import pathlib
import unittest

import yaml

from scripts.validate_backup_policy import BackupPolicyError, validate

ROOT = pathlib.Path(__file__).resolve().parents[1]


class BackupPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = yaml.safe_load((ROOT / "config/config.example.yml").read_text())
        self.defaults = yaml.safe_load((ROOT / "ansible/roles/backup/defaults/main.yml").read_text())

    def test_example_policy_is_valid(self) -> None:
        repository = validate(self.config, self.defaults, allow_documentation_endpoint=True)
        self.assertEqual(repository, "s3:https://s3.example.com/solo-vps-backups/solo-vps/solo-vps-01")

    def test_documentation_endpoint_is_rejected_for_local_use(self) -> None:
        with self.assertRaises(BackupPolicyError):
            validate(self.config, self.defaults)

    def test_http_endpoint_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["backup"]["repository"]["endpoint"] = "http://storage.example.net"
        with self.assertRaises(BackupPolicyError):
            validate(config, self.defaults)

    def test_same_host_endpoint_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["backup"]["repository"]["endpoint"] = "https://203.0.113.10"
        with self.assertRaises(BackupPolicyError):
            validate(config, self.defaults)

    def test_credentials_in_public_config_are_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["backup"]["repository"]["endpoint"] = "https://storage.example.net"
        config["backup"]["repository"]["access_key_id"] = "example"
        with self.assertRaises(BackupPolicyError):
            validate(config, self.defaults)

    def test_live_docker_storage_source_is_rejected(self) -> None:
        defaults = copy.deepcopy(self.defaults)
        defaults["solo_vps_backup_sources"] = ["/var/lib/docker/volumes"]
        config = copy.deepcopy(self.config)
        config["backup"]["repository"]["endpoint"] = "https://storage.example.net"
        with self.assertRaises(BackupPolicyError):
            validate(config, defaults)

    def test_retention_drift_is_rejected(self) -> None:
        defaults = copy.deepcopy(self.defaults)
        defaults["solo_vps_backup_retention"]["keep_daily"] = 30
        config = copy.deepcopy(self.config)
        config["backup"]["repository"]["endpoint"] = "https://storage.example.net"
        with self.assertRaises(BackupPolicyError):
            validate(config, defaults)


if __name__ == "__main__":
    unittest.main()
