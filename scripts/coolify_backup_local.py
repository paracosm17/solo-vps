#!/usr/bin/env python3
"""Create an encrypted local VPS backup with a public age recipient only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import uuid

if __package__:
    from .coolify_backup_common import receive_encrypted
    from .secrets_toolchain import (DEFAULT_MANIFEST, ToolchainError, check_installation,
                                   controller_platform, default_cache_root, install_dir, load_manifest)
    from .sops_policy import validate_age_recipient
else:
    from coolify_backup_common import receive_encrypted
    from secrets_toolchain import (DEFAULT_MANIFEST, ToolchainError, check_installation,
                                   controller_platform, default_cache_root, install_dir, load_manifest)
    from sops_policy import validate_age_recipient

ROOT = Path(__file__).resolve().parents[1]


def public_recipient(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256:
        raise ValueError("missing or unsafe public recipient file")
    # Only one X25519 public recipient; never read/fall back to an age identity.
    return validate_age_recipient(path.read_text(encoding="utf-8").strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--recipient-file", type=Path, required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    try:
        if os.geteuid() == 0:
            raise ValueError("run as the existing administrator, without sudo make")
        data = args.data_dir.expanduser().absolute()
        recipient = public_recipient(args.recipient_file.expanduser())
        manifest = load_manifest(DEFAULT_MANIFEST)
        platform = controller_platform()
        tools = check_installation(install_dir(default_cache_root(), manifest, platform),
                                   DEFAULT_MANIFEST, manifest, platform)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = Path(args.output) if args.output else data / "backups" / ("coolify-" + stamp + "-" + uuid.uuid4().hex[:8] + ".tar.gz.age")
        command = ["sudo", "-n", sys.executable, str(ROOT / "scripts/coolify_backup_collect.py"),
                   "--operator-data", str(data), "--source", str(ROOT)]
        receive_encrypted(command, tools["age"], ["-r", recipient], output)
        with output.expanduser().open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
    except (OSError, ValueError, UnicodeError, ToolchainError, subprocess.SubprocessError):
        parser.exit(2, "ERROR: local Coolify backup failed; check public recipient, pinned tools, healthy platform and non-overlapping capture\n")
    print("PASS encrypted local Coolify control-plane backup created")
    print("  output: " + str(output.expanduser().absolute()))
    print("  encrypted SHA256: " + digest)
    print("  content validated before encryption; decryption must be verified off the VPS")
    print("  application databases/volumes: excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
