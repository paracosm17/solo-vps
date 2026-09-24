#!/usr/bin/env python3
"""Install or verify the root-only M14 backup credential file on the VPS."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import sys
import tempfile

try:
    from scripts.backup_credentials_common import (
        BackupCredentialError,
        MAX_JSON_BYTES,
        canonical_json_bytes,
        parse_json_bytes,
    )
except ModuleNotFoundError:  # direct execution from scripts/ on the VPS
    from backup_credentials_common import (
        BackupCredentialError,
        MAX_JSON_BYTES,
        canonical_json_bytes,
        parse_json_bytes,
    )

DEFAULT_DIRECTORY = Path("/etc/solo-vps/backup")
DEFAULT_PATH = DEFAULT_DIRECTORY / "credentials.json"


class InstallError(RuntimeError):
    pass


def _absolute_unresolved(path: Path) -> Path:
    """Return an absolute path without following a final/intermediate symlink."""
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _require_root() -> None:
    if os.geteuid() != 0:
        raise InstallError("run this helper as root (the public workflow uses sudo -n)")


def _lstat_regular(path: Path) -> os.stat_result | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise InstallError(f"refusing non-regular credential path: {path}")
    return metadata


def _prepare_directory(directory: Path, *, owner_uid: int = 0, owner_gid: int = 0) -> None:
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        directory.mkdir(parents=True, mode=0o700)
        metadata = directory.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise InstallError(f"refusing non-directory credential root: {directory}")
    os.chown(directory, owner_uid, owner_gid)
    os.chmod(directory, 0o700)


def install_payload(
    payload: dict[str, str],
    destination: Path = DEFAULT_PATH,
    *,
    owner_uid: int = 0,
    owner_gid: int = 0,
) -> bool:
    directory = destination.parent
    _prepare_directory(directory, owner_uid=owner_uid, owner_gid=owner_gid)
    existing = _lstat_regular(destination)
    desired = canonical_json_bytes(payload)

    if existing is not None:
        current = destination.read_bytes()
        try:
            current_validated = canonical_json_bytes(parse_json_bytes(current))
        except BackupCredentialError as exc:
            raise InstallError(f"existing credential file is invalid; refusing overwrite: {exc}") from exc
        if current_validated == desired:
            os.chown(destination, owner_uid, owner_gid)
            os.chmod(destination, 0o600)
            return False

    fd, temporary_name = tempfile.mkstemp(prefix=".credentials.", dir=directory)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(desired)
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(temporary, owner_uid, owner_gid)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        try:
            directory_fd = os.open(directory, os.O_DIRECTORY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()
    return True


def verify_file(
    destination: Path = DEFAULT_PATH,
    *,
    owner_uid: int = 0,
    owner_gid: int = 0,
) -> dict[str, str]:
    directory = destination.parent
    try:
        directory_meta = directory.lstat()
    except FileNotFoundError as exc:
        raise InstallError(f"backup credential directory is missing: {directory}") from exc
    if stat.S_ISLNK(directory_meta.st_mode) or not stat.S_ISDIR(directory_meta.st_mode):
        raise InstallError(f"backup credential root is not a real directory: {directory}")
    if directory_meta.st_uid != owner_uid or directory_meta.st_gid != owner_gid:
        raise InstallError("backup credential directory has unexpected ownership")
    if stat.S_IMODE(directory_meta.st_mode) != 0o700:
        raise InstallError("backup credential directory mode must be 0700")

    metadata = _lstat_regular(destination)
    if metadata is None:
        raise InstallError(f"backup credential file is missing: {destination}")
    if metadata.st_uid != owner_uid or metadata.st_gid != owner_gid:
        raise InstallError("backup credential file has unexpected ownership")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise InstallError("backup credential file mode must be 0600")
    try:
        payload = parse_json_bytes(destination.read_bytes())
    except BackupCredentialError as exc:
        raise InstallError(f"backup credential file schema is invalid: {exc}") from exc
    return payload


def _read_stdin() -> dict[str, str]:
    raw = sys.stdin.buffer.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise InstallError("backup credential stdin payload exceeds 32 KiB")
    try:
        return parse_json_bytes(raw)
    except BackupCredentialError as exc:
        raise InstallError(str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("apply", "verify"))
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args()

    try:
        _require_root()
        destination = _absolute_unresolved(args.path)
        if args.command == "apply":
            payload = _read_stdin()
            changed = install_payload(payload, destination)
            verify_file(destination)
            print("PASS backup runtime credentials installed")
            print(f"  path: {destination}")
            print("  owner: root:root")
            print("  mode: 0600")
            print(f"  changed: {'yes' if changed else 'no'}")
            print("  plaintext printed: no")
        else:
            payload = verify_file(destination)
            print("PASS backup runtime credentials")
            print(f"  path: {destination}")
            print("  owner: root:root")
            print("  mode: 0600")
            print(f"  schema keys: {len(payload)} present")
            print("  plaintext printed: no")
    except (InstallError, OSError) as exc:
        print(f"ERROR backup runtime credentials: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
