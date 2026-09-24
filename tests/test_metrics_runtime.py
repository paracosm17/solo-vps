from __future__ import annotations

import pathlib
import subprocess
import tempfile
import shutil
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_metrics_runtime.py"
RUNTIME_FILES = [
    "Makefile",
    "ansible/roles/metrics/defaults/main.yml",
    "ansible/roles/metrics/tasks/install-runtime.yml",
    "ansible/roles/metrics/tasks/verify-runtime.yml",
    "ansible/roles/metrics/templates/config.alloy.j2",
    "ansible/roles/metrics/templates/solo-vps-metrics.service.j2",
    "ansible/playbooks/metrics-runtime.yml",
    "ansible/playbooks/verify-metrics-runtime.yml",
    "docs/operations/metrics.md",
    "docs/operations/metrics.ru.md",
]


class MetricsRuntimeContractTests(unittest.TestCase):
    def _run(self, root: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["python3", str(VALIDATOR), str(root)], capture_output=True, text=True, check=False)

    def test_current_tree_passes(self) -> None:
        result = self._run(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS host metrics runtime contract", result.stdout)

    def test_rejects_root_service(self) -> None:
        temp = pathlib.Path(tempfile.mkdtemp(prefix="solo-vps-metrics-runtime-"))
        self.addCleanup(shutil.rmtree, temp, True)
        for relative in RUNTIME_FILES:
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        unit = temp / "ansible/roles/metrics/templates/solo-vps-metrics.service.j2"
        unit.write_text(unit.read_text().replace("User={{ solo_vps_metrics_user }}", "User=root"))
        result = self._run(temp)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_docker_dependency(self) -> None:
        temp = pathlib.Path(tempfile.mkdtemp(prefix="solo-vps-metrics-runtime-"))
        self.addCleanup(shutil.rmtree, temp, True)
        for relative in RUNTIME_FILES:
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        config = temp / "ansible/roles/metrics/templates/config.alloy.j2"
        config.write_text(config.read_text() + "\n// docker dependency\n")
        result = self._run(temp)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
