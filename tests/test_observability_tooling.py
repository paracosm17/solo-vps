from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_observability_tooling.py"
FILES = [
    "Makefile",
    "ansible/roles/observability/defaults/main.yml",
    "ansible/roles/observability/tasks/assert-config.yml",
    "ansible/roles/observability/tasks/inspect-existing.yml",
    "ansible/roles/observability/tasks/install-alloy.yml",
    "ansible/roles/observability/tasks/verify-tooling.yml",
    "ansible/roles/observability/tasks/main.yml",
    "ansible/playbooks/observability-tooling.yml",
    "ansible/playbooks/verify-observability-tooling.yml",
]


class ObservabilityToolingContractTests(unittest.TestCase):
    def _tree(self) -> pathlib.Path:
        temp = pathlib.Path(tempfile.mkdtemp(prefix="solo-vps-observability-tooling-"))
        self.addCleanup(shutil.rmtree, temp, True)
        for relative in FILES:
            source = ROOT / relative
            dest = temp / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
        return temp

    def _run(self, root: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(VALIDATOR), str(root)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_current_tree_passes(self) -> None:
        result = self._run(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS observability tooling contract", result.stdout)

    def test_rejects_unpinned_version(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/defaults/main.yml"
        path.write_text(path.read_text().replace('solo_vps_alloy_version: "1.18.1"', 'solo_vps_alloy_version: "latest"'))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_service_start_in_tooling_slice(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/install-alloy.yml"
        path.write_text(path.read_text() + "\n- name: bad\n  ansible.builtin.systemd_service:\n    name: alloy\n    state: started\n")
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_docker_socket_access_in_tooling_slice(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/install-alloy.yml"
        path.write_text(path.read_text() + "\n# /var/run/docker.sock\n")
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_makefile_target(self) -> None:
        root = self._tree()
        path = root / "Makefile"
        path.write_text(path.read_text().replace("observability-tooling: doctor-admin-local", "observability-tooling-broken: doctor-admin-local"))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)


    def test_rejects_missing_aggregate_observability_dependency(self) -> None:
        root = self._tree()
        path = root / "Makefile"
        path.write_text(path.read_text().replace(" validate-observability-log-drain test-observability-log-drain", ""))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_explicit_boundary(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/verify-tooling.yml"
        path.write_text(path.read_text().replace("      remote_backend_configured: false\n", ""))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
