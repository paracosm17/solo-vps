from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validate_external_uptime_contract import ContractError, validate


ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "docs/contracts/external-uptime-policy.yml",
    "docs/operations/external-uptime.md",
    "scripts/external_uptime.py",
    "Makefile",
    "README.md",
    "docs/index.md",
)


class ExternalUptimeContractTests(unittest.TestCase):
    def fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="solo-vps-uptime-contract-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        for rel in FILES:
            src = ROOT / rel
            dst = temp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return temp

    def replace(self, root: Path, rel: str, old: str, new: str) -> None:
        path = root / rel
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_current_contract_passes(self) -> None:
        validate(ROOT)

    def test_same_vps_target_boundary_is_required(self) -> None:
        root = self.fixture()
        self.replace(root, "docs/contracts/external-uptime-policy.yml", "same_vps_monitor_is_not_sufficient: true", "same_vps_monitor_is_not_sufficient: false")
        with self.assertRaises(ContractError):
            validate(root)

    def test_https_health_endpoint_is_required(self) -> None:
        root = self.fixture()
        self.replace(root, "docs/contracts/external-uptime-policy.yml", "scheme: https", "scheme: http")
        with self.assertRaises(ContractError):
            validate(root)

    def test_provider_confirmation_retries_are_required(self) -> None:
        root = self.fixture()
        self.replace(
            root,
            "docs/contracts/external-uptime-policy.yml",
            "provider_confirmation_retries_required: true",
            "provider_confirmation_retries_required: false",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_whole_target_v3_requirement_is_required(self) -> None:
        root = self.fixture()
        self.replace(root, "docs/contracts/external-uptime-policy.yml", "crit015_v3_requires_whole_target_shutdown: true", "crit015_v3_requires_whole_target_shutdown: false")
        with self.assertRaises(ContractError):
            validate(root)

    def test_make_source_gate_cannot_drop_uptime_tests(self) -> None:
        root = self.fixture()
        self.replace(
            root,
            "Makefile",
            "test-release-process validate-external-uptime test-external-uptime ## Run the bounded source-only part of the public hosted CI gate",
            "test-release-process validate-external-uptime ## Run the bounded source-only part of the public hosted CI gate",
        )
        with self.assertRaises(ContractError):
            validate(root)

    def test_docs_must_forbid_raw_management_ports(self) -> None:
        root = self.fixture()
        self.replace(root, "docs/operations/external-uptime.md", "8000/6001/6002", "management ports")
        with self.assertRaises(ContractError):
            validate(root)

    def test_evidence_must_not_store_health_url(self) -> None:
        root = self.fixture()
        self.replace(root, "scripts/external_uptime.py", '"health_url_retained": False', '"health_url_retained": True')
        with self.assertRaises(ContractError):
            validate(root)


if __name__ == "__main__":
    unittest.main()
