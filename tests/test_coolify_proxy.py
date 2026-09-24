from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.inspect_coolify_proxy import ProxyError, evidence, inspect, safe_ports


def container():
    ports = {
        "80/tcp": [
            {"HostIp": "0.0.0.0", "HostPort": "80"},
            {"HostIp": "::", "HostPort": "80"},
        ],
        "443/tcp": [
            {"HostIp": "0.0.0.0", "HostPort": "443"},
            {"HostIp": "::", "HostPort": "443"},
        ],
    }
    return {
        "Name": "/coolify-proxy",
        "Config": {
            "Image": "traefik:v3.6",
            "Labels": {
                "coolify.proxy": "true",
                "com.docker.compose.service": "traefik",
            },
        },
        "HostConfig": {"NetworkMode": "coolify", "PortBindings": copy.deepcopy(ports)},
        "NetworkSettings": {"Ports": copy.deepcopy(ports)},
        "State": {"Running": True, "Health": {"Status": "healthy"}},
    }


class CoolifyProxyTests(unittest.TestCase):
    def test_tcp_edge_accepts_ipv4_ipv6_and_unpublished_exposed_ports(self):
        value = container()
        value["NetworkSettings"]["Ports"]["8080/tcp"] = None
        self.assertEqual(
            evidence(value),
            {"present": True, "running": True, "healthy": True, "ports_safe": True},
        )

    def test_default_proxy_publications_reproduce_audit_failure(self):
        for extra in ("8080/tcp", "443/udp"):
            for location in ("HostConfig", "NetworkSettings"):
                value = container()
                field = "PortBindings" if location == "HostConfig" else "Ports"
                value[location][field][extra] = [
                    {"HostIp": "::", "HostPort": extra.split("/")[0]}
                ]
                self.assertFalse(evidence(value)["ports_safe"])

    def test_wrong_host_port_or_missing_http_mapping_is_rejected(self):
        value = container()["HostConfig"]["PortBindings"]
        value["80/tcp"][0]["HostPort"] = "8080"
        self.assertFalse(safe_ports(value))
        del value["80/tcp"]
        self.assertFalse(safe_ports(value))

    def test_unrecognized_identity_and_host_network_are_rejected(self):
        for field, key, new in (
            ("Config", "Image", "caddy:2"),
            ("HostConfig", "NetworkMode", "host"),
        ):
            value = container()
            value[field][key] = new
            with self.assertRaises(ProxyError):
                evidence(value)
        value = container()
        value["Config"]["Labels"] = {}
        with self.assertRaises(ProxyError):
            evidence(value)

    def test_stopped_or_unhealthy_proxy_is_not_reported_healthy_and_running(self):
        value = container()
        value["State"]["Running"] = False
        self.assertFalse(evidence(value)["running"])
        value["State"]["Health"]["Status"] = "unhealthy"
        self.assertFalse(evidence(value)["healthy"])

    def test_absent_proxy_is_allowed_before_first_activation(self):
        with patch(
            "scripts.inspect_coolify_proxy.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run:
            self.assertFalse(inspect("docker")["present"])
            self.assertEqual(run.call_count, 1)

    def test_docker_error_is_not_mistaken_for_absent_proxy(self):
        with (
            patch(
                "scripts.inspect_coolify_proxy.subprocess.run",
                return_value=subprocess.CompletedProcess([], 1, "", "private-value"),
            ),
            self.assertRaises(ProxyError) as raised,
        ):
            inspect("docker")
        self.assertNotIn("private-value", str(raised.exception))

    def test_inspection_emits_no_environment_or_labels(self):
        value = container()
        value["Config"]["Env"] = ["TOKEN=private-value"]
        results = [
            subprocess.CompletedProcess([], 0, "abc\n", ""),
            subprocess.CompletedProcess([], 0, json.dumps([value]), ""),
        ]
        with patch("scripts.inspect_coolify_proxy.subprocess.run", side_effect=results):
            self.assertNotIn("private-value", json.dumps(inspect("docker")))

    def test_invalid_binding_shapes_fail_closed(self):
        for value in (None, [], {}, {"80/tcp": "bad", "443/tcp": "bad"}):
            self.assertFalse(safe_ports(value))


@unittest.skipUnless(
    os.environ.get("SOLO_VPS_TEST_COMPOSE"),
    "set SOLO_VPS_TEST_COMPOSE to a standalone Docker Compose executable",
)
class ProxyComposeIntegrationTests(unittest.TestCase):
    def test_default_discovery_removes_extra_ports_and_survives_base_regeneration(self):
        root = Path(__file__).resolve().parents[1]
        template = (
            root
            / "ansible/roles/coolify/templates/docker-compose.proxy-override.yml.j2"
        )
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / "docker-compose.override.yml").write_bytes(template.read_bytes())
            for additional in ([], ["8443:8443"]):
                base = {
                    "name": "coolify-proxy",
                    "services": {
                        "traefik": {
                            "image": "traefik:v3.6",
                            "container_name": "coolify-proxy",
                            "ports": [
                                "80:80",
                                "443:443",
                                "443:443/udp",
                                "8080:8080",
                                *additional,
                            ],
                            "command": [
                                "--api.insecure=false",
                                "--providers.file.watch=true",
                            ],
                            "labels": {"coolify.proxy": "true", "custom.route": "keep"},
                        }
                    },
                }
                (work / "docker-compose.yml").write_text(
                    json.dumps(base), encoding="utf-8"
                )
                result = subprocess.run(
                    [os.environ["SOLO_VPS_TEST_COMPOSE"], "config", "--format", "json"],
                    cwd=work,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                service = json.loads(result.stdout)["services"]["traefik"]
                self.assertEqual(
                    {
                        (p["target"], p["published"], p["protocol"])
                        for p in service["ports"]
                    },
                    {(80, "80", "tcp"), (443, "443", "tcp")},
                )
                self.assertEqual(
                    service["command"], base["services"]["traefik"]["command"]
                )
                self.assertEqual(service["labels"]["custom.route"], "keep")


if __name__ == "__main__":
    unittest.main()
