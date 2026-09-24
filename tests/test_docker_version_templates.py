"""Evaluate the source YAML with the pinned Ansible engine, without SSH or Docker.

Run with the controller QA Python (also part of make qa-static). These tests
deliberately require Ansible: plain Jinja does not reproduce Ansible escaping.
"""
from __future__ import annotations

from pathlib import Path
import os
import unittest

if os.name == "posix":
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "requires a Linux Ansible controller")
class DockerVersionTemplateTests(unittest.TestCase):
    def setUp(self):
        self.loader = DataLoader()
        self.tasks = self.loader.load_from_file(str(ROOT / "ansible/roles/docker/tasks/main.yml"))
        self.defaults = self.loader.load_from_file(str(ROOT / "ansible/roles/docker/defaults/main.yml"))

    def task(self, name):
        return next(task for task in self.tasks if task["name"] == name)

    def render_facts(self, name, variables):
        templar = Templar(loader=self.loader, variables=variables)
        return {
            key: templar.template(value)
            for key, value in self.task(name)["ansible.builtin.set_fact"].items()
        }

    def assert_gate(self, name, variables, expected):
        templar = Templar(loader=self.loader, variables={**self.defaults, **variables})
        for condition in self.task(name)["ansible.builtin.assert"]["that"]:
            self.assertIs(templar.evaluate_conditional(condition), expected)

    def test_installed_versions_and_guard(self):
        for version, major, accepted in (
            ("5:29.7.2-1~ubuntu.24.04~noble", 29, True),
            ("29.7.2", 29, True),
            ("5:30.0.0-1~ubuntu.24.04~noble", 30, False),
            ("5:28.5.0-1~ubuntu.24.04~noble", 28, False),
            ("invalid", -1, False),
            ("", -1, False),
        ):
            with self.subTest(version=version):
                facts = self.render_facts(
                    "Derive the installed Docker CE package major before any repository mutation",
                    {"ansible_facts": {"packages": {"docker-ce": [{"version": version}]}}},
                )
                self.assertEqual(facts["solo_vps_docker_existing_server_major"], major)
                self.assert_gate(
                    "Refuse an unsupported existing Docker major before any Docker role mutation",
                    facts, accepted,
                )

    def test_candidate_versions_and_guard(self):
        for candidate, major, accepted in (
            ("5:29.7.2-1~ubuntu.24.04~noble", 29, True),
            ("29.7.2", 29, True),
            ("5:30.0.0-1~ubuntu.24.04~noble", 30, False),
            ("(none)", -1, False),
            ("invalid", -1, False),
        ):
            with self.subTest(candidate=candidate):
                facts = self.render_facts(
                    "Derive the Docker CE candidate major version",
                    {"solo_vps_docker_ce_policy": {
                        "stdout": f"docker-ce:\n  Installed: (none)\n  Candidate: {candidate}\n  Version table:\n"
                    }},
                )
                self.assertEqual(facts["solo_vps_docker_ce_candidate_version"], candidate)
                self.assertEqual(facts["solo_vps_docker_ce_candidate_major"], major)
                self.assert_gate("Refuse an untested Docker major before first installation", facts, accepted)

    def test_missing_candidate_fails_closed_without_filter_exception(self):
        facts = self.render_facts(
            "Derive the Docker CE candidate major version",
            {"solo_vps_docker_ce_policy": {"stdout": "docker-ce:\n  Installed: (none)\n"}},
        )
        self.assertEqual(facts["solo_vps_docker_ce_candidate_version"], "")
        self.assertEqual(facts["solo_vps_docker_ce_candidate_major"], -1)
        self.assert_gate("Refuse an untested Docker major before first installation", facts, False)


if __name__ == "__main__":
    unittest.main()
