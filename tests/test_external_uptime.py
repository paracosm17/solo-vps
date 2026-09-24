from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.external_uptime import ARTIFACT_CONFIRM_REQUIRED, CONFIRM_REQUIRED, UptimeError, build_evidence, build_plan, main


class ExternalUptimeTests(unittest.TestCase):
    def test_plan_is_provider_credential_free_and_non_mutating(self) -> None:
        plan = build_plan(health_url="https://app.example.com/healthz")
        self.assertFalse(plan["provider_credentials_required"])
        self.assertFalse(plan["network_request"])
        self.assertFalse(plan["mutation"])
        self.assertEqual(plan["monitor"]["interval_seconds"], 300)
        self.assertTrue(plan["monitor"]["provider_confirmation_retries_required"])

    def test_http_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(UptimeError, "must use https"):
            build_plan(health_url="http://app.example.com/healthz")

    def test_local_target_is_rejected(self) -> None:
        for url in (
            "https://localhost/healthz",
            "https://127.0.0.1/healthz",
            "https://10.0.0.10/healthz",
        ):
            with self.subTest(url=url), self.assertRaises(UptimeError):
                build_plan(health_url=url)

    def test_raw_or_nonstandard_port_is_rejected(self) -> None:
        for port in (8000, 6001, 6002, 8080, 8443):
            with self.subTest(port=port), self.assertRaisesRegex(UptimeError, "normal HTTPS port 443"):
                build_plan(health_url=f"https://app.example.com:{port}/healthz")

    def test_query_and_root_path_are_rejected(self) -> None:
        for url in (
            "https://app.example.com/",
            "https://app.example.com/healthz?token=secret",
        ):
            with self.subTest(url=url), self.assertRaises(UptimeError):
                build_plan(health_url=url)

    def test_faster_provider_policy_is_accepted_within_bounds(self) -> None:
        plan = build_plan(
            health_url="https://app.example.com/healthz",
            interval_seconds=60,
            timeout_seconds=5,
        )
        self.assertEqual(plan["monitor"]["interval_seconds"], 60)
        self.assertEqual(plan["monitor"]["timeout_seconds"], 5)

    def test_slower_policy_is_rejected(self) -> None:
        with self.assertRaisesRegex(UptimeError, "interval must remain between"):
            build_plan(health_url="https://app.example.com/healthz", interval_seconds=301)

    def test_whole_target_evidence_meets_v3_acceptance(self) -> None:
        evidence = build_evidence(
            proof_id="crit015-demo",
            health_url="https://app.example.com/healthz",
            exercise_mode="whole-target-shutdown",
            notification_channel="email",
            provider_artifact_sha256="a" * 64,
            notification_test_received_at="2026-08-17T19:00:00Z",
            outage_started_at="2026-08-17T20:00:00Z",
            alert_received_at="2026-08-17T20:07:00Z",
            service_restored_at="2026-08-17T20:20:00Z",
            recovery_received_at="2026-08-17T20:24:00Z",
        )
        self.assertTrue(evidence["acceptance"]["crit015_v3_acceptance_candidate"])
        self.assertTrue(evidence["exercise"]["total_host_loss_proven"])
        serialized = json.dumps(evidence)
        self.assertNotIn("app.example.com", serialized)
        self.assertNotIn("/healthz", serialized)

    def test_endpoint_only_exercise_remains_partial(self) -> None:
        evidence = build_evidence(
            proof_id="crit015-partial",
            health_url="https://app.example.com/healthz",
            exercise_mode="public-endpoint-outage",
            notification_channel="push",
            provider_artifact_sha256="b" * 64,
            notification_test_received_at="2026-08-17T19:00:00Z",
            outage_started_at="2026-08-17T20:00:00Z",
            alert_received_at="2026-08-17T20:05:00Z",
            service_restored_at="2026-08-17T20:20:00Z",
            recovery_received_at="2026-08-17T20:22:00Z",
        )
        self.assertFalse(evidence["acceptance"]["crit015_v3_acceptance_candidate"])
        self.assertFalse(evidence["exercise"]["total_host_loss_proven"])

    def test_late_alert_is_recorded_as_failed_policy(self) -> None:
        evidence = build_evidence(
            proof_id="crit015-slow",
            health_url="https://app.example.com/healthz",
            exercise_mode="whole-target-shutdown",
            notification_channel="chat",
            provider_artifact_sha256="c" * 64,
            notification_test_received_at="2026-08-17T19:00:00Z",
            outage_started_at="2026-08-17T20:00:00Z",
            alert_received_at="2026-08-17T20:12:00Z",
            service_restored_at="2026-08-17T20:20:00Z",
            recovery_received_at="2026-08-17T20:22:00Z",
        )
        self.assertFalse(evidence["exercise"]["alert_within_policy"])
        self.assertFalse(evidence["acceptance"]["crit015_v3_acceptance_candidate"])

    def test_timestamp_order_is_fail_closed(self) -> None:
        with self.assertRaisesRegex(UptimeError, "before outage_started_at"):
            build_evidence(
                proof_id="crit015-order",
                health_url="https://app.example.com/healthz",
                exercise_mode="whole-target-shutdown",
                notification_channel="email",
                provider_artifact_sha256="d" * 64,
                notification_test_received_at="2026-08-17T19:00:00Z",
                outage_started_at="2026-08-17T20:00:00Z",
                alert_received_at="2026-08-17T19:59:00Z",
                service_restored_at="2026-08-17T20:20:00Z",
                recovery_received_at="2026-08-17T20:22:00Z",
            )

    def test_record_requires_confirmation_and_writes_private_sanitized_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-uptime-") as temp:
            evidence_dir = Path(temp) / "evidence"
            argv = [
                "external_uptime.py",
                "record",
                "--health-url", "https://app.example.com/healthz",
                "--proof-id", "crit015-file",
                "--exercise-mode", "whole-target-shutdown",
                "--notification-channel", "email",
                "--provider-artifact-sha256", "e" * 64,
                "--provider-artifact-review-confirm", ARTIFACT_CONFIRM_REQUIRED,
                "--notification-test-received-at", "2026-08-17T19:00:00Z",
                "--outage-started-at", "2026-08-17T20:00:00Z",
                "--alert-received-at", "2026-08-17T20:05:00Z",
                "--service-restored-at", "2026-08-17T20:20:00Z",
                "--recovery-received-at", "2026-08-17T20:22:00Z",
                "--confirm", CONFIRM_REQUIRED,
                "--evidence-dir", str(evidence_dir),
            ]
            from unittest.mock import patch

            with patch("sys.argv", argv), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(), 0)
            path = evidence_dir / "external-uptime-evidence.json"
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(evidence_dir.stat().st_mode & 0o777, 0o700)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("app.example.com", text)
            self.assertNotIn("/healthz", text)

    def test_record_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-uptime-") as temp:
            evidence_dir = Path(temp) / "evidence"
            evidence_dir.mkdir(mode=0o700)
            existing = evidence_dir / "external-uptime-evidence.json"
            existing.write_text("keep\n", encoding="utf-8")
            os.chmod(existing, 0o600)
            argv = [
                "external_uptime.py",
                "record",
                "--health-url", "https://app.example.com/healthz",
                "--proof-id", "crit015-overwrite",
                "--exercise-mode", "public-endpoint-outage",
                "--notification-channel", "email",
                "--provider-artifact-sha256", "e" * 64,
                "--provider-artifact-review-confirm", ARTIFACT_CONFIRM_REQUIRED,
                "--notification-test-received-at", "2026-08-17T19:00:00Z",
                "--outage-started-at", "2026-08-17T20:00:00Z",
                "--alert-received-at", "2026-08-17T20:05:00Z",
                "--service-restored-at", "2026-08-17T20:20:00Z",
                "--recovery-received-at", "2026-08-17T20:22:00Z",
                "--confirm", CONFIRM_REQUIRED,
                "--evidence-dir", str(evidence_dir),
            ]
            from unittest.mock import patch

            with patch("sys.argv", argv), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(), 2)
            self.assertEqual(existing.read_text(encoding="utf-8"), "keep\n")


if __name__ == "__main__":
    unittest.main()
