from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.prove_disposable_clean_target import (
    CONFIRMATION,
    PROVIDER_RECOVERY_CONFIRMATION,
    ProofError,
    configured_production_host,
    parse_recap,
    refuse_production_or_local_target,
    sanitize_failure,
    validate_inputs,
    write_evidence,
)


class DisposableCleanTargetUnitTests(unittest.TestCase):
    def args(self, root: Path) -> argparse.Namespace:
        identity = root / "bootstrap"
        identity.write_text("private-test-placeholder\n", encoding="utf-8")
        return argparse.Namespace(
            confirm=CONFIRMATION,
            provider_recovery_confirm=PROVIDER_RECOVERY_CONFIRMATION,
            target_id="clean-target-123456",
            host_key_sha256="SHA256:abcdefghijklmnopqrstuvwxyzABCDEFGH1234567890=",
            bootstrap_identity=identity,
            bootstrap_user="root",
            admin_user="ops",
        )

    def test_inputs_accept_explicit_safety_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            validate_inputs(self.args(Path(tmp)))

    def test_inputs_reject_missing_disposable_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp))
            args.confirm = "yes"
            with self.assertRaises(ProofError):
                validate_inputs(args)

    def test_inputs_reject_missing_provider_recovery_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp))
            args.provider_recovery_confirm = "yes"
            with self.assertRaises(ProofError):
                validate_inputs(args)

    def test_inputs_reject_short_target_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp))
            args.target_id = "short"
            with self.assertRaises(ProofError):
                validate_inputs(args)

    def test_inputs_reject_bad_host_key_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp))
            args.host_key_sha256 = "not-a-fingerprint"
            with self.assertRaises(ProofError):
                validate_inputs(args)

    def test_inputs_reject_missing_bootstrap_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp))
            args.bootstrap_identity = Path(tmp) / "missing"
            with self.assertRaises(ProofError):
                validate_inputs(args)

    def test_parse_recap_reads_last_ansible_summary(self) -> None:
        output = """
PLAY RECAP ****
solo_vps : ok=90 changed=12 unreachable=0 failed=0 skipped=2 rescued=0 ignored=0
"""
        self.assertEqual(
            parse_recap(output, "bootstrap"),
            {"ok": 90, "changed": 12, "unreachable": 0, "failed": 0},
        )

    def test_parse_recap_rejects_missing_summary(self) -> None:
        with self.assertRaises(ProofError):
            parse_recap("no recap here", "bootstrap")

    def test_sanitize_failure_redacts_target_and_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "private-key"
            raw = f"host 198.51.100.4 key {key}\nssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakePayload comment\n"
            clean = sanitize_failure(raw, "198.51.100.4", [key])
            self.assertNotIn("198.51.100.4", clean)
            self.assertNotIn(str(key), clean)
            self.assertNotIn("AAAAC3NzaC1lZDI1NTE5AAAAIFakePayload", clean)
            self.assertIn("<disposable-target>", clean)
            self.assertIn("<private-key-path>", clean)

    def test_evidence_writer_uses_private_file_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = write_evidence(Path(tmp) / "evidence", {"public_safe": True})
            self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
            self.assertEqual(dest.parent.stat().st_mode & 0o777, 0o700)

    def test_refuses_target_that_is_controller_local(self) -> None:
        with mock.patch("scripts.prove_disposable_clean_target.resolve_ips", return_value={__import__("ipaddress").ip_address("127.0.0.1")}), mock.patch(
            "scripts.prove_disposable_clean_target.local_ips",
            return_value={__import__("ipaddress").ip_address("127.0.0.1")},
        ):
            with self.assertRaises(ProofError):
                refuse_production_or_local_target("127.0.0.1")

    def test_refuses_configured_production_host(self) -> None:
        import ipaddress

        mapping = {
            "clean.example": {ipaddress.ip_address("203.0.113.40")},
            "prod.example": {ipaddress.ip_address("203.0.113.40")},
        }
        with mock.patch("scripts.prove_disposable_clean_target.local_ips", return_value={ipaddress.ip_address("127.0.0.1")}), mock.patch(
            "scripts.prove_disposable_clean_target.configured_production_host", return_value="prod.example"
        ), mock.patch("scripts.prove_disposable_clean_target.resolve_ips", side_effect=lambda host: mapping[host]):
            with self.assertRaises(ProofError):
                refuse_production_or_local_target("clean.example")

    def test_allows_distinct_remote_nonproduction_target(self) -> None:
        import ipaddress

        mapping = {
            "clean.example": {ipaddress.ip_address("203.0.113.40")},
            "prod.example": {ipaddress.ip_address("203.0.113.41")},
        }
        with mock.patch("scripts.prove_disposable_clean_target.local_ips", return_value={ipaddress.ip_address("127.0.0.1")}), mock.patch(
            "scripts.prove_disposable_clean_target.configured_production_host", return_value="prod.example"
        ), mock.patch("scripts.prove_disposable_clean_target.resolve_ips", side_effect=lambda host: mapping[host]):
            refuse_production_or_local_target("clean.example")

    def test_configured_production_host_reads_external_state_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            config = base / "solo-vps/config/config.yml"
            config.parent.mkdir(parents=True)
            config.write_text("server:\n  host: prod.example\n", encoding="utf-8")
            with mock.patch.dict("os.environ", {"XDG_DATA_HOME": str(base)}, clear=False):
                self.assertEqual(configured_production_host(), "prod.example")


if __name__ == "__main__":
    unittest.main()
