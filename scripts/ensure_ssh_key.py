#!/usr/bin/env python3
"""Ensure the default Solo VPS controller SSH key exists without overwriting identity."""

from __future__ import annotations

import argparse
import os
import pathlib
import socket
import subprocess
import sys

SUPPORTED_PREFIXES = (
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
)


class KeyError(RuntimeError):
    pass


def validate_public_key(path: pathlib.Path) -> None:
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise KeyError(f"cannot read SSH public key {path}: {exc}") from exc

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) != 1:
        raise KeyError(f"SSH public key must contain exactly one non-empty line: {path}")
    parts = lines[0].split()
    if len(parts) < 2 or parts[0] not in SUPPORTED_PREFIXES:
        raise KeyError(f"unsupported or malformed OpenSSH public key: {path}")
    if "PRIVATE KEY" in content:
        raise KeyError(f"public-key path contains private-key material: {path}")


def ensure_key(private_key: pathlib.Path) -> tuple[pathlib.Path, str]:
    private_key = private_key.expanduser()
    public_key = pathlib.Path(f"{private_key}.pub")
    private_exists = private_key.is_file()
    public_exists = public_key.is_file()

    private_key.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private_key.parent, 0o700)

    if not private_exists and not public_exists:
        comment = f"solo-vps-controller@{socket.gethostname()}"
        try:
            subprocess.run(
                [
                    "ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-C",
                    comment,
                    "-f",
                    str(private_key),
                ],
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise KeyError(f"failed to create SSH key {private_key}: {exc}") from exc
        private_exists = True
        public_exists = True
        action = "created"
    elif private_exists and not public_exists:
        try:
            result = subprocess.run(
                ["ssh-keygen", "-y", "-f", str(private_key)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
            public_key.write_text(result.stdout.strip() + "\n", encoding="utf-8")
        except (OSError, subprocess.CalledProcessError) as exc:
            raise KeyError(f"failed to derive missing public key from {private_key}: {exc}") from exc
        public_exists = True
        action = "recovered-public-key"
    elif not private_exists and public_exists:
        action = "existing-public-only"
    else:
        action = "existing"

    if private_exists:
        os.chmod(private_key, 0o600)
    if public_exists:
        os.chmod(public_key, 0o644)
        validate_public_key(public_key)

    return public_key, action


def main() -> int:
    parser = argparse.ArgumentParser(description="Create/reuse the Solo VPS controller SSH key safely.")
    parser.add_argument(
        "--private-key",
        default="~/.ssh/id_ed25519",
        help="Controller private-key path; default: ~/.ssh/id_ed25519",
    )
    args = parser.parse_args()

    try:
        public_key, action = ensure_key(pathlib.Path(args.private_key))
    except KeyError as exc:
        print(f"ERROR SSH key setup: {exc}", file=sys.stderr)
        return 2

    print(f"PASS SSH key setup: {action}")
    print(f"  public_key: {public_key}")
    if action == "existing-public-only":
        print(
            "  note: matching private key was not found beside this public key; "
            "SSH must obtain the private identity from an agent or another configured source."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
