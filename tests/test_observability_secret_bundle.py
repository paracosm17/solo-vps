from __future__ import annotations

import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import observability_secret_bundle as bundle

PAYLOAD = {
    "LOKI_URL": "https://logs.example.net/loki/api/v1/push",
    "LOKI_USERNAME": "123456",
    "GRAFANA_CLOUD_API_KEY": "synthetic-token-value",
}


class ObservabilitySecretBundleTests(unittest.TestCase):
    def test_init_writes_external_ciphertext_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "checkout"
            root.mkdir()
            policy = base / "policy.yaml"
            policy.write_text("creation_rules: []\n", encoding="utf-8")
            output = base / "state" / "secrets" / "observability.enc.yaml"
            encrypted = b"sops:\n  mac: ENC[synthetic]\n"
            with mock.patch.object(bundle, "_new_payload", return_value=PAYLOAD), mock.patch.object(
                bundle, "_run_sops", return_value=encrypted
            ), contextlib.redirect_stdout(io.StringIO()):
                bundle.init_bundle(root, policy, output, base / "age-key.txt", Path("/fake/sops"))
            self.assertEqual(output.read_bytes(), encrypted)
            self.assertFalse((root / "observability.enc.yaml").exists())

    def test_init_refuses_ciphertext_inside_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "checkout"
            root.mkdir()
            policy = Path(tmp) / "policy.yaml"
            policy.write_text("creation_rules: []\n", encoding="utf-8")
            output = root / "secrets" / "observability.enc.yaml"
            with mock.patch.object(bundle, "_new_payload", return_value=PAYLOAD), mock.patch.object(
                bundle, "_run_sops", return_value=b"sops:\n  mac: ENC[x]\n"
            ):
                with self.assertRaises(bundle.BundleError):
                    bundle.init_bundle(root, policy, output, Path(tmp) / "age-key.txt", Path("/fake/sops"))


    def test_init_reuses_existing_decryptable_ciphertext_without_prompting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "checkout"
            root.mkdir()
            policy = base / "policy.yaml"
            policy.write_text("creation_rules: []\n", encoding="utf-8")
            output = base / "state" / "secrets" / "observability.enc.yaml"
            output.parent.mkdir(parents=True)
            output.write_text("sops: {}\n", encoding="utf-8")
            key = base / "age-key.txt"
            key.write_text("synthetic\n", encoding="utf-8")
            stdout = io.StringIO()
            with mock.patch.object(bundle, "decrypt_bundle", return_value=PAYLOAD) as decrypt, mock.patch.object(
                bundle, "_new_payload"
            ) as prompt, contextlib.redirect_stdout(stdout):
                bundle.init_bundle(root, policy, output, key, Path("/fake/sops"))
            decrypt.assert_called_once_with(policy, output, key, Path("/fake/sops"))
            prompt.assert_not_called()
            self.assertIn("already exists; reusing it", stdout.getvalue())
            self.assertIn("existing ciphertext replaced: no", stdout.getvalue())

    def test_decrypt_rejects_symlink_key_before_sops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            policy = base / "policy.yaml"
            policy.write_text("creation_rules: []\n", encoding="utf-8")
            encrypted = base / "observability.enc.yaml"
            encrypted.write_text("sops: {}\n", encoding="utf-8")
            real_key = base / "real-key.txt"
            real_key.write_text("synthetic\n", encoding="utf-8")
            key = base / "age-key.txt"
            key.symlink_to(real_key)
            with mock.patch.object(bundle, "_run_sops") as run:
                with self.assertRaises(bundle.BundleError):
                    bundle.decrypt_bundle(policy, encrypted, key, Path("/fake/sops"))
                run.assert_not_called()

    def test_sops_failure_suppresses_stderr(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["sops"], returncode=7, stdout=b"", stderr=b"sensitive-detail\n"
        )
        with mock.patch.object(bundle.subprocess, "run", return_value=completed):
            with self.assertRaises(bundle.BundleError) as raised:
                bundle._run_sops(Path("/fake/sops"), ["decrypt"])
        self.assertIn("suppressed", str(raised.exception))
        self.assertNotIn("sensitive-detail", str(raised.exception))

    def test_push_uses_ssh_stdin_and_managed_installer(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["ssh"], returncode=0, stdout=b"PASS observability runtime credentials installed\n", stderr=b""
        )
        with mock.patch.object(bundle.subprocess, "run", return_value=completed) as run, contextlib.redirect_stdout(io.StringIO()):
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
            "cd $HOME/solo-vps && sudo -n python3 scripts/install_observability_credentials.py apply",
        )
        stdin = run.call_args.kwargs["input"]
        self.assertIn(b"synthetic-token-value", stdin)
        self.assertNotIn(b"AGE-SECRET-KEY-", stdin)


if __name__ == "__main__":
    unittest.main()
