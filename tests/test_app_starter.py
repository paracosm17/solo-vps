from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.create_app import ROOT, create_app


class AppStarterTests(unittest.TestCase):
    def test_generated_application_runs_its_complete_portable_suite(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory) / "app")
            self.assertIn("APP_DIR: .", (app / ".github/workflows/app.yml").read_text())
            self.assertFalse((app / ".git").exists())
            self.assertFalse((app / "config").exists())
            result = subprocess.run(
                [sys.executable, "-B", "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py"],
                cwd=app, capture_output=True, text=True, timeout=60, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_existing_application_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "app"
            app.mkdir()
            (app / "app.py").write_text("user code")
            with self.assertRaises(ValueError):
                create_app(app)
            self.assertEqual((app / "app.py").read_text(), "user code")

    def test_checkout_destination_is_rejected_before_writing(self):
        with self.assertRaises(ValueError):
            create_app(ROOT / "generated-app-must-not-exist")
        self.assertFalse((ROOT / "generated-app-must-not-exist").exists())
