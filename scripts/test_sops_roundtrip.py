#!/usr/bin/env python3
"""Exercise disposable age identity + SOPS encrypt/decrypt with placeholder data only."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import yaml

from secrets_toolchain import (
    DEFAULT_MANIFEST,
    ToolchainError,
    binary_paths,
    check_installation,
    controller_platform,
    default_cache_root,
    install_dir,
    load_manifest,
)
from sops_policy import render_sops_config, validate_age_recipient

PLACEHOLDER_MARKER = "SOLO_VPS_DISPOSABLE_ROUNDTRIP_VALUE"


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ToolchainError(f"roundtrip command failed to start: {Path(command[0]).name}: {exc}") from exc


def _safe_env() -> dict[str, str]:
    env = dict(os.environ)
    for name in (
        "SOPS_AGE_KEY",
        "SOPS_AGE_KEY_FILE",
        "SOPS_AGE_SSH_PRIVATE_KEY_FILE",
        "SOPS_KMS_ARN",
        "SOPS_PGP_FP",
    ):
        env.pop(name, None)
    env["LC_ALL"] = "C"
    return env


def run_roundtrip(manifest_path: Path, cache_root: Path) -> None:
    manifest_path = manifest_path.expanduser().resolve()
    manifest = load_manifest(manifest_path)
    platform_id = controller_platform()
    root = install_dir(cache_root.expanduser().resolve(), manifest, platform_id)
    paths = check_installation(root, manifest_path, manifest, platform_id)

    temp_root_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="solo-vps-sops-roundtrip-") as temporary:
        temp_root = Path(temporary)
        temp_root_path = temp_root
        identity_path = temp_root / "age-identity.txt"
        secrets_dir = temp_root / "secrets"
        secrets_dir.mkdir(mode=0o700)
        secret_path = secrets_dir / "roundtrip.enc.yaml"

        env = _safe_env()
        keygen = _run(
            [str(paths["age-keygen"]), "-o", str(identity_path)], cwd=temp_root, env=env
        )
        if keygen.returncode != 0:
            raise ToolchainError("age-keygen failed during disposable roundtrip")
        identity_path.chmod(0o600)
        if identity_path.stat().st_mode & 0o077:
            raise ToolchainError("disposable age identity permissions are broader than 0600")

        recipient_result = _run(
            [str(paths["age-keygen"]), "-y", str(identity_path)], cwd=temp_root, env=env
        )
        if recipient_result.returncode != 0:
            raise ToolchainError("cannot derive disposable age public recipient")
        recipient = validate_age_recipient(recipient_result.stdout.strip())

        (temp_root / ".sops.yaml").write_text(render_sops_config(recipient), encoding="utf-8")
        plaintext = {
            "roundtrip": {
                "purpose": "disposable-local-test",
                "value": PLACEHOLDER_MARKER,
            }
        }
        secret_path.write_text(yaml.safe_dump(plaintext, sort_keys=True), encoding="utf-8")

        encrypt = _run(
            [
                str(paths["sops"]),
                "--config",
                str(temp_root / ".sops.yaml"),
                "--encrypt",
                "--in-place",
                str(secret_path),
            ],
            cwd=temp_root,
            env=env,
        )
        if encrypt.returncode != 0:
            raise ToolchainError("SOPS encryption failed during disposable roundtrip")

        encrypted_text = secret_path.read_text(encoding="utf-8")
        if PLACEHOLDER_MARKER in encrypted_text:
            raise ToolchainError("SOPS ciphertext still contains the placeholder secret in plaintext")
        encrypted = yaml.safe_load(encrypted_text)
        sops_metadata = encrypted.get("sops") if isinstance(encrypted, dict) else None
        if not isinstance(sops_metadata, dict) or not sops_metadata.get("mac"):
            raise ToolchainError("SOPS ciphertext is missing metadata/MAC")
        age_entries = sops_metadata.get("age")
        if not isinstance(age_entries, list) or not any(
            isinstance(entry, dict) and entry.get("recipient") == recipient for entry in age_entries
        ):
            raise ToolchainError("SOPS ciphertext is not wrapped for the disposable test recipient")

        decrypt_env = dict(env)
        decrypt_env["SOPS_AGE_KEY_FILE"] = str(identity_path)
        decrypt = _run(
            [str(paths["sops"]), "--decrypt", str(secret_path)], cwd=temp_root, env=decrypt_env
        )
        if decrypt.returncode != 0:
            raise ToolchainError("SOPS decryption failed during disposable roundtrip")
        recovered = yaml.safe_load(decrypt.stdout)
        if recovered != plaintext:
            raise ToolchainError("SOPS roundtrip output does not match the original placeholder data")

        # Do not print the recipient, identity, ciphertext, or placeholder value.
        shutil.rmtree(secrets_dir)
        identity_path.unlink()
        if identity_path.exists():
            raise ToolchainError("disposable age identity was not removed before test exit")

    if temp_root_path is not None and temp_root_path.exists():
        raise ToolchainError("temporary SOPS roundtrip directory was not removed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cache-dir", type=Path, default=None)
    args = parser.parse_args()
    try:
        run_roundtrip(args.manifest, args.cache_dir or default_cache_root())
    except ToolchainError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print("PASS disposable SOPS + age encrypt/decrypt roundtrip; private test identity removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
