from __future__ import annotations

from pathlib import Path
import contextlib
import io
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import backup_secret_bundle as bundle


PAYLOAD = {
    "AWS_ACCESS_KEY_ID": "example-access-id",
    "AWS_SECRET_ACCESS_KEY": "example-secret-value",
    "RESTIC_PASSWORD": "example-restic-password",
}


class BackupSecretBundleTests(unittest.TestCase):
    def test_init_writes_only_external_ciphertext(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "checkout"
            root.mkdir()
            policy = base / "state" / "sops" / ".sops.yaml"
            policy.parent.mkdir(parents=True)
            policy.write_text("creation_rules: []\n", encoding="utf-8")
            output = base / "state" / "secrets" / "backup.enc.yaml"

            with mock.patch.object(bundle, "_new_payload", return_value=PAYLOAD), mock.patch.object(
                bundle, "_run_sops", return_value=b"sops:\n  mac: ENC[example]\n"
            ), contextlib.redirect_stdout(io.StringIO()):
                bundle.init_bundle(root, policy, output, Path("/fake/sops"))

            self.assertTrue(output.is_file())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertFalse((root / "secrets" / "backup.enc.yaml").exists())
            encrypted = output.read_bytes()
            for value in PAYLOAD.values():
                self.assertNotIn(value.encode(), encrypted)

    def test_init_reuses_existing_decryptable_ciphertext(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "checkout"
            root.mkdir()
            policy = base / "state" / "sops" / ".sops.yaml"
            policy.parent.mkdir(parents=True)
            policy.write_text("creation_rules: []\n", encoding="utf-8")
            output = base / "state" / "secrets" / "backup.enc.yaml"
            output.parent.mkdir(parents=True)
            output.write_text("sops: {}\n", encoding="utf-8")
            key = base / "age-key.txt"
            key.write_text("synthetic-test-key\n", encoding="utf-8")
            stdout = io.StringIO()

            with mock.patch.object(bundle, "decrypt_bundle", return_value=PAYLOAD) as decrypt, mock.patch.object(
                bundle, "_new_payload"
            ) as new_payload, contextlib.redirect_stdout(stdout):
                bundle.init_bundle(root, policy, output, Path("/fake/sops"), key_file=key)

            decrypt.assert_called_once_with(policy, output, key, Path("/fake/sops"))
            new_payload.assert_not_called()
            self.assertIn("already exists; reusing it", stdout.getvalue())
            self.assertIn("existing ciphertext replaced: no", stdout.getvalue())

    def test_init_existing_ciphertext_with_wrong_key_requires_explicit_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "checkout"
            root.mkdir()
            policy = base / "state" / "sops" / ".sops.yaml"
            policy.parent.mkdir(parents=True)
            policy.write_text("creation_rules: []\n", encoding="utf-8")
            output = base / "state" / "secrets" / "backup.enc.yaml"
            output.parent.mkdir(parents=True)
            output.write_text("sops: {}\n", encoding="utf-8")
            key = base / "age-key.txt"
            key.write_text("synthetic-test-key\n", encoding="utf-8")

            with mock.patch.object(bundle, "decrypt_bundle", side_effect=bundle.BundleError("wrong key")):
                with self.assertRaises(bundle.BundleError) as raised:
                    bundle.init_bundle(root, policy, output, Path("/fake/sops"), key_file=key)

            self.assertIn("cannot be validated with the current age key", str(raised.exception))
            self.assertEqual(output.read_text(encoding="utf-8"), "sops: {}\n")

    def test_init_refuses_ciphertext_inside_source_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "checkout"
            root.mkdir()
            policy = Path(tmp) / "policy.yaml"
            policy.write_text("creation_rules: []\n", encoding="utf-8")
            output = root / "secrets" / "backup.enc.yaml"
            with mock.patch.object(bundle, "_new_payload", return_value=PAYLOAD), mock.patch.object(
                bundle, "_run_sops", return_value=b"sops:\n  mac: ENC[example]\n"
            ):
                with self.assertRaises(bundle.BundleError):
                    bundle.init_bundle(root, policy, output, Path("/fake/sops"))

    def test_init_refuses_dangling_ciphertext_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "checkout"
            root.mkdir()
            policy = base / "policy.yaml"
            policy.write_text("creation_rules: []\n", encoding="utf-8")
            output = base / "state" / "secrets" / "backup.enc.yaml"
            output.parent.mkdir(parents=True)
            output.symlink_to(base / "elsewhere" / "missing.enc.yaml")
            with mock.patch.object(bundle, "_new_payload", return_value=PAYLOAD), mock.patch.object(
                bundle, "_run_sops", return_value=b"sops:\n  mac: ENC[example]\n"
            ):
                with self.assertRaises(bundle.BundleError):
                    bundle.init_bundle(root, policy, output, Path("/fake/sops"))

    def test_decrypt_rejects_symlink_key_before_sops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            policy = base / "policy.yaml"
            policy.write_text("creation_rules: []\n", encoding="utf-8")
            encrypted = base / "backup.enc.yaml"
            encrypted.write_text("sops: {}\n", encoding="utf-8")
            real_key = base / "real-age-key.txt"
            real_key.write_text("synthetic-test-key\n", encoding="utf-8")
            key = base / "age-key.txt"
            key.symlink_to(real_key)
            with mock.patch.object(bundle, "_run_sops") as run:
                with self.assertRaises(bundle.BundleError):
                    bundle.decrypt_bundle(policy, encrypted, key, Path("/fake/sops"))
                run.assert_not_called()

    def test_sops_failure_suppresses_stderr(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["sops"], returncode=7, stdout=b"", stderr=b"do-not-surface-this-detail\n"
        )
        with mock.patch.object(bundle.subprocess, "run", return_value=completed):
            with self.assertRaises(bundle.BundleError) as raised:
                bundle._run_sops(Path("/fake/sops"), ["decrypt"])
        message = str(raised.exception)
        self.assertIn("exit code 7", message)
        self.assertIn("suppressed", message)
        self.assertNotIn("do-not-surface-this-detail", message)

    def test_push_uses_ssh_stdin_and_managed_remote_installer(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout=b"PASS backup runtime credentials installed\n",
            stderr=b"",
        )
        with mock.patch.object(bundle.subprocess, "run", return_value=completed) as run, contextlib.redirect_stdout(
            io.StringIO()
        ):
            bundle.push_bundle(
                PAYLOAD,
                ssh="ssh",
                user="ops",
                host="203.0.113.10",
                project_dir="~/solo-vps",
                identity_file=None,
            )

        argv = run.call_args.args[0]
        self.assertEqual(argv[:4], ["ssh", "-T", "-o", "BatchMode=yes"])
        self.assertEqual(argv[4], "ops@203.0.113.10")
        self.assertEqual(
            argv[5],
            "cd $HOME/solo-vps && sudo -n python3 scripts/install_backup_credentials.py apply",
        )
        stdin = run.call_args.kwargs["input"]
        self.assertIn(b"example-access-id", stdin)
        self.assertNotIn(b"AGE-SECRET-KEY-", stdin)
        self.assertEqual(run.call_args.kwargs["timeout"], 45)

    def test_push_rejects_shell_like_remote_inputs_before_ssh(self) -> None:
        for user, host, project in (
            ("ops;id", "203.0.113.10", "~/solo-vps"),
            ("ops", "-oProxyCommand=x", "~/solo-vps"),
            ("ops", "203.0.113.10", "~/solo-vps;id"),
        ):
            with self.subTest(user=user, host=host, project=project):
                with mock.patch.object(bundle.subprocess, "run") as run:
                    with self.assertRaises(bundle.BundleError):
                        bundle.push_bundle(
                            PAYLOAD,
                            ssh="ssh",
                            user=user,
                            host=host,
                            project_dir=project,
                            identity_file=None,
                        )
                    run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
