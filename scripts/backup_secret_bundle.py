#!/usr/bin/env python3
"""Create, validate, and deliver the M14 SOPS-encrypted backup credential bundle."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import tempfile

try:
    from scripts.backup_credentials_common import BackupCredentialError, canonical_json_bytes, parse_json_bytes
    from scripts.secrets_toolchain import (
        ToolchainError,
        binary_paths,
        check_installation,
        controller_platform,
        default_cache_root,
        install_dir,
        load_manifest,
    )
except ModuleNotFoundError:  # direct execution from scripts/ on a Linux workstation
    from backup_credentials_common import BackupCredentialError, canonical_json_bytes, parse_json_bytes
    from secrets_toolchain import (
        ToolchainError,
        binary_paths,
        check_installation,
        controller_platform,
        default_cache_root,
        install_dir,
        load_manifest,
    )

DEFAULT_KEY_FILE = Path.home() / ".config" / "solo-vps" / "age-key.txt"
SOPS_FILENAME_OVERRIDE = "secrets/backup.enc.yaml"
_REMOTE_PATH_RE = re.compile(r"^[A-Za-z0-9_./~+-]+$")
_REMOTE_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


class BundleError(RuntimeError):
    pass


def _absolute_unresolved(path: Path) -> Path:
    """Return an absolute path without following symlinks so safety checks still see them."""
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _managed_sops(manifest_path: Path) -> Path:
    manifest = load_manifest(manifest_path)
    platform_id = controller_platform()
    target = install_dir(default_cache_root(), manifest, platform_id)
    check_installation(target, manifest_path, manifest, platform_id)
    return binary_paths(target)["sops"]


def _run_sops(
    sops: Path,
    args: list[str],
    *,
    stdin: bytes | None = None,
    key_file: Path | None = None,
) -> bytes:
    env = os.environ.copy()
    if key_file is not None:
        env["SOPS_AGE_KEY_FILE"] = str(key_file)
    try:
        result = subprocess.run(
            [str(sops), *args],
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=env,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BundleError(f"could not execute SOPS: {exc}") from exc
    if result.returncode != 0:
        raise BundleError(f"SOPS failed with exit code {result.returncode}; secret-bearing stderr was suppressed")
    return result.stdout


def _write_external_ciphertext(root: Path, output: Path, encrypted: bytes) -> None:
    root = root.resolve()
    output = _absolute_unresolved(output)
    if output.is_symlink():
        raise BundleError(f"refusing symlink backup ciphertext destination: {output}")
    if _inside(output, root):
        raise BundleError("backup ciphertext for an installation must stay outside the public source checkout")
    if output.exists():
        raise BundleError(f"refusing to overwrite existing backup ciphertext: {output}")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        output.parent.chmod(0o700)
    except OSError:
        pass
    fd, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encrypted)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def _new_payload() -> dict[str, str]:
    print("Enter the S3-compatible credentials. Values are not echoed back.")
    access_key = getpass.getpass("S3 access key ID: ").strip()
    secret_key = getpass.getpass("S3 secret access key: ")
    session_token = getpass.getpass("S3 session token (press Enter if not used): ")
    payload = {
        "AWS_ACCESS_KEY_ID": access_key,
        "AWS_SECRET_ACCESS_KEY": secret_key,
        "RESTIC_PASSWORD": secrets.token_urlsafe(32),
    }
    if session_token:
        payload["AWS_SESSION_TOKEN"] = session_token
    try:
        return json.loads(canonical_json_bytes(payload).decode("utf-8"))
    except BackupCredentialError as exc:
        raise BundleError(str(exc)) from exc


def init_bundle(
    root: Path, policy: Path, output: Path, sops: Path, *, key_file: Path = DEFAULT_KEY_FILE
) -> None:
    if not policy.is_file():
        raise BundleError(f"persistent SOPS policy is missing: {policy}; initialize it first")
    if output.exists():
        try:
            decrypt_bundle(policy, output, key_file, sops)
        except BundleError as exc:
            raise BundleError(
                "an encrypted backup bundle already exists but cannot be validated with the current age key; "
                "for an intentional clean rerun archive the old local secret state first"
            ) from exc
        print("PASS encrypted backup secret bundle already exists; reusing it")
        print("  existing ciphertext replaced: no")
        print("  to enter new storage credentials: rotate them explicitly or start fresh")
        return
    payload = _new_payload()
    plaintext = canonical_json_bytes(payload)
    encrypted = _run_sops(
        sops,
        [
            "--config",
            str(policy),
            "encrypt",
            "--filename-override",
            SOPS_FILENAME_OVERRIDE,
            "--input-type",
            "json",
            "--output-type",
            "yaml",
        ],
        stdin=plaintext,
    )
    if not encrypted.strip():
        raise BundleError("SOPS returned empty ciphertext")
    for value in payload.values():
        if value.encode("utf-8") in encrypted:
            raise BundleError("SOPS output unexpectedly contains a plaintext credential value")
    _write_external_ciphertext(root, output, encrypted)
    print("PASS encrypted backup secret bundle created")
    print(f"  ciphertext: {output.expanduser().resolve()}")
    print("  restic repository password: generated automatically")
    print("  plaintext file created: no")
    print("  source checkout mutated: no")


def decrypt_bundle(policy: Path, encrypted: Path, key_file: Path, sops: Path) -> dict[str, str]:
    if not policy.is_file():
        raise BundleError(f"persistent SOPS policy is missing: {policy}")
    if not encrypted.is_file() or encrypted.is_symlink():
        raise BundleError(f"encrypted backup secret bundle is missing or unsafe: {encrypted}")
    if not key_file.is_file() or key_file.is_symlink():
        raise BundleError(f"age private key is missing or unsafe: {key_file}")
    decrypted = _run_sops(
        sops,
        [
            "--config",
            str(policy),
            "decrypt",
            "--input-type",
            "yaml",
            "--output-type",
            "json",
            str(encrypted),
        ],
        key_file=key_file,
    )
    try:
        return parse_json_bytes(decrypted)
    except BackupCredentialError as exc:
        raise BundleError(f"decrypted backup bundle failed schema validation: {exc}") from exc


def _validate_remote(user: str, host: str, project_dir: str) -> None:
    if not _REMOTE_USER_RE.fullmatch(user):
        raise BundleError("VPS SSH user must be a simple Linux username")
    if not host or any(char.isspace() for char in host) or host.startswith("-"):
        raise BundleError("VPS host must be a non-empty SSH host/IP without whitespace")
    if not _REMOTE_PATH_RE.fullmatch(project_dir):
        raise BundleError("remote project path contains unsupported shell characters")


def push_bundle(
    payload: dict[str, str],
    *,
    ssh: str,
    user: str,
    host: str,
    project_dir: str,
    identity_file: Path | None,
) -> None:
    _validate_remote(user, host, project_dir)
    if project_dir == "~":
        remote_dir = "$HOME"
    elif project_dir.startswith("~/"):
        remote_dir = "$HOME/" + project_dir[2:]
    else:
        remote_dir = shlex.quote(project_dir)
    remote = f"cd {remote_dir} && sudo -n python3 scripts/install_backup_credentials.py apply"
    argv = [ssh, "-T", "-o", "BatchMode=yes"]
    if identity_file is not None:
        argv.extend(["-i", str(identity_file.expanduser())])
    argv.extend([f"{user}@{host}", remote])
    try:
        result = subprocess.run(
            argv,
            input=canonical_json_bytes(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BundleError(f"SSH credential delivery failed before completion: {exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise BundleError(
            "VPS credential installation failed"
            + (f": {stderr.splitlines()[-1]}" if stderr else f" with exit code {result.returncode}")
        )
    stdout = result.stdout.decode("utf-8", errors="replace").strip()
    if stdout:
        print(stdout)
    print("PASS workstation-to-VPS backup credential delivery")
    print("  transport: SSH stdin")
    print("  age private key copied to VPS: no")
    print("  plaintext stored in source checkout: no")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "check", "push"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, default=Path("tools/secrets-toolchain.json"))
    parser.add_argument("--sops", type=Path, default=None)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--encrypted", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--ssh", default="ssh")
    parser.add_argument("--vps-host")
    parser.add_argument("--vps-user")
    parser.add_argument("--remote-project", default="~/solo-vps")
    parser.add_argument("--identity-file", type=Path, default=None)
    args = parser.parse_args()

    try:
        sops = args.sops.expanduser().resolve() if args.sops else _managed_sops(args.manifest.resolve())
        policy = _absolute_unresolved(args.policy)
        encrypted = _absolute_unresolved(args.encrypted)
        key_file = _absolute_unresolved(args.key_file)
        if args.command == "init":
            init_bundle(args.root, policy, encrypted, sops, key_file=key_file)
        else:
            payload = decrypt_bundle(policy, encrypted, key_file, sops)
            if args.command == "check":
                print("PASS encrypted backup secret bundle decrypts and matches the expected schema")
                print(f"  ciphertext: {encrypted}")
                print(f"  keys present: {len(payload)}")
                print("  plaintext printed: no")
                print("  age private key copied to VPS: no")
            else:
                if not args.vps_host or not args.vps_user:
                    raise BundleError("push requires --vps-host and --vps-user")
                push_bundle(
                    payload,
                    ssh=args.ssh,
                    user=args.vps_user,
                    host=args.vps_host,
                    project_dir=args.remote_project,
                    identity_file=args.identity_file,
                )
    except (BundleError, BackupCredentialError, ToolchainError, OSError) as exc:
        print(f"ERROR backup secret bundle: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
