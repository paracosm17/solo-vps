from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from scripts.backup_credentials_common import (
    BackupCredentialError,
    canonical_json_bytes,
    parse_json_bytes,
    validate_payload,
)
from scripts import install_backup_credentials as installer
from scripts.install_backup_credentials import InstallError, install_payload, verify_file


VALID = {
    "AWS_ACCESS_KEY_ID": "example-access-key",
    "AWS_SECRET_ACCESS_KEY": "example-secret-key+/=",
    "RESTIC_PASSWORD": "example-restic-password-value",
}


class BackupCredentialSchemaTests(unittest.TestCase):
    def test_required_payload_roundtrip(self) -> None:
        raw = canonical_json_bytes(VALID)
        self.assertEqual(parse_json_bytes(raw), VALID)
        self.assertTrue(raw.endswith(b"\n"))

    def test_optional_session_token_is_supported(self) -> None:
        payload = dict(VALID, AWS_SESSION_TOKEN="temporary-token+/=")
        self.assertEqual(validate_payload(payload), payload)

    def test_unknown_key_is_rejected(self) -> None:
        payload = dict(VALID, EXTRA_SECRET="no")
        with self.assertRaises(BackupCredentialError):
            validate_payload(payload)

    def test_missing_key_is_rejected(self) -> None:
        payload = dict(VALID)
        payload.pop("RESTIC_PASSWORD")
        with self.assertRaises(BackupCredentialError):
            validate_payload(payload)

    def test_multiline_value_is_rejected(self) -> None:
        payload = dict(VALID, AWS_SECRET_ACCESS_KEY="first\nsecond")
        with self.assertRaises(BackupCredentialError):
            validate_payload(payload)


class BackupCredentialInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.uid = os.getuid()
        self.gid = os.getgid()

    def test_install_is_atomic_mode_safe_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "backup" / "credentials.json"
            changed = install_payload(VALID, path, owner_uid=self.uid, owner_gid=self.gid)
            self.assertTrue(changed)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(verify_file(path, owner_uid=self.uid, owner_gid=self.gid), VALID)

            changed = install_payload(VALID, path, owner_uid=self.uid, owner_gid=self.gid)
            self.assertFalse(changed)

    def test_changed_payload_replaces_valid_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "backup" / "credentials.json"
            install_payload(VALID, path, owner_uid=self.uid, owner_gid=self.gid)
            updated = dict(VALID, RESTIC_PASSWORD="new-restic-password")
            self.assertTrue(
                install_payload(updated, path, owner_uid=self.uid, owner_gid=self.gid)
            )
            self.assertEqual(
                verify_file(path, owner_uid=self.uid, owner_gid=self.gid), updated
            )

    def test_invalid_existing_file_is_not_silently_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "backup" / "credentials.json"
            path.parent.mkdir(mode=0o700)
            path.write_text("not-json\n", encoding="utf-8")
            path.chmod(0o600)
            with self.assertRaises(InstallError):
                install_payload(VALID, path, owner_uid=self.uid, owner_gid=self.gid)

    def test_symlink_destination_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "real.json"
            target.write_text("{}\n", encoding="utf-8")
            directory = root / "backup"
            directory.mkdir(mode=0o700)
            path = directory / "credentials.json"
            path.symlink_to(target)
            with self.assertRaises(InstallError):
                install_payload(VALID, path, owner_uid=self.uid, owner_gid=self.gid)

    def test_symlink_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            linked = root / "backup"
            linked.symlink_to(real, target_is_directory=True)
            with self.assertRaises(InstallError):
                install_payload(
                    VALID,
                    linked / "credentials.json",
                    owner_uid=self.uid,
                    owner_gid=self.gid,
                )


    def test_cli_keeps_symlink_visible_to_fail_closed_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "real.json"
            target.write_bytes(canonical_json_bytes(VALID))
            link = root / "credentials.json"
            link.symlink_to(target)
            with mock.patch.object(installer, "_require_root"), mock.patch(
                "sys.argv", ["install_backup_credentials.py", "verify", "--path", str(link)]
            ), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(installer.main(), 2)
            self.assertEqual(target.read_bytes(), canonical_json_bytes(VALID))



if __name__ == "__main__":
    unittest.main()
