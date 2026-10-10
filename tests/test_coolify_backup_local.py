import hashlib
import io
from contextlib import redirect_stderr
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.coolify_backup_collect import capture_lock, collect
from scripts.coolify_backup_common import receive_encrypted
from scripts.coolify_backup_local import main, public_recipient

PUBLIC = "age1s3cqcks5genc6ru8chl0hkkd04zmxvczsvdxq99ekffe4gmvjpzsedk23c"


class LocalBackupTests(unittest.TestCase):
    def test_only_a_public_recipient_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recipient.txt"
            with self.assertRaises(ValueError):
                public_recipient(path)
            for value in ("AGE-SECRET-KEY-test", PUBLIC + "\n" + PUBLIC, "age1invalid", "x" * 300):
                path.write_text(value)
                with self.assertRaises(ValueError):
                    public_recipient(path)
            path.write_text(PUBLIC + "\n")
            self.assertEqual(public_recipient(path), PUBLIC)
            link = Path(directory) / "link"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                public_recipient(link)

    def test_shared_capture_lock_rejects_overlap_and_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "exports"
            with capture_lock(root):
                with self.assertRaises(BlockingIOError):
                    with capture_lock(root):
                        self.fail("second capture must not acquire lock")
            with capture_lock(root):
                pass
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)

    def test_pending_install_or_upgrade_is_rejected_before_dump(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for marker in (".solo-vps-upgrading", ".solo-vps-installing"):
                path = root / marker
                path.touch()
                with patch("scripts.coolify_backup_collect.checkpoint") as dump:
                    with self.assertRaises(ValueError):
                        collect(root, root, root, root)
                    dump.assert_not_called()
                path.unlink()

    def test_local_pipeline_uses_public_recipient_and_publishes_only_complete_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            age = root / "age-fixture"
            arg_file = root / "arguments"
            age.write_text("#!/usr/bin/env python3\nimport pathlib,shutil,sys\npathlib.Path(" + repr(str(arg_file)) + ").write_text(' '.join(sys.argv[1:]));shutil.copyfileobj(sys.stdin.buffer,sys.stdout.buffer)\n")
            age.chmod(0o700)
            source = b"no private identity in this fixture"
            checksum = hashlib.sha256(source).hexdigest()
            for expected in ("0" * 64, checksum):
                command = [sys.executable, "-c", "import sys;sys.stdout.buffer.write(" + repr(source) + ");sys.stderr.write('SOLO_BACKUP_SHA256=" + expected + "\\n')"]
                output = root / "backup.age"
                if expected != checksum:
                    with self.assertRaises(ValueError):
                        receive_encrypted(command, age, ["-r", PUBLIC], output)
                    self.assertFalse(output.exists())
                else:
                    receive_encrypted(command, age, ["-r", PUBLIC], output)
                    self.assertEqual(output.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(output.read_bytes(), source)
            self.assertEqual(arg_file.read_text(), "--encrypt -r " + PUBLIC)
            self.assertEqual(list(root.glob(".*.partial")), [])

    def test_root_context_is_rejected_before_reading_inputs(self):
        with patch("sys.argv", ["backup", "--data-dir", "/unused", "--recipient-file", "/unused"]), \
                patch("scripts.coolify_backup_local.os.geteuid", return_value=0), \
                patch("scripts.coolify_backup_local.public_recipient") as recipient, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                main()
            self.assertEqual(result.exception.code, 2)
            recipient.assert_not_called()

