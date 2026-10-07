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
from scripts.coolify_proxy_policy import PolicyError, policy_configuration, execute
from scripts.coolify_proxy_ingress_guard import GuardError, rules, reconcile, CHAIN
import yaml
import shlex


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
    def test_guard_preserves_shared_rules_is_idempotent_and_check_never_mutates(self):
        shared = ['-m', 'conntrack', '--ctstate', 'RELATED,ESTABLISHED', '-j', 'RETURN']
        forward = [['-j', 'ufw-before-forward'], ['-j', 'DOCKER-USER'], ['-j', 'DOCKER-FORWARD']]
        chains = {'INPUT': [['-j', 'ufw-before-input']], 'FORWARD': copy.deepcopy(forward), 'DOCKER-USER': [shared.copy()]}
        mutations = []
        def fake(binary, args, required=True):
            op, name, *rest = args
            rc, output = 0, ''
            if op == '-S':
                if name not in chains:
                    rc = 1
                else:
                    output = '\n'.join(shlex.join(['-A', name, *entry]) for entry in chains[name])
            elif op == '-C':
                rc = 0 if rest in chains.get(name, []) else 1
            else:
                mutations.append(args.copy())
                if op == '-N': chains[name] = []
                elif op == '-A': chains[name].append(rest)
                elif op == '-I': chains[name].insert(int(rest[0]) - 1, rest[1:])
                elif op == '-D': chains[name].remove(rest)
                else: self.fail('Unexpected shared-chain mutation')
            return subprocess.CompletedProcess([], rc, output, '')
        with patch('scripts.coolify_proxy_ingress_guard.invoke', side_effect=fake):
            self.assertTrue(reconcile('iptables', ['ens18'], False))
            self.assertIn(shared, chains['DOCKER-USER'])
            self.assertIn(['-j', 'ufw-before-input'], chains['INPUT'])
            self.assertEqual(chains['FORWARD'], [['-j', CHAIN], *forward])
            self.assertFalse(reconcile('iptables', ['ens18'], False))
            mutations.clear()
            self.assertFalse(reconcile('iptables', ['ens18'], True))
            self.assertFalse(mutations)
            # Docker prepends its normal hooks while restoring workloads.
            # DOCKER-USER still enters the guard before any shared rules.
            chains['FORWARD'] = [['-j', 'DOCKER-USER'], ['-j', 'DOCKER-FORWARD'], ['-j', CHAIN]]
            self.assertFalse(reconcile('iptables', ['ens18'], True))
            self.assertFalse(reconcile('iptables', ['ens18'], False))
            self.assertFalse(mutations)
            chains[CHAIN].append(['-j', 'ACCEPT'])
            with self.assertRaises(GuardError):
                reconcile('iptables', ['ens18'], False)
            self.assertFalse(mutations)

    def test_ingress_guard_is_bounded_to_original_external_forbidden_ports(self):
        values = rules(['ens18', 'ens18'])
        self.assertEqual(len(values), 2)
        for value in values:
            self.assertEqual(value[value.index('-i') + 1], 'ens18')
            self.assertEqual(value[value.index('--ctdir') + 1], 'ORIGINAL')
            self.assertEqual(value[value.index('-j') + 1], 'DROP')
        self.assertEqual({value[value.index('--ctorigdstport') + 1] for value in values}, {'8080', '443'})
        for values in ([], ['ens18;bad'], ['']):
            with self.assertRaises(GuardError):
                rules(values)

    def test_port_patch_preserves_comments_and_compose_scalar_spelling(self):
        original = '''# Operator configuration
services:
  traefik:
    container_name: coolify-proxy
    image: traefik:v3.6
    labels:
      coolify.proxy: 'true'
      custom.value: on
    ports:
      - 80:80
      - 443:443
      - 8080:8080
    environment:
      VALUE: off # Preserve this comment
'''
        updated, changed = policy_configuration(original)
        self.assertTrue(changed)
        self.assertIn('custom.value: on', updated)
        self.assertIn('VALUE: off # Preserve this comment', updated)
        self.assertTrue(updated.startswith('# Operator configuration\n'))

    def test_restart_image_or_network_drift_is_refused_before_save(self):
        original = yaml.safe_dump({'services': {'traefik': {'container_name': 'coolify-proxy', 'labels': {'coolify.proxy': 'true'}, 'image': 'traefik:v3.6', 'ports': ['80:80', '443:443', '8080:8080']}}})
        before = container()
        before['HostConfig']['PortBindings']['8080/tcp'] = [{'HostIp': '0.0.0.0', 'HostPort': '8080'}]
        for model in ({'services': {'traefik': {'image': 'traefik:foreign'}}}, {'services': {'traefik': {'image': 'traefik:v3.6'}}, 'networks': {}}):
            before['NetworkSettings']['Networks'] = {'unexpected-app': {}}
            with tempfile.TemporaryDirectory() as temp, patch('scripts.coolify_proxy_policy.proxy_state', return_value=before), patch('scripts.coolify_proxy_policy.native', return_value={'configuration': original}) as native, patch('scripts.coolify_proxy_policy.run', return_value=json.dumps(model)):
                with self.assertRaises(PolicyError):
                    execute('docker', 'ops', True, Path(temp) / 'absent')
                self.assertEqual(native.call_count, 1)

    def test_native_policy_changes_only_ports_and_preserves_custom_configuration(self):
        data = {'services': {'traefik': {'image': 'traefik:v3.6', 'container_name': 'coolify-proxy',
                'labels': {'coolify.proxy': 'true', 'private.route': 'preserve'},
                'ports': ['80:80', '443:443', '8080:8080', '443:443/udp'],
                'command': ['--providers.file.watch=true'], 'volumes': ['volume:/data'],
                'environment': {'PRIVATE_VALUE': 'stay-private'}},
                'sidecar': {'image': 'busybox:1', 'command': ['true']}},
                'networks': {'app': {'external': True, 'name': 'app-network'}}}
        text, changed = policy_configuration(yaml.safe_dump(data))
        self.assertTrue(changed)
        value = yaml.safe_load(text)
        self.assertEqual(value['services']['traefik']['ports'], ['80:80/tcp', '443:443/tcp'])
        value['services']['traefik']['ports'] = data['services']['traefik']['ports']
        self.assertEqual(value, data)
        self.assertFalse(policy_configuration(text)[1])

    def test_native_policy_refuses_unknown_service_ownership_image_and_network(self):
        valid = {'container_name': 'coolify-proxy', 'labels': {'coolify.proxy': 'true'}, 'image': 'traefik:v3.6'}
        for key, value in [('container_name', 'foreign'), ('labels', {}), ('image', 'caddy:2'), ('network_mode', 'host')]:
            with self.subTest(key=key), self.assertRaises(PolicyError):
                policy_configuration(yaml.safe_dump({'services': {'traefik': {**valid, key: value}}}))

    def test_native_policy_stopped_proxy_stays_stopped_and_unknown_override_is_preserved(self):
        valid = {'services': {'traefik': {'container_name': 'coolify-proxy', 'labels': {'coolify.proxy': 'true'}, 'image': 'traefik:v3.6', 'ports': ['80:80', '443:443', '8080:8080']}}}
        original = yaml.safe_dump(valid)
        updated, _ = policy_configuration(original)
        stopped = container()
        stopped['State']['Running'] = False
        with tempfile.TemporaryDirectory() as temp, patch('scripts.coolify_proxy_policy.proxy_state', return_value=stopped), patch('scripts.coolify_proxy_policy.native', side_effect=[{'configuration': original}, {}, {'configuration': updated}]) as native:
            override = Path(temp) / 'override.yml'
            result = execute('docker', 'ops', True, override)
            self.assertTrue(result['changed'])
            self.assertFalse(result['restarted'])
            self.assertFalse(native.call_args_list[1].args[1]['restart'])
            override.write_text('# custom operator override')
            native.reset_mock()
            with self.assertRaises(PolicyError):
                execute('docker', 'ops', True, override)
            native.assert_not_called()
            self.assertEqual(override.read_text(), '# custom operator override')

    def test_native_policy_check_is_read_only_and_rejects_saved_drift(self):
        original = yaml.safe_dump({'services': {'traefik': {'container_name': 'coolify-proxy', 'labels': {'coolify.proxy': 'true'}, 'image': 'traefik:v3.6', 'ports': ['80:80', '443:443', '8080:8080']}}})
        with tempfile.TemporaryDirectory() as temp, patch('scripts.coolify_proxy_policy.proxy_state', return_value=container()), patch('scripts.coolify_proxy_policy.native', return_value={'configuration': original}) as native:
            with self.assertRaises(PolicyError):
                execute('docker', 'ops', False, Path(temp) / 'absent')
            self.assertEqual(native.call_count, 1)
            self.assertEqual(native.call_args.args[1]['mode'], 'check')

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
