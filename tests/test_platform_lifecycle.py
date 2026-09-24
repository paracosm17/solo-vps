from __future__ import annotations

import unittest
from pathlib import Path

from scripts.platform_lifecycle import LifecycleError, build_plan, load_policy, parse_engine_version


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/contracts/platform-lifecycle-policy.yml"


class PlatformLifecycleTests(unittest.TestCase):
    def test_plan_is_offline_non_mutating_and_exact(self) -> None:
        plan = build_plan(load_policy(POLICY), "29.7.2")
        self.assertFalse(plan["network_request"])
        self.assertFalse(plan["mutation"])
        self.assertTrue(plan["docker"]["supported"])
        self.assertEqual(plan["coolify"]["upgrade_path"], "4.1.1 -> 4.1.2")
        self.assertFalse(plan["coolify"]["fresh_restic_backup_required"])
        self.assertFalse(plan["coolify"]["offsite_instance_database_backup_required"])
        self.assertTrue(plan["coolify"]["local_control_plane_checkpoint_required"])
        self.assertFalse(plan["coolify"]["automatic_downgrade_on_failure"])

    def test_docker_debian_epoch_version_parses(self) -> None:
        self.assertEqual(parse_engine_version("5:29.7.2-1~ubuntu.24.04~noble"), (29, 7, 2))

    def test_docker_plain_version_parses(self) -> None:
        self.assertEqual(parse_engine_version("29.7.2"), (29, 7, 2))

    def test_future_docker_major_is_reported_unsupported(self) -> None:
        plan = build_plan(load_policy(POLICY), "30.0.0")
        self.assertFalse(plan["docker"]["supported"])
        self.assertEqual(plan["docker"]["observed_major"], 30)

    def test_old_docker_major_is_reported_unsupported(self) -> None:
        plan = build_plan(load_policy(POLICY), "28.5.2")
        self.assertFalse(plan["docker"]["supported"])

    def test_unparseable_docker_version_fails_closed(self) -> None:
        with self.assertRaises(LifecycleError):
            parse_engine_version("latest")


if __name__ == "__main__":
    unittest.main()
