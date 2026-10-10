#!/usr/bin/env python3
"""Private root collector for the workstation Coolify backup exporter."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

if __package__:
    from .coolify_backup_common import verify_members
    from .coolify_upgrade_checkpoint import checkpoint
else:
    from coolify_backup_common import verify_members
    from coolify_upgrade_checkpoint import checkpoint


def add_tree(tar: tarfile.TarFile, path: Path, name: str, hashes: dict) -> None:
    if path.is_symlink():
        raise ValueError("backup inputs must not be symlinks")
    if path.is_dir():
        for child in sorted(path.iterdir()):
            if "access.log" not in child.name:
                add_tree(tar, child, name + "/" + child.name, hashes)
    elif path.is_file():
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        tar.add(path, arcname=name, recursive=False)
        hashes[name] = digest
    else:
        raise ValueError("missing or special backup input")


def collect(data: Path, operator: Path, source: Path, stage: Path) -> Path:
    if any((data / name).exists() for name in (".solo-vps-upgrading", ".solo-vps-installing")):
        raise ValueError("finish the pending upgrade before backup")
    cp = checkpoint(data, stage / "checkpoints")
    inspect = subprocess.run(
        ["/usr/bin/docker", "inspect", "coolify", "coolify-db", "coolify-proxy", "coolify-sentinel"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    containers = json.loads(inspect)
    if not all(c["State"].get("Health", {}).get("Status") == "healthy" for c in containers):
        raise ValueError("platform must be healthy before backup")
    snapshot = stage / "runtime.json"
    snapshot.write_bytes(inspect)
    revision = subprocess.run(["git", "-c", "safe.directory=" + str(source), "-C", str(source),
                               "rev-parse", "HEAD"], check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE).stdout.decode().strip()
    hashes: dict[str, str] = {}
    archive = stage / "backup.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        add_tree(tar, cp, "control-plane", hashes)
        add_tree(tar, data / "proxy", "proxy", hashes)
        add_tree(tar, operator / "config", "operator-config", hashes)
        add_tree(tar, snapshot, "runtime.json", hashes)
        manifest = stage / "manifest.json"
        manifest.write_text(json.dumps({
            "schema": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_revision": revision, "files": hashes,
            "scope": "Coolify database/source/SSH keys, proxy certificates/config, operator config and platform metadata",
            "excludes": ["application databases and volumes", "Docker images", "access logs",
                         "workstation SSH/age identities", "historical checkpoints"],
            "restore": "Manual control-plane recovery; source/image downgrade does not undo database migrations",
        }, indent=2) + "\n")
        tar.add(manifest, arcname="manifest.json", recursive=False)
    with archive.open("rb") as stream:
        verify_members(stream)
    return archive


@contextmanager
def capture_lock(root: Path):
    if root.is_symlink():
        raise ValueError("unsafe staging root")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    fd = os.open(root / ".capture.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-data", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if os.geteuid() != 0:
            raise ValueError("root required")
        root = Path("/var/lib/solo-vps/exports")
        with capture_lock(root), tempfile.TemporaryDirectory(prefix="coolify-", dir=root) as tmp:
            archive = collect(Path("/data/coolify"), args.operator_data, args.source, Path(tmp))
            digest = hashlib.sha256()
            with archive.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
                    sys.stdout.buffer.write(block)
            sys.stdout.buffer.flush()
            print("SOLO_BACKUP_SHA256=" + digest.hexdigest(), file=sys.stderr)
    except BlockingIOError:
        print("ERROR: another Coolify backup capture is running", file=sys.stderr)
        return 2
    except (OSError, ValueError, EOFError, subprocess.SubprocessError, tarfile.TarError):
        print("ERROR: private Coolify backup collection failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
