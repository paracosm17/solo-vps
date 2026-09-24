from __future__ import annotations

import pathlib
import shutil
import tempfile
import unittest

from scripts.validate_firewall_contract import ContractError, validate_root


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


class FirewallContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name) / "repo"
        shutil.copytree(PROJECT_ROOT, self.root, ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_current_contract_passes(self) -> None:
        validate_root(self.root)

    def test_rejects_old_allow_in_only_parser(self) -> None:
        path = self.root / "ansible/roles/firewall/defaults/main.yml"
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "ALLOW(?:(?:\\s+IN)|(?!\\s+(?:OUT|FWD)\\b))\\s+",
            "ALLOW\\s+IN\\s+",
        )
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_parser_that_accepts_outbound_rows(self) -> None:
        path = self.root / "ansible/roles/firewall/defaults/main.yml"
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "ALLOW(?:(?:\\s+IN)|(?!\\s+(?:OUT|FWD)\\b))\\s+",
            "ALLOW\\s+",
        )
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_evidence_report_after_assert(self) -> None:
        path = self.root / "ansible/roles/firewall/tasks/verify.yml"
        text = path.read_text(encoding="utf-8")
        report_start = text.index("- name: Report current host exposure evidence before enforcing it")
        assert_start = text.index("- name: Verify the UFW host exposure baseline")
        report_block = text[report_start:assert_start]
        text = text[:report_start] + text[assert_start:] + "\n" + report_block
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_wildcard_listener_as_standalone_public_exposure_failure(self) -> None:
        path = self.root / "ansible/roles/firewall/tasks/verify.yml"
        text = path.read_text(encoding="utf-8")
        marker = "      - solo_vps_firewall_expected_allow_targets | difference(solo_vps_firewall_allow_targets) | length == 0\n"
        text = text.replace(
            marker,
            marker
            + "      - solo_vps_firewall_wildcard_tcp_ports | difference(solo_vps_firewall_expected_tcp_ports) | length == 0\n",
            1,
        )
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_trailing_blank_line_in_firewall_verifier(self) -> None:
        path = self.root / "ansible/roles/firewall/tasks/verify.yml"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_root(self.root)


if __name__ == "__main__":
    unittest.main()
