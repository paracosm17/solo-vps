from __future__ import annotations

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_metrics_credentials_contract.py"


class MetricsCredentialContractTests(unittest.TestCase):
    def test_current_tree_passes(self) -> None:
        result = subprocess.run(["python3", str(VALIDATOR), str(ROOT)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS metrics credential contract", result.stdout)


if __name__ == "__main__":
    unittest.main()
