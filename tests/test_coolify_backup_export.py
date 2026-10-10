import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from scripts.coolify_backup_collect import add_tree
from scripts.coolify_backup_export import ROOT, connection, export, payload, verify_ciphertext, verify_members


def archive(extra=None, wrong_hash=False):
    files = {name: b"fixture" for name in (
        "control-plane/coolify-db.dump", "control-plane/control-plane.tar.gz",
        "control-plane/checkpoint.json", "runtime.json", "operator-config/config.yml",
        "operator-config/hosts.yml", "proxy/docker-compose.yml")}
    if extra:
        files.update(extra)
    manifest = {"schema": 1, "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    if wrong_hash:
        manifest["files"]["runtime.json"] = "0" * 64
    files["manifest.json"] = json.dumps(manifest).encode()
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode="w:gz") as tar:
        for name, data in files.items():
            item = tarfile.TarInfo(name)
            item.size = len(data)
            tar.addfile(item, io.BytesIO(data))
    return result.getvalue()


class ExportTests(unittest.TestCase):
    def test_source_checkout_output_is_rejected_before_collection(self):
        with self.assertRaises(ValueError):
            export([], Path("unused"), Path("unused"), ROOT / "fixture-backup.age", b"")

    @unittest.skipUnless(sys.platform.startswith("linux"), "POSIX process/pipe test")
    def test_decrypt_stream_checks_hash_and_authentication_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = archive()
            source = root / "fixture.age"
            source.write_bytes(data)
            fake = root / "decrypt-fixture"
            for status in (0, 2):
                fake.write_text("#!/usr/bin/env python3\nimport pathlib,sys\nsys.stdout.buffer.write(pathlib.Path(sys.argv[-1]).read_bytes());sys.exit(" + str(status) + ")\n")
                fake.chmod(0o700)
                if status == 0:
                    verify_ciphertext(fake, root / "key", source, hashlib.sha256(data).hexdigest())
                with self.assertRaises(ValueError):
                    verify_ciphertext(fake, root / "key", source, "0" * 64)
                if status:
                    with self.assertRaises(ValueError):
                        verify_ciphertext(fake, root / "key", source, hashlib.sha256(data).hexdigest())

    def test_verified_members_and_hash_corruption(self):
        verify_members(io.BytesIO(archive()))
        for data in (archive(wrong_hash=True), archive({"../outside": b"bad"}), archive()[:-30]):
            with self.assertRaises((ValueError, EOFError, tarfile.TarError)):
                verify_members(io.BytesIO(data))

    def test_code_payload_has_only_collector_and_checkpoint(self):
        with zipfile.ZipFile(io.BytesIO(payload())) as zip:
            self.assertEqual(set(zip.namelist()), {"__main__.py", "coolify_upgrade_checkpoint.py"})
            self.assertNotIn(b"AGE-SECRET-KEY-", payload())

    def test_connection_rejects_injection_root_and_multiple_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "hosts.yml"
            inventory.write_text("all:\n  hosts:\n    one: {}\n    two: {}\n")
            args = SimpleNamespace(host="", user="", inventory=inventory, ssh_identity="")
            with self.assertRaises(ValueError):
                connection(args)
            for host, user in (("example.org;id", "ops"), ("example.org", "root"), ("example.org", "ops;id")):
                args.host, args.user = host, user
                with self.assertRaises(ValueError):
                    connection(args)
            args.host, args.user = "example.org", "ops"
            command, _, _ = connection(args)
            self.assertIn("StrictHostKeyChecking=yes", command)

    @unittest.skipUnless(sys.platform.startswith("linux"), "POSIX process/pipe test")
    def test_failed_ssh_or_verification_never_publish_and_collisions_preserve_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Fixture passthrough substitutes only the age process; no cryptographic claim.
            age = root / "age-fixture"
            age.write_text("#!/usr/bin/env python3\nimport shutil,sys\nshutil.copyfileobj(sys.stdin.buffer,sys.stdout.buffer)\n")
            age.chmod(0o700)
            key = root / "key"
            key.write_text("unused fixture")
            out = root / "backup.age"
            for status in (1, 0):
                command = [sys.executable, "-c", "import sys;sys.stdin.buffer.read();sys.stdout.buffer.write(b'partial');sys.stderr.write('SOLO_BACKUP_SHA256='+ '0'*64+'\\n');sys.exit(" + str(status) + ")"]
                with patch("scripts.coolify_backup_export.verify_ciphertext", side_effect=ValueError("bad checksum")):
                    with self.assertRaises(ValueError):
                        export(command, age, key, out, b"code")
                self.assertFalse(out.exists())
                self.assertEqual(list(root.glob("*.partial")), [])
                self.assertEqual(list(root.glob(".*.partial")), [])
            out.write_bytes(b"previous backup")
            with self.assertRaises(ValueError):
                export([], age, key, out, b"code")
            self.assertEqual(out.read_bytes(), b"previous backup")

    @unittest.skipUnless(sys.platform.startswith("linux"), "POSIX process/pipe test")
    def test_success_is_published_only_after_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            age = root / "age-fixture"
            age.write_text("#!/usr/bin/env python3\nimport shutil,sys\nshutil.copyfileobj(sys.stdin.buffer,sys.stdout.buffer)\n")
            age.chmod(0o700)
            out = root / "backup.age"
            data = archive()
            script = "import sys;sys.stdin.buffer.read();sys.stdout.buffer.write(" + repr(data) + ");sys.stderr.write('SOLO_BACKUP_SHA256=" + hashlib.sha256(data).hexdigest() + "\\n')"
            with patch("scripts.coolify_backup_export.verify_ciphertext") as verify:
                export([sys.executable, "-c", script], age, root / "key", out, b"code")
                verify.assert_called_once()
            self.assertEqual(out.read_bytes(), data)
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(sys.platform.startswith("linux"), "POSIX process/pipe test")
    def test_failed_age_never_publishes_even_when_ssh_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            age = root / "age-failure"
            age.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdin.buffer.read();sys.exit(2)\n")
            age.chmod(0o700)
            command = [sys.executable, "-c", "import sys;sys.stdin.buffer.read();sys.stdout.buffer.write(b'fixture');sys.stderr.write('SOLO_BACKUP_SHA256='+'0'*64+'\\n')"]
            with self.assertRaises(ValueError):
                export(command, age, root / "key", root / "backup.age", b"code")
            self.assertFalse((root / "backup.age").exists())
            self.assertEqual(list(root.glob(".*.partial")), [])

    def test_collection_rejects_symlinks_and_excludes_access_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "acme.json").write_text("fixture certificates")
            (root / "access.log").write_text("private requests")
            hashes = {}
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w") as tar:
                add_tree(tar, root, "proxy", hashes)
            self.assertEqual(set(hashes), {"proxy/acme.json"})
            try:
                (root / "link").symlink_to(root / "acme.json")
            except OSError:
                self.skipTest("symlinks unavailable")
            with tarfile.open(fileobj=io.BytesIO(), mode="w") as tar:
                with self.assertRaises(ValueError):
                    add_tree(tar, root, "proxy", {})
