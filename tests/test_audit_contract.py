from __future__ import annotations

import pathlib
import shutil
import tempfile
import unittest

import yaml

from scripts.validate_audit_contract import (
    AuditContractError,
    EXPECTED_DOCKER_PORT_KEY_PATTERN,
    validate,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]


class AuditContractTests(unittest.TestCase):
    COPY_PATHS = (
        "ansible/playbooks/audit.yml",
        "ansible/roles/security_audit/defaults/main.yml",
        "ansible/roles/security_audit/tasks/main.yml",
        "ansible/roles/ssh/defaults/main.yml",
        "Makefile",
    )

    def copy_contract(self, destination: pathlib.Path) -> pathlib.Path:
        for relative in self.COPY_PATHS:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        return destination

    def test_current_contract_is_valid(self) -> None:
        validate(ROOT)

    def test_docker_port_key_pattern_accepts_reviewed_protocol_shape(self) -> None:
        import re

        for value in ("8080/tcp", "6001/tcp", "53/udp"):
            self.assertIsNotNone(re.fullmatch(EXPECTED_DOCKER_PORT_KEY_PATTERN, value))
        for value in ("8080", "tcp/8080", "8080/sctp", ""):
            self.assertIsNone(re.fullmatch(EXPECTED_DOCKER_PORT_KEY_PATTERN, value))

    def test_current_source_reads_full_inspect_json_and_enumerates_bindings(self) -> None:
        text = (ROOT / "ansible/roles/security_audit/tasks/main.yml").read_text(encoding="utf-8")
        self.assertIn("container\n      - inspect", text)
        self.assertIn(".NetworkSettings.Ports", text)
        self.assertIn("| dict2items", text)
        self.assertIn("subelements('value')", text)
        self.assertNotIn("range $containerPort", text)

    def test_structured_coolify_fixture_contains_three_independent_bindings(self) -> None:
        sample = {
            "8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8000"}],
            "6001/tcp": [{"HostIp": "127.0.0.1", "HostPort": "6001"}],
            "6002/tcp": [{"HostIp": "127.0.0.1", "HostPort": "6002"}],
        }
        bindings = [
            (binding["HostIp"], binding["HostPort"], container_port)
            for container_port, values in sample.items()
            for binding in values
        ]
        self.assertEqual(
            bindings,
            [
                ("127.0.0.1", "8000", "8080/tcp"),
                ("127.0.0.1", "6001", "6001/tcp"),
                ("127.0.0.1", "6002", "6002/tcp"),
            ],
        )

    def test_rejects_mutating_audit_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/security_audit/tasks/main.yml"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            data.insert(0, {"name": "Bad mutation", "ansible.builtin.file": {"path": "/tmp/x", "state": "touch"}})
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            with self.assertRaises(AuditContractError):
                validate(root)

    def test_rejects_missing_baseline_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/playbooks/audit.yml"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            del data[3]  # remove verify-updates.yml
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            with self.assertRaises(AuditContractError):
                validate(root)

    def test_rejects_default_verify_ssh_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/playbooks/audit.yml"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            data[1]["ansible.builtin.import_playbook"] = "verify-ssh.yml"
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            with self.assertRaises(AuditContractError):
                validate(root)

    def test_rejects_missing_docker_publication_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/security_audit/tasks/main.yml"
            text = path.read_text(encoding="utf-8").replace(".NetworkSettings.Ports", ".NetworkSettings.Networks")
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(AuditContractError):
                validate(root)

    def test_rejects_human_oriented_docker_ports_parser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/security_audit/tasks/main.yml"
            text = path.read_text(encoding="utf-8")
            text = text.replace("- container\n      - inspect", "- ps\n      - --format\n      - {{.Ports}}")
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(AuditContractError):
                validate(root)

    def test_rejects_structured_binding_enumeration_removal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/security_audit/tasks/main.yml"
            text = path.read_text(encoding="utf-8").replace("| dict2items", "| list")
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(AuditContractError):
                validate(root)

    def test_rejects_non_tcp_publication_policy_weakening(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/security_audit/tasks/main.yml"
            text = path.read_text(encoding="utf-8").replace("(item.protocol != 'tcp') or\n", "")
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(AuditContractError):
                validate(root)

    def test_rejects_docker_loopback_caveat_removal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/security_audit/tasks/main.yml"
            text = path.read_text(encoding="utf-8").replace("solo_vps_audit_docker_server_major | int < 28", "false")
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(AuditContractError):
                validate(root)

    def test_user_visible_audit_summary_avoids_internal_milestone_labels(self) -> None:
        defaults = yaml.safe_load((ROOT / "ansible/roles/security_audit/defaults/main.yml").read_text(encoding="utf-8"))
        boundaries = defaults["solo_vps_audit_evidence_boundaries"]
        rendered_boundaries = "\n".join(boundaries.values())
        tasks = yaml.safe_load((ROOT / "ansible/roles/security_audit/tasks/main.yml").read_text(encoding="utf-8"))
        rendered_tasks = "\n".join(str(task) for task in tasks)
        import re
        self.assertIsNone(re.search(r"\bM\d+\b", rendered_boundaries))
        for old in ("PASS: M4", "PASS: M5", "PASS: M6", "PASS: M7"):
            self.assertNotIn(old, rendered_tasks)

    def test_rejects_false_pass_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/security_audit/defaults/main.yml"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            data["solo_vps_audit_evidence_boundaries"]["backup_repository"] = "PASS: assumed"
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            with self.assertRaises(AuditContractError):
                validate(root)

    def test_rejects_ssh_policy_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/security_audit/defaults/main.yml"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            data["solo_vps_audit_expected_ssh_options"].remove("permitrootlogin no")
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            with self.assertRaises(AuditContractError):
                validate(root)

    def test_rejects_missing_fail_closed_assert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/security_audit/tasks/main.yml"
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            data = [task for task in data if "ansible.builtin.assert" not in task]
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            with self.assertRaises(AuditContractError):
                validate(root)

    def test_rejects_audit_without_platform_doctor_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "Makefile"
            text = path.read_text(encoding="utf-8").replace("audit: doctor-platform-local", "audit: doctor-local")
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(AuditContractError):
                validate(root)


if __name__ == "__main__":
    unittest.main()
