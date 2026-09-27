#!/usr/bin/env python3
"""Prepare a separate, exact-tag Solo VPS source checkout without host mutation."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


REPOSITORY_URL = "https://github.com/paracosm17/solo-vps.git"
VERSION_RE = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+")


class SourceUpdateError(ValueError):
    pass


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode:
        raise SourceUpdateError(f"git {args[0]} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def prepare(current: Path, version: str) -> Path:
    if not VERSION_RE.fullmatch(version):
        raise SourceUpdateError("RELEASE_VERSION must be an exact tag such as v0.2.3")
    current = current.resolve(strict=True)
    if git("rev-parse", "--show-toplevel", cwd=current) != str(current):
        raise SourceUpdateError("run this command from the root of the current Solo VPS checkout")
    if git("status", "--porcelain", "--untracked-files=all", cwd=current):
        raise SourceUpdateError("current source checkout has local changes; review and preserve them first")

    target = current.parent / f"solo-vps-{version}"
    if target.exists():
        raise SourceUpdateError(f"target already exists: {target}")
    git("clone", "--branch", version, "--depth", "1", REPOSITORY_URL, str(target), cwd=current.parent)
    if git("describe", "--tags", "--exact-match", cwd=target) != version:
        raise SourceUpdateError(f"cloned checkout did not resolve to exact tag {version}; inspect {target}")
    if git("status", "--porcelain", "--untracked-files=all", cwd=target):
        raise SourceUpdateError(f"cloned checkout is not clean; inspect {target}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--current", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        target = prepare(args.current, args.version)
    except (OSError, SourceUpdateError) as exc:
        print(f"ERROR source update preparation: {exc}", file=sys.stderr)
        return 2
    print(f"PASS exact release checkout prepared: {target}")
    print(f"NEXT: cd {target}")
    print("NEXT: make setup && make paths && make validate && make doctor")
    print("NEXT: compare state paths, read release notes, then run the required platform preflight or make verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
