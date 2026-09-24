"""Evaluate socket diagnostics with the actual Ansible template engine."""
from __future__ import annotations

import os
from pathlib import Path
import unittest

if os.name == "posix":
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "requires a Linux Ansible controller")
class FirewallListenerTemplateTests(unittest.TestCase):
    def setUp(self):
        self.loader = DataLoader()
        tasks = self.loader.load_from_file(str(ROOT / "ansible/roles/firewall/tasks/verify.yml"))
        self.expression = next(
            task["ansible.builtin.set_fact"]["solo_vps_firewall_wildcard_tcp_ports"]
            for task in tasks
            if "solo_vps_firewall_wildcard_tcp_ports" in task.get("ansible.builtin.set_fact", {})
        )

    def render(self, sockets):
        return Templar(loader=self.loader, variables={
            "solo_vps_firewall_tcp_listeners": {"stdout": sockets},
        }).template(trust_as_template(self.expression))

    def test_only_local_wildcard_addresses_are_reported(self):
        sockets = "\n".join([
            'LISTEN 0 4096 127.0.0.1:8000 0.0.0.0:* users:(("docker-proxy",pid=100,fd=8))',
            'LISTEN 0 4096 127.0.0.53%lo:53 0.0.0.0:*',
            'LISTEN 0 4096 [::1]:6001 [::]:*',
            'LISTEN 0 4096 192.0.2.10:9000 0.0.0.0:12345',
            'LISTEN 0 4096 0.0.0.0:22 0.0.0.0:*',
            'LISTEN 0 4096 [::]:22 [::]:*',
            'LISTEN 0 4096 *:443 *:*',
            'LISTEN 0 4096 0.0.0.0:80 0.0.0.0:*',
        ])
        self.assertEqual(self.render(sockets), [22, 80, 443])

    def test_loopback_only_and_empty_input(self):
        self.assertEqual(self.render('LISTEN 0 4096 127.0.0.1:8000 0.0.0.0:*'), [])
        self.assertEqual(self.render(''), [])


if __name__ == "__main__":
    unittest.main()
