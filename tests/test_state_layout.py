from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from scripts.validate_state_layout import StateLayoutError, validate


ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "scripts/init_local.py"


class StateLayoutTests(unittest.TestCase):
    def test_repository_contract_passes(self) -> None:
        validate(ROOT)

    def test_init_creates_external_state_without_touching_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-state-") as tmp:
            base = Path(tmp)
            source = base / "source"
            state = base / "state"
            (source / "config").mkdir(parents=True)
            (source / "ansible/inventories/example").mkdir(parents=True)
            (source / "config/config.example.yml").write_text("server: {}\n", encoding="utf-8")
            (source / "ansible/inventories/example/hosts.yml").write_text("all: {}\n", encoding="utf-8")
            before = sorted(str(path.relative_to(source)) for path in source.rglob("*") if path.is_file())

            result = subprocess.run(
                [
                    sys.executable,
                    str(INIT),
                    "--root",
                    str(source),
                    "--data-dir",
                    str(state),
                    "--config",
                    str(state / "config/config.yml"),
                    "--inventory",
                    str(state / "config/hosts.yml"),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((state / "config/config.yml").is_file())
            self.assertTrue((state / "config/hosts.yml").is_file())
            after = sorted(str(path.relative_to(source)) for path in source.rglob("*") if path.is_file())
            self.assertEqual(before, after)
            self.assertIn("source checkout mutated: no", result.stdout)

    def test_init_migrates_legacy_files_without_deleting_them(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-state-") as tmp:
            base = Path(tmp)
            source = base / "source"
            state = base / "state"
            (source / "config").mkdir(parents=True)
            (source / "ansible/inventories/example").mkdir(parents=True)
            (source / "ansible/inventories/local").mkdir(parents=True)
            (source / "config/config.example.yml").write_text("example: true\n", encoding="utf-8")
            (source / "ansible/inventories/example/hosts.yml").write_text("example: true\n", encoding="utf-8")
            (source / "config/config.yml").write_text("owner: config\n", encoding="utf-8")
            (source / "ansible/inventories/local/hosts.yml").write_text("owner: inventory\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(INIT),
                    "--root",
                    str(source),
                    "--data-dir",
                    str(state),
                    "--config",
                    str(state / "config/config.yml"),
                    "--inventory",
                    str(state / "config/hosts.yml"),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((state / "config/config.yml").read_text(), "owner: config\n")
            self.assertEqual((state / "config/hosts.yml").read_text(), "owner: inventory\n")
            self.assertTrue((source / "config/config.yml").exists())
            self.assertTrue((source / "ansible/inventories/local/hosts.yml").exists())
            self.assertIn("migration:", result.stdout)

    def test_init_refuses_state_inside_checkout(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-state-") as tmp:
            source = Path(tmp) / "source"
            (source / "config").mkdir(parents=True)
            (source / "ansible/inventories/example").mkdir(parents=True)
            (source / "config/config.example.yml").write_text("server: {}\n", encoding="utf-8")
            (source / "ansible/inventories/example/hosts.yml").write_text("all: {}\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(INIT),
                    "--root",
                    str(source),
                    "--data-dir",
                    str(source / ".state"),
                    "--config",
                    str(source / ".state/config.yml"),
                    "--inventory",
                    str(source / ".state/hosts.yml"),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("must be outside", result.stderr)

    def test_checkout_local_default_regression_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="solo-vps-layout-") as tmp:
            root = Path(tmp)
            for rel in (
                "Makefile",
                "scripts/init_local.py",
                "scripts/configure_inventory.py",
                "scripts/handoff_admin_workspace.py",
                "scripts/init_sops_policy.py",
                "docs/state-layout.md",
            ):
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, dest)
            makefile = root / "Makefile"
            text = makefile.read_text(encoding="utf-8")
            text = text.replace("CONFIG ?= $(SOLO_VPS_CONFIG_DIR)/config.yml", "CONFIG ?= config/config.yml")
            makefile.write_text(text, encoding="utf-8")
            with self.assertRaises(StateLayoutError):
                validate(root)


if __name__ == "__main__":
    unittest.main()
