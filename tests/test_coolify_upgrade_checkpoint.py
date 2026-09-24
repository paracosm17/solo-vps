from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from scripts.coolify_upgrade_checkpoint import checkpoint


class CoolifyUpgradeCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        for name in ("source", "ssh", "applications"):
            (self.data / name).mkdir(parents=True)
        (self.data / "source/.env").write_text("APP_KEY=test-only\n")
        (self.data / "ssh/key").write_text("test-only-key")
        (self.data / ".solo-vps-managed").write_text("coolify_version=4.1.1\n")
        (self.data / "applications/private-data").write_text("excluded")
        self.destination = self.root / "checkpoints"

    def successful_run(self, argv, **kwargs):
        if "pg_restore" in argv:
            self.assertEqual(kwargs["stdin"].read(), b"PGDMP test archive")
        else:
            kwargs["stdout"].write(b"PGDMP test archive")
        return subprocess.CompletedProcess(argv, 0)

    def test_preserves_configuration_and_database_with_matching_hashes(self):
        result = checkpoint(self.data, self.destination, self.successful_run)
        manifest = json.loads((result / "checkpoint.json").read_text())
        for name, expected in manifest["files"].items():
            self.assertEqual(hashlib.sha256((result / name).read_bytes()).hexdigest(), expected)
        with tarfile.open(result / "control-plane.tar.gz") as archive:
            self.assertIn("source/.env", archive.getnames())
            self.assertIn("ssh/key", archive.getnames())
            self.assertNotIn("applications/private-data", archive.getnames())
        second = checkpoint(self.data, self.destination, self.successful_run)
        self.assertNotEqual(result, second)
        self.assertTrue((result / "checkpoint.json").exists())

    def test_dump_failure_never_produces_completion_manifest(self):
        def fail(argv, **kwargs):
            raise subprocess.CalledProcessError(1, argv)
        with self.assertRaises(subprocess.CalledProcessError):
            checkpoint(self.data, self.destination, fail)
        self.assertFalse(list(self.destination.glob("*/checkpoint.json")))

    def test_invalid_dump_never_produces_completion_manifest(self):
        def fail_validation(argv, **kwargs):
            if "pg_restore" in argv:
                raise subprocess.CalledProcessError(1, argv)
            return self.successful_run(argv, **kwargs)
        with self.assertRaises(subprocess.CalledProcessError):
            checkpoint(self.data, self.destination, fail_validation)
        self.assertFalse(list(self.destination.glob("*/checkpoint.json")))

    def test_missing_configuration_fails_before_dump(self):
        (self.data / ".solo-vps-managed").unlink()
        with self.assertRaises(ValueError):
            checkpoint(self.data, self.destination, self.successful_run)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
