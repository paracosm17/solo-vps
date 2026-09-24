from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_observability_credentials_contract.py"
FILES = [
    "Makefile",
    "scripts/observability_credentials_common.py",
    "scripts/observability_secret_bundle.py",
    "scripts/install_observability_credentials.py",
    "scripts/windows/init-observability-secrets.ps1",
    "scripts/windows/test-observability-secrets.ps1",
    "scripts/windows/push-observability-secrets.ps1",
    "docs/operations/observability.md",
    "docs/operations/observability.ru.md",
    "docs/secrets-sops-age.md",
]


class ObservabilityCredentialsContractTests(unittest.TestCase):
    def _tree(self) -> pathlib.Path:
        temp = pathlib.Path(tempfile.mkdtemp(prefix="solo-vps-observability-credentials-"))
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
        self.assertIn("PASS observability credential contract", result.stdout)

    def test_rejects_missing_runtime_boundary(self) -> None:
        root = self._tree()
        path = root / "scripts/install_observability_credentials.py"
        path.write_text(path.read_text().replace('            print("  telemetry sent: no")\n', ""))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_windows_push(self) -> None:
        root = self._tree()
        path = root / "scripts/windows/push-observability-secrets.ps1"
        path.write_text(path.read_text().replace("observability.enc.yaml", "missing.enc.yaml"))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
