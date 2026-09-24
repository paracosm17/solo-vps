from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from scripts.observability_credentials_common import (
    ObservabilityCredentialError,
    canonical_json_bytes,
    parse_json_bytes,
    validate_payload,
)
from scripts import install_observability_credentials as installer
from scripts.install_observability_credentials import InstallError, install_payload, verify_file

VALID = {
    "LOKI_URL": "https://logs.example.net/loki/api/v1/push",
    "LOKI_USERNAME": "123456",
    "GRAFANA_CLOUD_API_KEY": "synthetic-token-value",
}


class ObservabilityCredentialSchemaTests(unittest.TestCase):
    def test_required_payload_roundtrip(self) -> None:
        raw = canonical_json_bytes(VALID)
        self.assertEqual(parse_json_bytes(raw), VALID)
        self.assertTrue(raw.endswith(b"\n"))

    def test_unknown_key_is_rejected(self) -> None:
        with self.assertRaises(ObservabilityCredentialError):
            validate_payload(dict(VALID, EXTRA="no"))

    def test_missing_key_is_rejected(self) -> None:
        payload = dict(VALID)
        payload.pop("GRAFANA_CLOUD_API_KEY")
        with self.assertRaises(ObservabilityCredentialError):
            validate_payload(payload)

    def test_http_loki_url_is_rejected(self) -> None:
        with self.assertRaises(ObservabilityCredentialError):
            validate_payload(dict(VALID, LOKI_URL="http://logs.example.net/loki/api/v1/push"))

    def test_wrong_loki_path_is_rejected(self) -> None:
        with self.assertRaises(ObservabilityCredentialError):
            validate_payload(dict(VALID, LOKI_URL="https://logs.example.net/api/push"))

    def test_multiline_token_is_rejected(self) -> None:
        with self.assertRaises(ObservabilityCredentialError):
            validate_payload(dict(VALID, GRAFANA_CLOUD_API_KEY="first\nsecond"))


class ObservabilityCredentialInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.uid = os.getuid()
        self.gid = os.getgid()

    def test_install_is_atomic_mode_safe_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observability" / "grafana-cloud.json"
            self.assertTrue(install_payload(VALID, path, owner_uid=self.uid, owner_gid=self.gid))
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(verify_file(path, owner_uid=self.uid, owner_gid=self.gid), VALID)
            self.assertFalse(install_payload(VALID, path, owner_uid=self.uid, owner_gid=self.gid))

    def test_changed_payload_replaces_valid_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observability" / "grafana-cloud.json"
            install_payload(VALID, path, owner_uid=self.uid, owner_gid=self.gid)
            updated = dict(VALID, GRAFANA_CLOUD_API_KEY="rotated-synthetic-token")
            self.assertTrue(install_payload(updated, path, owner_uid=self.uid, owner_gid=self.gid))
            self.assertEqual(verify_file(path, owner_uid=self.uid, owner_gid=self.gid), updated)

    def test_invalid_existing_file_is_not_silently_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observability" / "grafana-cloud.json"
            path.parent.mkdir(mode=0o700)
            path.write_text("not-json\n", encoding="utf-8")
            path.chmod(0o600)
            with self.assertRaises(InstallError):
                install_payload(VALID, path, owner_uid=self.uid, owner_gid=self.gid)

    def test_symlink_destination_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "real.json"
            target.write_text("{}\n", encoding="utf-8")
            directory = root / "observability"
            directory.mkdir(mode=0o700)
            path = directory / "grafana-cloud.json"
            path.symlink_to(target)
            with self.assertRaises(InstallError):
                install_payload(VALID, path, owner_uid=self.uid, owner_gid=self.gid)

    def test_symlink_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            linked = root / "observability"
            linked.symlink_to(real, target_is_directory=True)
            with self.assertRaises(InstallError):
                install_payload(VALID, linked / "grafana-cloud.json", owner_uid=self.uid, owner_gid=self.gid)

    def test_cli_keeps_symlink_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "real.json"
            target.write_bytes(canonical_json_bytes(VALID))
            link = root / "grafana-cloud.json"
            link.symlink_to(target)
            with mock.patch.object(installer, "_require_root"), mock.patch(
                "sys.argv", ["install_observability_credentials.py", "verify", "--path", str(link)]
            ), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(installer.main(), 2)


if __name__ == "__main__":
    unittest.main()
