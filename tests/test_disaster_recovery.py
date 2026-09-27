from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

from scripts import coolify_instance_restore as restore
from scripts import recovery_kit


class RecoveryKitTests(unittest.TestCase):
    def make_data_dir(self, root: Path) -> Path:
        data = root / "data"
        for part in ("config", "sops", "secrets", "state/database-backups"):
            (data / part).mkdir(parents=True, exist_ok=True)
        (data / "config/config.yml").write_text("server:\n  host: 203.0.113.10\n", encoding="utf-8")
        (data / "sops/.sops.yaml").write_text("creation_rules: []\n", encoding="utf-8")
        (data / "sops/production.txt").write_text("age1publicrecipient\n", encoding="utf-8")
        (data / "secrets/backup.enc.yaml").write_text("sops:\n  mac: ENC[AES256_GCM,data:x]\n", encoding="utf-8")
        (data / "state/database-backups/db123.json").write_text('{"database_uuid":"db123","backup_uuid":"bk123"}\n', encoding="utf-8")
        return data

    def test_export_and_verify_keep_only_recovery_safe_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self.make_data_dir(root)
            output = root / "kit.tar.gz"
            manifest = recovery_kit.export_kit(data, output, source_revision="abc123")
            self.assertEqual(manifest["source_revision"], "abc123")
            self.assertFalse(manifest["off_vps_copy_verified"])
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            verified = recovery_kit.verify_kit(output)
            self.assertIn("config/config.yml", verified["files"])
            with tarfile.open(output, "r:gz") as archive:
                names = set(archive.getnames())
            self.assertNotIn("config/hosts.yml", names)
            self.assertIn("state/database-backups/db123.json", names)

    def test_export_rejects_private_key_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self.make_data_dir(root)
            (data / "config/config.yml").write_bytes(b"-----BEGIN " + b"PRIVATE KEY-----\n")
            with self.assertRaises(recovery_kit.RecoveryKitError):
                recovery_kit.export_kit(data, root / "kit.tar.gz", source_revision="abc123")

    def test_extract_restores_only_verified_inputs_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self.make_data_dir(root)
            output = root / "kit.tar.gz"
            recovery_kit.export_kit(data, output, source_revision="abc123")
            restored = root / "restored"
            restored.mkdir(mode=0o700)
            manifest = recovery_kit.extract_kit(output, restored)
            self.assertEqual((restored / "config/config.yml").read_text(encoding="utf-8"), "server:\n  host: 203.0.113.10\n")
            self.assertTrue((restored / "secrets/backup.enc.yaml").is_file())
            self.assertEqual(len(manifest["files"]), 5)
            with self.assertRaises(recovery_kit.RecoveryKitError):
                recovery_kit.extract_kit(output, restored)

    def test_extract_rejects_permissive_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self.make_data_dir(root)
            output = root / "kit.tar.gz"
            recovery_kit.export_kit(data, output, source_revision="abc123")
            restored = root / "restored"
            restored.mkdir(mode=0o755)
            with self.assertRaises(recovery_kit.RecoveryKitError):
                recovery_kit.extract_kit(output, restored)

    def test_verify_rejects_tampered_manifest_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self.make_data_dir(root)
            output = root / "kit.tar.gz"
            recovery_kit.export_kit(data, output, source_revision="abc123")
            bad = root / "bad.tar.gz"
            with tarfile.open(output, "r:gz") as src, tarfile.open(bad, "w:gz") as dst:
                for member in src.getmembers():
                    content = src.extractfile(member).read()
                    if member.name == "config/config.yml":
                        content += b"# changed\n"
                    info = tarfile.TarInfo(member.name)
                    info.size = len(content)
                    info.mode = 0o600
                    dst.addfile(info, io.BytesIO(content))
            bad.chmod(0o600)
            with self.assertRaises(recovery_kit.RecoveryKitError):
                recovery_kit.verify_kit(bad)

    def test_verify_rejects_unexpected_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.tar.gz"
            with tarfile.open(path, "w:gz") as archive:
                data = b"x"
                info = tarfile.TarInfo("private/id_ed25519")
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            path.chmod(0o600)
            with self.assertRaises(recovery_kit.RecoveryKitError):
                recovery_kit.verify_kit(path)


class CoolifyInstanceRestoreTests(unittest.TestCase):
    def private_file(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(0o600)

    def fake_pg_restore_runner(self, command, **kwargs):
        if "--list" in command:
            return subprocess.CompletedProcess(command, 0, stdout="1; 0 0 TABLE public users postgres\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def prepare(self, root: Path):
        recovery_root = root / "staged"
        self.private_file(
            recovery_root / "data/coolify/source/.env",
            "APP_KEY=base64:oldkey\nDB_USERNAME=old\nDB_DATABASE=coolify\n",
        )
        key = recovery_root / "data/coolify/ssh/keys/id.ops@host.docker.internal"
        self.private_file(key, "synthetic-private-key-for-test\n")
        live_env = root / "live/.env"
        self.private_file(
            live_env,
            "APP_KEY=base64:newkey\nDB_USERNAME=coolify\nDB_DATABASE=coolify\nDB_PASSWORD=fresh-password\n",
        )
        marker = root / "live/.solo-vps-managed"
        self.private_file(marker, "managed_by=solo-vps\ncoolify_version=4.1.2\nlocalhost_user=ops\n")
        archive = root / "coolify.dmp"
        self.private_file(archive, "synthetic custom archive\n")
        return recovery_root, live_env, marker, archive

    def test_plan_uses_old_app_key_but_fresh_database_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recovery_root, live_env, marker, archive = self.prepare(root)
            with mock.patch.object(restore.shutil, "which", return_value="pg_restore"):
                plan = restore.build_plan(
                    archive=archive,
                    recovery_root=recovery_root,
                    expected_version="4.1.2",
                    live_env=live_env,
                    live_marker=marker,
                    runner=self.fake_pg_restore_runner,
                )
            self.assertEqual(plan.admin_user, "ops")
            self.assertEqual(plan.db_user, "coolify")
            self.assertTrue(plan.previous_app_key_present)
            self.assertEqual(plan.recovered_ssh_keys, 1)

    def test_previous_app_key_is_added_without_replacing_fresh_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            self.private_file(env, "APP_KEY=base64:new\nDB_PASSWORD=fresh\nREDIS_PASSWORD=redis\n")
            restore.update_previous_keys(env, "base64:old")
            values = restore.parse_env(env)
            self.assertEqual(values["APP_KEY"], "base64:new")
            self.assertEqual(values["DB_PASSWORD"], "fresh")
            self.assertEqual(values["REDIS_PASSWORD"], "redis")
            self.assertEqual(values["APP_PREVIOUS_KEYS"], "base64:old")

    def test_previous_key_update_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            self.private_file(env, "APP_KEY=base64:new\nAPP_PREVIOUS_KEYS=base64:older\n")
            restore.update_previous_keys(env, "base64:old")
            restore.update_previous_keys(env, "base64:old")
            values = restore.parse_env(env)
            self.assertEqual(values["APP_PREVIOUS_KEYS"], "base64:older,base64:old")

    def test_target_marker_requires_exact_root_private_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "marker"
            marker.write_text("recovery-1234\n", encoding="utf-8")
            marker.chmod(0o600)
            with mock.patch.object(restore.os, "geteuid", return_value=0):
                with self.assertRaises(restore.CoolifyInstanceRestoreError):
                    restore._require_target_marker(marker, "different-1234")

    def test_plan_rejects_old_env_without_app_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recovery_root, live_env, marker, archive = self.prepare(root)
            self.private_file(recovery_root / "data/coolify/source/.env", "DB_USERNAME=old\n")
            with mock.patch.object(restore.shutil, "which", return_value="pg_restore"):
                with self.assertRaises(restore.CoolifyInstanceRestoreError):
                    restore.build_plan(
                        archive=archive,
                        recovery_root=recovery_root,
                        expected_version="4.1.2",
                        live_env=live_env,
                        live_marker=marker,
                        runner=self.fake_pg_restore_runner,
                    )

    def test_archive_inspection_uses_running_coolify_db_when_host_pg_restore_missing(self):
        seen = {}

        def runner(command, **kwargs):
            seen["command"] = command
            seen["stdin_open"] = not kwargs["stdin"].closed
            seen["docker_host"] = kwargs["env"]["DOCKER_HOST"]
            seen["docker_context_present"] = "DOCKER_CONTEXT" in kwargs["env"]
            return subprocess.CompletedProcess(command, 0, stdout=b"; header\n1; 1259 1234 TABLE public.demo postgres\n", stderr=b"")

        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "coolify.dmp"
            self.private_file(archive, "archive\n")
            def which(name):
                return "/usr/bin/docker" if name == "docker" else None
            with mock.patch.object(restore.shutil, "which", side_effect=which):
                with mock.patch.dict(restore.os.environ, {"DOCKER_CONTEXT": "remote", "DOCKER_HOST": "tcp://example.invalid:2375"}):
                    self.assertEqual(restore.inspect_archive(archive, runner=runner), 1)
        self.assertEqual(seen["command"], ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock", "exec", "-i", "coolify-db", "pg_restore", "--list"])
        self.assertTrue(seen["stdin_open"])
        self.assertEqual(seen["docker_host"], "unix:///var/run/docker.sock")
        self.assertFalse(seen["docker_context_present"])

    def test_archive_inspection_rejects_container_pg_restore_failure(self):
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b"bad archive")

        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "coolify.dmp"
            self.private_file(archive, "archive\n")
            def which(name):
                return "/usr/bin/docker" if name == "docker" else None
            with mock.patch.object(restore.shutil, "which", side_effect=which):
                with self.assertRaisesRegex(restore.CoolifyInstanceRestoreError, "bad archive"):
                    restore.inspect_archive(archive, runner=runner)

    def test_inspect_cli_reports_missing_pg_restore_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "coolify.dmp"
            self.private_file(archive, "archive\n")
            with mock.patch.object(restore.shutil, "which", return_value=None):
                with mock.patch.object(restore.sys, "argv", ["restore", "inspect", "--archive", str(archive)]):
                    with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
                        self.assertEqual(restore.main(), 2)
            self.assertIn("pg_restore or a running Coolify database container is required", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_archive_inspection_rejects_empty_archive_listing(self):
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, stdout="; header only\n", stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "coolify.dmp"
            self.private_file(archive, "archive\n")
            with mock.patch.object(restore.shutil, "which", return_value="pg_restore"):
                with self.assertRaises(restore.CoolifyInstanceRestoreError):
                    restore.inspect_archive(archive, runner=runner)


    def test_recovered_key_directory_rejects_unexpected_regular_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            keys = root / "keys"
            self.private_file(keys / "notes.txt", "not a Coolify key\n")
            with self.assertRaises(restore.CoolifyInstanceRestoreError):
                restore._key_files(keys)

    def test_localhost_private_key_uuid_resolves_exact_server_zero_relation(self):
        seen = {}

        def runner(command, **kwargs):
            seen["command"] = command
            return subprocess.CompletedProcess(command, 0, stdout="localhostkey123\n", stderr="")

        value = restore.resolve_localhost_private_key_uuid("coolify", "coolify", runner=runner)
        self.assertEqual(value, "localhostkey123")
        sql = seen["command"][-1]
        self.assertIn("JOIN private_keys", sql)
        self.assertIn("s.id = 0", sql)

    def test_localhost_private_key_uuid_rejects_ambiguous_result(self):
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, stdout="keyone123\nkeytwo123\n", stderr="")

        with self.assertRaises(restore.CoolifyInstanceRestoreError):
            restore.resolve_localhost_private_key_uuid("coolify", "coolify", runner=runner)

    def test_restore_keys_authorizes_only_database_associated_localhost_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recovery_root = root / "staged"
            keys = recovery_root / "data/coolify/ssh/keys"
            self.private_file(keys / "ssh_key@localhostkey123", "local-private\n")
            self.private_file(keys / "ssh_key@remotehostkey123", "remote-private\n")
            self.private_file(keys / "ssh_key@remotehostkey123.lock", "")
            live_keys = root / "live-keys"
            home = root / "home"
            home.mkdir()
            user = type("User", (), {"pw_dir": str(home), "pw_uid": os.getuid(), "pw_gid": os.getgid()})()

            def runner(command, **kwargs):
                path = Path(command[-1])
                if path.name == "ssh_key@localhostkey123":
                    return subprocess.CompletedProcess(command, 0, stdout="ssh-ed25519 LOCAL\n", stderr="")
                return subprocess.CompletedProcess(command, 0, stdout="ssh-ed25519 REMOTE\n", stderr="")

            with mock.patch.object(restore.pwd, "getpwnam", return_value=user), mock.patch.object(restore.os, "chown"):
                count = restore.restore_keys(
                    recovery_root,
                    live_keys,
                    "ops",
                    "localhostkey123",
                    runner=runner,
                )
            self.assertEqual(count, 2)
            authorized = (home / ".ssh/authorized_keys").read_text(encoding="utf-8")
            self.assertIn("ssh-ed25519 LOCAL", authorized)
            self.assertNotIn("REMOTE", authorized)
            self.assertTrue((live_keys / "ssh_key@remotehostkey123").exists())
            self.assertFalse((live_keys / "ssh_key@remotehostkey123.lock").exists())

    def test_restore_keys_refuses_missing_database_associated_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recovery_root = root / "staged"
            self.private_file(recovery_root / "data/coolify/ssh/keys/ssh_key@otherkey123", "private\n")
            with self.assertRaises(restore.CoolifyInstanceRestoreError):
                restore.restore_keys(
                    recovery_root,
                    root / "live-keys",
                    "ops",
                    "localhostkey123",
                )


if __name__ == "__main__":
    unittest.main()
