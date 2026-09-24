from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

import yaml

from scripts.validate_config import ConfigError, validate_config


ROOT = Path(__file__).resolve().parents[1]


class SmallVpsCapacityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = yaml.safe_load((ROOT / "config/config.example.yml").read_text(encoding="utf-8"))

    def test_default_and_explicit_false_preserve_supported_profile(self) -> None:
        validate_config(self.config)
        self.config["evaluation"] = {"allow_small_vps": False}
        validate_config(self.config)

    def test_disposable_small_vps_opt_in_is_boolean(self) -> None:
        self.config["evaluation"] = {"allow_small_vps": True}
        validate_config(self.config)

    def test_malformed_opt_in_fails_closed(self) -> None:
        for value in ("true", 1, None, [], {}, {"allow_small_vps": True, "skip_ram": True}):
            with self.subTest(value=value):
                config = deepcopy(self.config)
                config["evaluation"] = value
                with self.assertRaises(ConfigError):
                    validate_config(config)

    def test_both_capacity_gates_share_a_guarded_profile(self) -> None:
        role = ROOT / "ansible/roles/coolify/tasks"
        policy = (role / "capacity-policy.yml").read_text(encoding="utf-8")
        bootstrap = (role / "capacity.yml").read_text(encoding="utf-8")
        readiness = (role / "readiness.yml").read_text(encoding="utf-8")
        defaults = (ROOT / "ansible/roles/coolify/defaults/main.yml").read_text(encoding="utf-8")
        for gate in (bootstrap, readiness):
            self.assertIn("ansible.builtin.import_tasks: capacity-policy.yml", gate)
            self.assertIn("solo_vps_coolify_required_cpu_count | int", gate)
            self.assertIn("solo_vps_coolify_required_free_disk_bytes | int", gate)
            self.assertIn("solo_vps_coolify_minimum_memory_mb", gate)
        self.assertIn("solo_vps_coolify_minimum_cpu_count: 2", defaults)
        self.assertIn("solo_vps_coolify_minimum_free_disk_bytes: 32212254720", defaults)
        self.assertIn("10737418240", policy)
        self.assertIn("UNSUPPORTED evaluation only", policy)


if __name__ == "__main__":
    unittest.main()
