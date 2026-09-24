#!/usr/bin/env python3
"""Read-only M13 proof that the production age private identity is absent from the VPS."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import os
import subprocess
import sys


@dataclass(frozen=True)
class Candidate:
    path: Path
    requires_sudo: bool = False


def private_age_candidates(home: Path) -> tuple[Candidate, ...]:
    return (
        Candidate(home / ".config" / "solo-vps" / "age-key.txt"),
        Candidate(home / ".config" / "sops" / "age" / "keys.txt"),
        Candidate(Path("/root/.config/solo-vps/age-key.txt"), requires_sudo=True),
        Candidate(Path("/root/.config/sops/age/keys.txt"), requires_sudo=True),
    )


def _sudo_test_exists(path: Path) -> bool:
    result = subprocess.run(
        ["sudo", "-n", "test", "-e", str(path)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    detail = result.stderr.strip() or f"sudo test returned {result.returncode}"
    raise RuntimeError(f"cannot inspect {path} with passwordless sudo: {detail}")


def candidate_exists(candidate: Candidate) -> bool:
    if candidate.requires_sudo and os.geteuid() != 0:
        return _sudo_test_exists(candidate.path)
    return candidate.path.exists()


def resolve_admin_home(home_arg: str | None) -> Path:
    explicit = home_arg is not None
    if not explicit and os.geteuid() == 0:
        raise ValueError(
            "cannot infer the managed admin home while running as root; "
            "run this check as the Solo VPS admin or pass --home /home/<admin>"
        )

    home = Path(home_arg if explicit else Path.home()).expanduser().resolve()
    if home == Path("/root"):
        raise ValueError("managed admin home must be distinct from /root")
    if not home.is_dir():
        raise ValueError(f"home is not a directory: {home}")
    return home


def find_present_private_age_paths(home: Path) -> list[Path]:
    present: list[Path] = []
    for candidate in private_age_candidates(home):
        if candidate_exists(candidate):
            present.append(candidate.path)
    return present


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Solo VPS M13 check: verify that the standard production age private-key "
            "locations are absent from this VPS."
        )
    )
    parser.add_argument(
        "--home",
        default=None,
        help=(
            "managed non-root admin home to inspect; defaults to the current user's home. "
            "Required when the verifier is intentionally run as root."
        ),
    )
    args = parser.parse_args()

    if sys.platform != "linux":
        print("ERROR VPS secrets boundary: this verifier is intended for the Linux VPS", file=sys.stderr)
        return 2

    try:
        home = resolve_admin_home(args.home)
        present = find_present_private_age_paths(home)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR VPS secrets boundary: {exc}", file=sys.stderr)
        return 2

    if present:
        print("ERROR VPS secrets boundary: private age identity material exists in a standard Solo VPS/SOPS location:", file=sys.stderr)
        for path in present:
            print(f"  {path}", file=sys.stderr)
        print("Remove/correct it only after reviewing where the real workstation backup lives.", file=sys.stderr)
        return 2

    print("PASS VPS secrets boundary")
    print("  production age private identity on VPS: absent")
    print(f"  admin home checked: {home}")
    print("  root SOPS/Solo VPS key locations checked: yes")
    print("  filesystem mutation: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
