from __future__ import annotations

import copy
import unittest

from scripts.inspect_coolify_sentinel import SentinelInspectionError, evaluate_inspect


EXPECTED_ENDPOINT = "https://coolify.example.com"
EXPECTED_IMAGE = "ghcr.io/coollabsio/sentinel:1.0.1"
EXPECTED_IMAGE_ID = "sha256:23b28fee258052080eaf89ffdc2acc318eaa58d1238ee5d56247daa27738a548"


def fixture() -> list[dict]:
    return [
        {
            "Name": "/coolify-sentinel",
            "Image": EXPECTED_IMAGE_ID,
            "Config": {
                "Image": EXPECTED_IMAGE,
                "Env": [
                    "TOKEN=secret-value-that-must-never-be-reported",
                    "DEBUG=false",
                    f"PUSH_ENDPOINT={EXPECTED_ENDPOINT}",
                    "COLLECTOR_ENABLED=false",
                ],
            },
            "State": {"Status": "running", "Health": {"Status": "healthy"}},
            "HostConfig": {"PidMode": "host", "PortBindings": {}},
            "NetworkSettings": {"Ports": {"8888/tcp": None}},
            "Mounts": [
                {"Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock", "RW": True},
                {"Source": "/data/coolify/sentinel", "Destination": "/app/db", "RW": True},
            ],
        }
    ]


class CoolifySentinelInspectTests(unittest.TestCase):
    def evaluate(self, payload: list[dict]) -> dict:
        return evaluate_inspect(
            payload,
            expected_push_endpoint=EXPECTED_ENDPOINT,
            expected_image=EXPECTED_IMAGE,
            expected_image_id=EXPECTED_IMAGE_ID,
            observed_version="1.0.1",
            expected_version="1.0.1",
        )

    def test_safe_candidate_passes_without_returning_token(self) -> None:
        report = self.evaluate(fixture())
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["token_present"])
        self.assertNotIn("secret-value", repr(report))
        self.assertFalse(report["host_ports_published"])

    def test_post_reboot_docker_hub_alias_passes_with_pinned_image_id(self) -> None:
        payload = fixture()
        payload[0]["Config"]["Image"] = "docker.io/coollabsio/sentinel:1.0.1"
        self.assertEqual(self.evaluate(payload)["status"], "PASS")

    def test_alias_with_wrong_image_content_is_rejected(self) -> None:
        payload = fixture()
        payload[0]["Config"]["Image"] = "docker.io/coollabsio/sentinel:1.0.1"
        payload[0]["Image"] = "sha256:" + "0" * 64
        with self.assertRaises(SentinelInspectionError):
            self.evaluate(payload)

    def test_unreviewed_registry_is_rejected(self) -> None:
        payload = fixture()
        payload[0]["Config"]["Image"] = "example.org/coollabsio/sentinel:1.0.1"
        with self.assertRaises(SentinelInspectionError):
            self.evaluate(payload)

    def test_public_port_is_rejected(self) -> None:
        payload = fixture()
        payload[0]["HostConfig"]["PortBindings"] = {"8888/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8888"}]}
        with self.assertRaises(SentinelInspectionError):
            self.evaluate(payload)

    def test_loopback_coolify_endpoint_is_rejected(self) -> None:
        payload = fixture()
        payload[0]["Config"]["Env"][2] = "PUSH_ENDPOINT=http://host.docker.internal:8000"
        with self.assertRaises(SentinelInspectionError):
            self.evaluate(payload)

    def test_missing_token_is_rejected(self) -> None:
        payload = fixture()
        payload[0]["Config"]["Env"][0] = "TOKEN="
        with self.assertRaises(SentinelInspectionError):
            self.evaluate(payload)

    def test_debug_mode_is_rejected(self) -> None:
        payload = fixture()
        payload[0]["Config"]["Env"][1] = "DEBUG=true"
        with self.assertRaises(SentinelInspectionError):
            self.evaluate(payload)

    def test_read_only_socket_drift_is_reported_not_silently_accepted(self) -> None:
        payload = copy.deepcopy(fixture())
        payload[0]["Mounts"][0]["RW"] = False
        with self.assertRaises(SentinelInspectionError):
            self.evaluate(payload)

    def test_wrong_version_is_rejected(self) -> None:
        with self.assertRaises(SentinelInspectionError):
            evaluate_inspect(
                fixture(),
                expected_push_endpoint=EXPECTED_ENDPOINT,
                expected_image=EXPECTED_IMAGE,
                expected_image_id=EXPECTED_IMAGE_ID,
                observed_version="1.0.0",
                expected_version="1.0.1",
            )

    def test_non_https_expected_endpoint_is_rejected(self) -> None:
        with self.assertRaises(SentinelInspectionError):
            evaluate_inspect(fixture(), expected_push_endpoint="http://coolify.example.com")


if __name__ == "__main__":
    unittest.main()
