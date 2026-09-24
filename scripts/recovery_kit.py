#!/usr/bin/env python3
"""Build and verify a portable Solo VPS lost-server recovery kit.

The kit intentionally contains only non-secret configuration, encrypted SOPS
ciphertexts, public SOPS metadata, and small ownership metadata. Private SSH/age
keys and plaintext runtime credentials are never accepted into the archive.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile
import tempfile
from typing import Iterable


class RecoveryKitError(RuntimeError):
    pass


KIT_VERSION = 1
PRIVATE_MARKERS = (
    b"PRIVATE KEY",
    b"AGE-SECRET-KEY-",
    b"AWS_SECRET_ACCESS_KEY=",
    b"RESTIC_PASSWORD=",
)
ALLOWED_EXACT = {
    "config/config.yml",
    "sops/.sops.yaml",
    "sops/production.txt",
    "secrets/backup.enc.yaml",
    "secrets/observability.enc.yaml",
    "manifest.json",
}
ALLOWED_PREFIXES = ("state/database-backups/",)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_regular(path: Path, *, name: str, required: bool = True) -> bytes | None:
    try:
        meta = path.lstat()
    except FileNotFoundError:
        if required:
            raise RecoveryKitError(f"required recovery input is missing: {name}")
        return None
    if stat.S_ISLNK(meta.st_mode) or not stat.S_ISREG(meta.st_mode):
        raise RecoveryKitError(f"recovery input must be a regular non-symlink file: {name}")
    data = path.read_bytes()
    for marker in PRIVATE_MARKERS:
        if marker in data:
            raise RecoveryKitError(f"refusing private/plaintext secret material in recovery input: {name}")
    return data


def _safe_member_name(name: str) -> str:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise RecoveryKitError(f"unsafe recovery-kit member path: {name}")
    normalized = str(pure)
    if normalized in ALLOWED_EXACT or any(normalized.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        return normalized
    raise RecoveryKitError(f"unexpected recovery-kit member: {name}")


def _database_state_files(data_dir: Path) -> Iterable[tuple[str, bytes]]:
    root = data_dir / "state/database-backups"
    if not root.exists():
        return []
    meta = root.lstat()
    if stat.S_ISLNK(meta.st_mode) or not stat.S_ISDIR(meta.st_mode):
        raise RecoveryKitError("database backup state directory must be a real directory")
    rows: list[tuple[str, bytes]] = []
    for path in sorted(root.glob("*.json")):
        data = _require_regular(path, name=str(path.relative_to(data_dir)))
        assert data is not None
        rows.append((f"state/database-backups/{path.name}", data))
    return rows


def collect_files(data_dir: Path) -> dict[str, bytes]:
    data_dir = data_dir.expanduser().resolve()
    files: dict[str, bytes] = {}
    required = {
        "config/config.yml": data_dir / "config/config.yml",
    }
    optional = {
        "sops/.sops.yaml": data_dir / "sops/.sops.yaml",
        "sops/production.txt": data_dir / "sops/production.txt",
        "secrets/backup.enc.yaml": data_dir / "secrets/backup.enc.yaml",
        "secrets/observability.enc.yaml": data_dir / "secrets/observability.enc.yaml",
    }
    for name, path in required.items():
        data = _require_regular(path, name=name)
        assert data is not None
        files[name] = data
    for name, path in optional.items():
        data = _require_regular(path, name=name, required=False)
        if data is not None:
            files[name] = data
    for name, data in _database_state_files(data_dir):
        files[name] = data
    return files


def build_manifest(files: dict[str, bytes], *, source_revision: str) -> dict[str, object]:
    source_revision = source_revision.strip()
    if not source_revision or any(c in source_revision for c in "\r\n\x00"):
        raise RecoveryKitError("source revision must be a non-empty single-line value")
    return {
        "version": KIT_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": source_revision,
        "files": {name: _sha256(data) for name, data in sorted(files.items())},
        "excluded_private_inputs": [
            "workstation age private identity",
            "workstation SSH private key",
            "provider account/recovery credentials",
        ],
        "required_external_recovery_inputs": [
            "Solo VPS source release matching source_revision",
            "workstation age private identity from a separate personal backup",
            "managed off-site restic repository and its SOPS-encrypted credentials",
            "Coolify instance database backup stored outside the lost VPS",
            "application PostgreSQL logical backup archives stored outside the lost VPS",
            "Git repositories/GHCR immutable artifacts for application redeploy",
            "DNS/provider access required to repoint the replacement VPS",
        ],
        "off_vps_copy_verified": False,
    }


def _write_tar_member(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o600
    info.mtime = 0
    with tempfile.SpooledTemporaryFile() as handle:
        handle.write(data)
        handle.seek(0)
        archive.addfile(info, handle)


def export_kit(data_dir: Path, output: Path, *, source_revision: str) -> dict[str, object]:
    files = collect_files(data_dir)
    manifest = build_manifest(files, source_revision=source_revision)
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise RecoveryKitError(f"refusing to overwrite existing recovery kit: {output}")
    fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        os.chmod(temp, 0o600)
        with tarfile.open(temp, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            for name, data in sorted(files.items()):
                _write_tar_member(archive, name, data)
            _write_tar_member(archive, "manifest.json", manifest_bytes)
        with temp.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temp, output)
        os.chmod(output, 0o600)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
    verify_kit(output)
    return manifest


def verify_kit(path: Path) -> dict[str, object]:
    path = path.expanduser().resolve()
    meta = path.lstat()
    if stat.S_ISLNK(meta.st_mode) or not stat.S_ISREG(meta.st_mode):
        raise RecoveryKitError("recovery kit must be a regular non-symlink file")
    if stat.S_IMODE(meta.st_mode) & 0o077:
        raise RecoveryKitError("recovery kit must not be group/world accessible")
    contents: dict[str, bytes] = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            name = _safe_member_name(member.name)
            if not member.isfile() or member.issym() or member.islnk():
                raise RecoveryKitError(f"recovery-kit member must be a regular file: {name}")
            if name in contents:
                raise RecoveryKitError(f"duplicate recovery-kit member: {name}")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise RecoveryKitError(f"could not read recovery-kit member: {name}")
            data = extracted.read()
            for marker in PRIVATE_MARKERS:
                if marker in data:
                    raise RecoveryKitError(f"recovery kit contains private/plaintext secret marker: {name}")
            contents[name] = data
    try:
        manifest = json.loads(contents.pop("manifest.json").decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecoveryKitError("recovery kit has no valid manifest.json") from exc
    if not isinstance(manifest, dict) or manifest.get("version") != KIT_VERSION:
        raise RecoveryKitError("unsupported recovery-kit manifest version")
    hashes = manifest.get("files")
    if not isinstance(hashes, dict) or set(hashes) != set(contents):
        raise RecoveryKitError("recovery-kit manifest file list does not match archive contents")
    if "config/config.yml" not in contents:
        raise RecoveryKitError("recovery kit is missing config/config.yml")
    for name, data in contents.items():
        if hashes.get(name) != _sha256(data):
            raise RecoveryKitError(f"recovery-kit checksum mismatch: {name}")
    if manifest.get("off_vps_copy_verified") is not False:
        raise RecoveryKitError("source-generated recovery kit must not claim off-VPS copy evidence")
    return manifest




def extract_kit(path: Path, data_dir: Path) -> dict[str, object]:
    manifest = verify_kit(path)
    path = path.expanduser().resolve()
    data_dir = data_dir.expanduser().resolve()
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    data_meta = data_dir.lstat()
    if stat.S_ISLNK(data_meta.st_mode) or not stat.S_ISDIR(data_meta.st_mode):
        raise RecoveryKitError("recovery-kit destination must be a real directory")
    if stat.S_IMODE(data_meta.st_mode) & 0o077:
        raise RecoveryKitError("recovery-kit destination must not be group/world accessible")
    with tarfile.open(path, "r:gz") as archive:
        members = {member.name: member for member in archive.getmembers()}
        for name in sorted(manifest["files"]):
            safe_name = _safe_member_name(name)
            member = members.get(safe_name)
            if member is None or not member.isfile():
                raise RecoveryKitError(f"verified recovery-kit member disappeared: {safe_name}")
            destination = data_dir.joinpath(*PurePosixPath(safe_name).parts)
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                raise RecoveryKitError(f"refusing to overwrite existing recovery input: {safe_name}")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise RecoveryKitError(f"could not read recovery-kit member: {safe_name}")
            payload = extracted.read()
            if _sha256(payload) != manifest["files"][safe_name]:
                raise RecoveryKitError(f"recovery-kit checksum changed during extraction: {safe_name}")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            fd = os.open(destination, flags, 0o600)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                try:
                    destination.unlink()
                except FileNotFoundError:
                    pass
                raise
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("export", "verify", "extract"))
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".local/share/solo-vps")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", default="PRE-ALPHA-unversioned")
    args = parser.parse_args()
    try:
        if args.operation == "export":
            manifest = export_kit(args.data_dir, args.output, source_revision=args.source_revision)
            print("PASS Solo VPS recovery kit export")
            print(f"  files: {len(manifest['files'])}")
            print("  private_keys_included: false")
            print("  plaintext_runtime_credentials_included: false")
            print("  off_vps_copy_verified: false")
        else:
            manifest = verify_kit(args.output)
            print("PASS Solo VPS recovery kit verification")
            print(f"  files: {len(manifest['files'])}")
            print("  checksums: pass")
            print("  private_keys_included: false")
        return 0
    except (OSError, tarfile.TarError, RecoveryKitError) as exc:
        print(f"ERROR recovery kit: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
