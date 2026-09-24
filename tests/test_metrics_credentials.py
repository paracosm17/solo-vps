from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import unittest

from scripts.metrics_credentials_common import (
    MetricsCredentialError,
    canonical_json_bytes,
    parse_json_bytes,
    validate_payload,
)
from scripts.install_metrics_credentials import InstallError, install_payload, verify_file

VALID = {
    "PROMETHEUS_URL": "https://prometheus-prod-01.grafana.net/api/prom/push",
    "PROMETHEUS_USERNAME": "123456",
    "GRAFANA_CLOUD_METRICS_API_KEY": "synthetic-metrics-token-value",
}


class MetricsCredentialSchemaTests(unittest.TestCase):
    def test_required_payload_roundtrip(self) -> None:
        self.assertEqual(parse_json_bytes(canonical_json_bytes(VALID)), VALID)

    def test_unknown_key_is_rejected(self) -> None:
        with self.assertRaises(MetricsCredentialError):
            validate_payload(dict(VALID, EXTRA="no"))

    def test_http_endpoint_is_rejected(self) -> None:
        with self.assertRaises(MetricsCredentialError):
            validate_payload(dict(VALID, PROMETHEUS_URL="http://example.net/api/prom/push"))

    def test_wrong_path_is_rejected(self) -> None:
        with self.assertRaises(MetricsCredentialError):
            validate_payload(dict(VALID, PROMETHEUS_URL="https://example.net/api/v1/push"))

    def test_non_numeric_username_is_rejected(self) -> None:
        with self.assertRaises(MetricsCredentialError):
            validate_payload(dict(VALID, PROMETHEUS_USERNAME="stack-name"))

    def test_multiline_token_is_rejected(self) -> None:
        with self.assertRaises(MetricsCredentialError):
            validate_payload(dict(VALID, GRAFANA_CLOUD_METRICS_API_KEY="one\ntwo"))


class MetricsCredentialInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.uid = os.getuid()
        self.gid = os.getgid()

    def test_install_is_mode_safe_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics" / "grafana-cloud.json"
            self.assertTrue(install_payload(VALID, path, owner_uid=self.uid, owner_gid=self.gid))
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(verify_file(path, owner_uid=self.uid, owner_gid=self.gid), VALID)
            self.assertFalse(install_payload(VALID, path, owner_uid=self.uid, owner_gid=self.gid))

    def test_invalid_existing_file_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics" / "grafana-cloud.json"
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
            directory = root / "metrics"
            directory.mkdir(mode=0o700)
            link = directory / "grafana-cloud.json"
            link.symlink_to(target)
            with self.assertRaises(InstallError):
                install_payload(VALID, link, owner_uid=self.uid, owner_gid=self.gid)


if __name__ == "__main__":
    unittest.main()
