from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import secrets_toolchain  # noqa: E402
from secrets_toolchain import (  # noqa: E402
    DEFAULT_MANIFEST,
    ToolchainError,
    controller_platform,
    extract_age_archive,
    install_toolchain,
    load_manifest,
    check_installation,
    verify_sha256,
)


class SecretsToolchainTests(unittest.TestCase):
    def test_project_manifest_is_valid_and_exactly_pinned(self) -> None:
        manifest = load_manifest(DEFAULT_MANIFEST)
        self.assertEqual(manifest["tools"]["sops"]["version"], "3.13.3")
        self.assertEqual(manifest["tools"]["age"]["version"], "1.3.1")
        self.assertEqual(manifest["controller_platforms"], ["linux-amd64", "linux-arm64"])
        for tool in manifest["tools"].values():
            for artifact in tool["artifacts"].values():
                self.assertEqual(len(artifact["sha256"]), 64)
                self.assertTrue(artifact["url"].startswith("https://github.com/"))

    def test_controller_platform_aliases_and_rejections(self) -> None:
        self.assertEqual(controller_platform("Linux", "x86_64"), "linux-amd64")
        self.assertEqual(controller_platform("linux", "amd64"), "linux-amd64")
        self.assertEqual(controller_platform("Linux", "aarch64"), "linux-arm64")
        self.assertEqual(controller_platform("linux", "arm64"), "linux-arm64")
        with self.assertRaisesRegex(ToolchainError, "Linux only"):
            controller_platform("Darwin", "arm64")
        with self.assertRaisesRegex(ToolchainError, "unsupported Linux controller architecture"):
            controller_platform("Linux", "riscv64")

    def test_checksum_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "artifact"
            path.write_bytes(b"not-the-reviewed-release")
            expected = hashlib.sha256(b"reviewed-release").hexdigest()
            with self.assertRaisesRegex(ToolchainError, "SHA-256 mismatch"):
                verify_sha256(path, expected)

    def test_age_archive_extracts_only_exact_regular_binaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "age.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                for name, payload in {
                    "age/age": b"age-binary",
                    "age/age-keygen": b"keygen-binary",
                    "../should-not-extract": b"unsafe-extra",
                    "age/LICENSE": b"license",
                }.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    info.mode = 0o755
                    archive.addfile(info, io.BytesIO(payload))

            bin_dir = root / "bin"
            extract_age_archive(
                archive_path,
                {"age": "age/age", "age-keygen": "age/age-keygen"},
                bin_dir,
            )
            self.assertEqual((bin_dir / "age").read_bytes(), b"age-binary")
            self.assertEqual((bin_dir / "age-keygen").read_bytes(), b"keygen-binary")
            self.assertFalse((root / "should-not-extract").exists())
            self.assertFalse((bin_dir / "LICENSE").exists())

    def test_age_archive_rejects_duplicate_expected_member(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "age.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                for name, payload in [
                    ("age/age", b"first"),
                    ("age/age", b"second"),
                    ("age/age-keygen", b"keygen"),
                ]:
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))

            with self.assertRaisesRegex(ToolchainError, "duplicate expected members"):
                extract_age_archive(
                    archive_path,
                    {"age": "age/age", "age-keygen": "age/age-keygen"},
                    root / "bin",
                )

    def test_age_archive_rejects_symlink_in_place_of_binary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "age.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                symlink = tarfile.TarInfo("age/age")
                symlink.type = tarfile.SYMTYPE
                symlink.linkname = "/bin/sh"
                archive.addfile(symlink)
                payload = b"keygen-binary"
                info = tarfile.TarInfo("age/age-keygen")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))

            with self.assertRaisesRegex(ToolchainError, "not a regular file"):
                extract_age_archive(
                    archive_path,
                    {"age": "age/age", "age-keygen": "age/age-keygen"},
                    root / "bin",
                )


    def test_offline_install_flow_uses_verified_artifacts_and_detects_binary_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sops_bytes = b"fake-reviewed-sops-binary"
            age_archive = root / "fixture-age.tar.gz"
            with tarfile.open(age_archive, "w:gz") as archive:
                for name, payload in {
                    "age/age": b"fake-reviewed-age-binary",
                    "age/age-keygen": b"fake-reviewed-age-keygen-binary",
                }.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    info.mode = 0o755
                    archive.addfile(info, io.BytesIO(payload))

            manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
            manifest["tools"]["sops"]["artifacts"]["linux-amd64"]["sha256"] = hashlib.sha256(sops_bytes).hexdigest()
            manifest["tools"]["age"]["artifacts"]["linux-amd64"]["sha256"] = hashlib.sha256(age_archive.read_bytes()).hexdigest()
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            loaded = load_manifest(manifest_path)

            def fake_download(url: str, destination: Path) -> None:
                if "getsops/sops" in url:
                    destination.write_bytes(sops_bytes)
                else:
                    destination.write_bytes(age_archive.read_bytes())

            cache = root / "cache"
            with patch.object(secrets_toolchain, "_download", side_effect=fake_download):
                installed = install_toolchain(manifest_path, loaded, cache, "linux-amd64")
                second = install_toolchain(manifest_path, loaded, cache, "linux-amd64")
            self.assertEqual(installed, second)
            self.assertEqual((installed / "bin" / "sops").read_bytes(), sops_bytes)
            self.assertEqual((installed / "bin" / "age").read_bytes(), b"fake-reviewed-age-binary")
            self.assertEqual((installed / "bin" / "age-keygen").read_bytes(), b"fake-reviewed-age-keygen-binary")

            (installed / "bin" / "age").write_bytes(b"tampered")
            (installed / "bin" / "age").chmod(0o755)
            with self.assertRaisesRegex(ToolchainError, "no longer matches"):
                check_installation(installed, manifest_path, loaded, "linux-amd64")

    def test_offline_artifact_directory_install_never_calls_downloader(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_dir = root / "artifacts"
            artifact_dir.mkdir()
            sops_bytes = b"offline-reviewed-sops-binary"
            age_archive = artifact_dir / "age-v1.3.1-linux-amd64.tar.gz"
            with tarfile.open(age_archive, "w:gz") as archive:
                for name, payload in {
                    "age/age": b"offline-reviewed-age-binary",
                    "age/age-keygen": b"offline-reviewed-age-keygen-binary",
                }.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    info.mode = 0o755
                    archive.addfile(info, io.BytesIO(payload))
            (artifact_dir / "sops-v3.13.3.linux.amd64").write_bytes(sops_bytes)

            manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
            manifest["tools"]["sops"]["artifacts"]["linux-amd64"]["sha256"] = hashlib.sha256(sops_bytes).hexdigest()
            manifest["tools"]["age"]["artifacts"]["linux-amd64"]["sha256"] = hashlib.sha256(age_archive.read_bytes()).hexdigest()
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            loaded = load_manifest(manifest_path)

            with patch.object(secrets_toolchain, "_download", side_effect=AssertionError("network downloader must not run")):
                installed = install_toolchain(
                    manifest_path, loaded, root / "cache", "linux-amd64", artifact_dir=artifact_dir
                )

            self.assertEqual((installed / "bin" / "sops").read_bytes(), sops_bytes)
            self.assertEqual((installed / "bin" / "age").read_bytes(), b"offline-reviewed-age-binary")
            self.assertEqual(
                (installed / "bin" / "age-keygen").read_bytes(),
                b"offline-reviewed-age-keygen-binary",
            )

    def test_offline_artifact_directory_rejects_symlink_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_dir = root / "artifacts"
            artifact_dir.mkdir()
            real_sops = root / "real-sops"
            real_sops.write_bytes(b"offline-reviewed-sops-binary")
            (artifact_dir / "sops-v3.13.3.linux.amd64").symlink_to(real_sops)

            age_archive = artifact_dir / "age-v1.3.1-linux-amd64.tar.gz"
            with tarfile.open(age_archive, "w:gz") as archive:
                for name, payload in {
                    "age/age": b"age",
                    "age/age-keygen": b"age-keygen",
                }.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))

            manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
            manifest["tools"]["sops"]["artifacts"]["linux-amd64"]["sha256"] = hashlib.sha256(real_sops.read_bytes()).hexdigest()
            manifest["tools"]["age"]["artifacts"]["linux-amd64"]["sha256"] = hashlib.sha256(age_archive.read_bytes()).hexdigest()
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            loaded = load_manifest(manifest_path)

            with self.assertRaisesRegex(ToolchainError, "regular non-symlink file"):
                install_toolchain(
                    manifest_path, loaded, root / "cache", "linux-amd64", artifact_dir=artifact_dir
                )


    def test_makefile_exposes_one_command_online_crypto_proof(self) -> None:
        makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn(
            "secrets-crypto-proof: validate-secrets-toolchain test-secrets-toolchain",
            makefile,
        )
        block = makefile.split(
            "secrets-crypto-proof: validate-secrets-toolchain test-secrets-toolchain", 1
        )[1].split("secrets-crypto-proof-offline:", 1)[0]
        self.assertIn("secrets-tools", block)
        self.assertIn("check-secrets-tools", block)
        self.assertIn("test-sops-roundtrip", block)
        self.assertNotIn("init-sops-policy", block)

    def test_makefile_offline_crypto_proof_reuses_same_verified_roundtrip(self) -> None:
        makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
        block = makefile.split(
            "secrets-crypto-proof-offline: validate-secrets-toolchain test-secrets-toolchain", 1
        )[1].split("validate-backup-tooling:", 1)[0]
        self.assertIn("SECRETS_ARTIFACT_DIR", block)
        self.assertIn("secrets-tools-offline", block)
        self.assertIn("check-secrets-tools", block)
        self.assertIn("test-sops-roundtrip", block)
        self.assertNotIn("init-sops-policy", block)

    def test_manifest_rejects_non_official_download_host(self) -> None:
        manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        manifest["tools"]["sops"]["artifacts"]["linux-amd64"]["url"] = (
            "https://example.invalid/sops-v3.13.3.linux.amd64"
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ToolchainError, "official GitHub HTTPS release URL"):
                load_manifest(path)


if __name__ == "__main__":
    unittest.main()
