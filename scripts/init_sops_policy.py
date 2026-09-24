#!/usr/bin/env python3
"""Initialize persistent public SOPS policy from an age recipient only."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

from sops_policy import LEGACY_SOPS_PATH_REGEX, render_sops_config, validate_age_recipient


def _write_public_file(path: Path, content: str, *, legacy_contents: tuple[str, ...] = ()) -> str:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    if path.exists():
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"refusing non-regular policy path {path}")
        current = path.read_text(encoding="utf-8")
        if current == content:
            try:
                path.chmod(0o600)
            except OSError:
                pass
            return "unchanged"
        if current not in legacy_contents:
            raise RuntimeError(
                f"refusing to overwrite existing {path}; use the explicit recipient-rotation workflow"
            )

        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                temporary.chmod(0o600)
            except OSError:
                pass
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return "migrated"

    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return "created"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create persistent public SOPS policy files from an age X25519 public recipient. "
            "This command never generates, reads, or stores a private age identity."
        )
    )
    parser.add_argument("--recipient", required=True, help="age X25519 public recipient (age1...)")
    parser.add_argument("--policy", required=True, type=Path, help="external SOPS policy destination")
    parser.add_argument("--recipient-file", required=True, type=Path, help="external public recipient destination")
    args = parser.parse_args()

    try:
        recipient = validate_age_recipient(args.recipient)
        policy_path = args.policy.expanduser().resolve()
        recipient_path = args.recipient_file.expanduser().resolve()
        if policy_path == recipient_path:
            raise RuntimeError("policy and recipient paths must be different")
        policy_status = _write_public_file(
            policy_path,
            render_sops_config(recipient),
            legacy_contents=(render_sops_config(recipient, path_regex=LEGACY_SOPS_PATH_REGEX),),
        )
        recipient_status = _write_public_file(recipient_path, f"{recipient}\n")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR SOPS policy initialization: {exc}", file=sys.stderr)
        return 2

    print(f"PASS local SOPS policy: {policy_path} {policy_status}")
    print(f"PASS local public age recipient: {recipient_path} {recipient_status}")
    print("PASS private age identity: not generated/read/copied")
    print("PASS source checkout mutated: no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
