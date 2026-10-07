#!/usr/bin/env python3
"""Fill missing first-install secrets atomically; never rotate existing values."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile


SECRET_KEYS = (
    "APP_ID", "APP_KEY", "DB_PASSWORD", "REDIS_PASSWORD",
    "PUSHER_APP_ID", "PUSHER_APP_KEY", "PUSHER_APP_SECRET",
)


def generated_value(key: str) -> str:
    if key == "APP_ID":
        return secrets.token_hex(16)
    if key in ("APP_KEY", "DB_PASSWORD", "REDIS_PASSWORD"):
        value = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        return "base64:" + value if key == "APP_KEY" else value
    return secrets.token_hex(32)


def complete_environment(text: str, *, require_existing: bool = False) -> str:
    lines = text.splitlines()
    positions: dict[str, int] = {}
    missing: list[str] = []
    for index, line in enumerate(lines):
        key, separator, value = line.partition("=")
        if not separator or key not in SECRET_KEYS:
            continue
        if key in positions:
            raise ValueError(f"duplicate {key} in Coolify environment; review it before continuing")
        positions[key] = index
        if not value.strip():
            missing.append(key)
    missing.extend(key for key in SECRET_KEYS if key not in positions)
    if require_existing and missing:
        raise ValueError("configured installation has missing secrets; restore its environment instead of regenerating identities")
    if not missing:
        return text
    for key in missing:
        line = f"{key}={generated_value(key)}"
        if key in positions:
            lines[positions[key]] = line
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def complete_reverb_environment(text: str) -> str:
    """Migrate only the supported local backend, preserving every secret verbatim."""
    lines = text.splitlines()
    positions: dict[str, int] = {}
    values: dict[str, str] = {}
    for index, line in enumerate(lines):
        key, sep, value = line.partition("=")
        if not sep or key not in ("PUSHER_BACKEND_HOST", "PUSHER_BACKEND_PORT"):
            continue
        if key in positions:
            raise ValueError("duplicate realtime backend setting; review it before upgrading")
        positions[key] = index
        values[key] = value.strip().strip('\"\'')
    if values.get("PUSHER_BACKEND_HOST", "") not in ("", "coolify-realtime", "127.0.0.1"):
        raise ValueError("custom realtime backend host is outside the reviewed local Reverb upgrade; reconcile it before upgrading")
    if values.get("PUSHER_BACKEND_PORT", "") not in ("", "6001"):
        raise ValueError("custom realtime backend port is outside the reviewed 6001 port policy; reconcile it before upgrading")
    updates = {"PUSHER_BACKEND_HOST": "127.0.0.1", "PUSHER_BACKEND_PORT": "6001"}
    changed = False
    for key, value in updates.items():
        if values.get(key) == value:
            continue
        changed = True
        line = f"{key}={value}"
        if key in positions:
            lines[positions[key]] = line
        else:
            lines.append(line)
    return "\n".join(lines) + "\n" if changed else text


def initialize(path: Path, *, require_existing: bool = False, reverb: bool = False, check_only: bool = False) -> bool:
    previous = path.lstat()
    if not stat.S_ISREG(previous.st_mode):
        raise ValueError("Coolify environment must be a regular file, not a symlink")
    original = path.read_text(encoding="utf-8")
    updated = complete_environment(original, require_existing=require_existing)
    if reverb:
        updated = complete_reverb_environment(updated)
    if check_only:
        return False
    if updated == original:
        return False
    fd, name = tempfile.mkstemp(prefix=".solo-vps-env-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        if hasattr(os, "chown"):
            os.chown(temporary, previous.st_uid, previous.st_gid)
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--require-existing", action="store_true")
    parser.add_argument("--reverb", action="store_true", help="validate/migrate the reviewed local realtime backend")
    parser.add_argument("--check", action="store_true", help="validate without changing the file")
    args = parser.parse_args()
    try:
        changed = initialize(args.path, require_existing=args.require_existing, reverb=args.reverb, check_only=args.check)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"ERROR Coolify environment: {exc}\n")
    print(json.dumps({"changed": changed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
