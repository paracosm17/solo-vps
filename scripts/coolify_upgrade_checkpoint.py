#!/usr/bin/env python3
"""Create a private local Coolify control-plane checkpoint before upgrade."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile


def checkpoint(data: Path, destination: Path, run=subprocess.run) -> Path:
    # Never overwrite an earlier checkpoint, including after a failed attempt.
    for name in ("source", "ssh", ".solo-vps-managed"):
        path = data / name
        if path.is_symlink() or not path.exists():
            raise ValueError(f"missing or unsafe checkpoint input: {name}")
    destination.mkdir(parents=True, mode=0o700, exist_ok=True)
    if destination.is_symlink():
        raise ValueError("checkpoint destination must not be a symlink")
    os.chmod(destination, 0o700)
    result = Path(tempfile.mkdtemp(prefix="coolify-", dir=destination))
    dump = result / "coolify-db.dump"
    with dump.open("xb") as stream:
        os.chmod(dump, 0o600)
        run(["/usr/bin/docker", "exec", "coolify-db", "sh", "-c",
             'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom'],
            stdout=stream, stderr=subprocess.PIPE, check=True)
    if dump.stat().st_size == 0:
        raise ValueError("empty Coolify database dump")
    # Validate the archive with the matching PostgreSQL tools already in the container.
    with dump.open("rb") as stream:
        run(["/usr/bin/docker", "exec", "-i", "coolify-db", "pg_restore", "--list"],
            stdin=stream, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    archive = result / "control-plane.tar.gz"
    with tarfile.open(archive, "w:gz", dereference=False) as stream:
        for name in ("source", "ssh", ".solo-vps-managed"):
            stream.add(data / name, arcname=name)
    os.chmod(archive, 0o600)
    checksums = {}
    for path in (dump, archive):
        with path.open("r+b") as stream:
            checksums[path.name] = hashlib.file_digest(stream, "sha256").hexdigest()
            os.fsync(stream.fileno())
    # The completion record is written last; an incomplete directory is not a checkpoint.
    manifest = result / "checkpoint.json"
    manifest.write_text(json.dumps({"schema": 1, "files": checksums,
        "scope": "Coolify database, source configuration and SSH keys; excludes application data"}, indent=2) + "\n")
    os.chmod(manifest, 0o600)
    with manifest.open("r+b") as stream:
        os.fsync(stream.fileno())
    if os.name == "posix":
        for directory in (result, destination):
            descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("/data/coolify"))
    parser.add_argument("--destination", type=Path, default=Path("/var/lib/solo-vps/checkpoints"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.exit(2, "ERROR: checkpoint requires root\n")
    try:
        result = checkpoint(args.data, args.destination)
    except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError):
        # Do not print pg_dump stderr, which can contain installation details.
        parser.exit(2, "ERROR: local checkpoint failed; upgrade must not continue\n")
    print(json.dumps({"checkpoint": str(result)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
