from __future__ import annotations

import pathlib
import shutil
import tempfile
import unittest

from scripts.validate_docker_contract import ContractError, validate_root


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


class DockerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name) / "repo"
        # The validator consumes only this role; never copy local archives, Git or toolchains.
        shutil.copytree(PROJECT_ROOT / "ansible/roles/docker", self.root / "ansible/roles/docker")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_current_contract_passes(self) -> None:
        validate_root(self.root)

    def test_rejects_cache_valid_time_after_repository_add(self) -> None:
        path = self.root / "ansible/roles/docker/tasks/main.yml"
        text = path.read_text(encoding="utf-8")
        text = text.replace("    update_cache: true\n", "    update_cache: true\n    cache_valid_time: 3600\n", 1)
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_install_before_repository_refresh(self) -> None:
        path = self.root / "ansible/roles/docker/tasks/main.yml"
        text = path.read_text(encoding="utf-8")
        refresh = "Refresh APT metadata after Docker repository changes or before first install"
        install = "Install Docker Engine, Buildx, and Compose plugin packages"
        text = text.replace(refresh, "TEMP_REFRESH", 1).replace(install, refresh, 1).replace("TEMP_REFRESH", install, 1)
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_candidate_gate(self) -> None:
        path = self.root / "ansible/roles/docker/tasks/main.yml"
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "Refuse Docker installation when the official repository has no package candidate",
            "Skip Docker package candidate enforcement",
            1,
        )
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_future_major_candidate_gate(self) -> None:
        path = self.root / "ansible/roles/docker/tasks/main.yml"
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "solo_vps_docker_ce_candidate_major in solo_vps_docker_supported_major_versions",
            "solo_vps_docker_ce_candidate_major >= 1",
            1,
        )
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_existing_engine_pre_mutation_gate(self) -> None:
        path = self.root / "ansible/roles/docker/tasks/main.yml"
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "solo_vps_docker_existing_server_major in solo_vps_docker_supported_major_versions",
            "solo_vps_docker_existing_server_major >= 1",
            1,
        )
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_installed_engine_verify_gate(self) -> None:
        path = self.root / "ansible/roles/docker/tasks/verify.yml"
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "solo_vps_docker_server_major in solo_vps_docker_supported_major_versions",
            "solo_vps_docker_server_major >= 1",
            1,
        )
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_escaped_capture_backreference_regression(self) -> None:
        path = self.root / "ansible/roles/docker/tasks/main.yml"
        text = path.read_text(encoding="utf-8")
        safe = "regex_findall('^(?:[0-9]+:)?([0-9]+)[.]')"
        unsafe = r"regex_search('^(?:[0-9]+:)?([0-9]+)\\.', '\\1')"
        self.assertIn(safe, text)
        path.write_text(text.replace(safe, unsafe, 1), encoding="utf-8")
        with self.assertRaises(ContractError):
            validate_root(self.root)


if __name__ == "__main__":
    unittest.main()
