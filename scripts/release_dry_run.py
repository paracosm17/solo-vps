#!/usr/bin/env python3
"""Fail-closed, no-publish release dry run for Solo VPS."""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

VERSION_RE = re.compile(r"^v0\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
CHANGELOG_RELEASE_RE_TEMPLATE = r"(?m)^## \[{version}\] - \d{{4}}-\d{{2}}-\d{{2}}\s*$"
REQUIRED_TRACKED = {
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "PROJECT_PASSPORT.md",
    "ROADMAP.md",
    "Makefile",
    "docs/release-process.md",
}
FORBIDDEN_EXACT_PATHS = {
    "config/config.yml",
    "inventory.yml",
    ".sops.yaml",
    "secrets/recipients/production.txt",
}
FORBIDDEN_PREFIXES = (
    ".git/",
    ".venv/",
    "ansible/inventories/local/",
)
PRIVATE_KEY_FILENAME_RE = re.compile(
    r"(^|/)(id_(rsa|dsa|ecdsa|ed25519)|.*\.(pem|key|p12|pfx))$",
    re.IGNORECASE,
)
AGE_PRIVATE_PREFIX = b"AGE-" + b"SECRET-KEY-1"
PRIVATE_KEY_CONTENT_RE = re.compile(
    rb"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----|" + AGE_PRIVATE_PREFIX + rb"[0-9A-Z]{40,}",
    re.IGNORECASE,
)


class ReleaseCheckError(RuntimeError):
    pass


def forbidden_operator_path(name: str) -> bool:
    normalized = name.replace("\\", "/")
    basename = PurePosixPath(normalized).name
    if normalized in FORBIDDEN_EXACT_PATHS or normalized.startswith(FORBIDDEN_PREFIXES):
        return True
    if basename == ".env" or (basename.startswith(".env.") and basename != ".env.example"):
        return True
    if normalized.startswith("secrets/") and normalized not in {
        "secrets/README.md", "secrets/recipients/production.example.txt"
    } and not normalized.endswith(".enc.yaml"):
        return True
    return bool(PRIVATE_KEY_FILENAME_RE.search(normalized))


def run_git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def validate_version(version: str) -> str:
    match = VERSION_RE.fullmatch(version)
    if not match:
        raise ReleaseCheckError(
            "release version must match PRE-ALPHA tag form v0.MINOR.PATCH; v1+ is blocked by the ROADMAP release gate"
        )
    if int(match.group(1)) == 0:
        raise ReleaseCheckError("the first public release must start no lower than v0.1.0")
    return version[1:]


def require_release_files(root: Path, version_without_v: str) -> None:
    license_path = root / "LICENSE"
    if not license_path.is_file() or not license_path.read_text(encoding="utf-8").strip():
        raise ReleaseCheckError(
            "root LICENSE is required before a public release; the selected project license must be published in the repository"
        )

    changelog_path = root / "CHANGELOG.md"
    if not changelog_path.is_file():
        raise ReleaseCheckError("CHANGELOG.md is required")
    changelog = changelog_path.read_text(encoding="utf-8")
    if "## [Unreleased]" not in changelog:
        raise ReleaseCheckError("CHANGELOG.md must retain an Unreleased section")
    release_re = re.compile(
        CHANGELOG_RELEASE_RE_TEMPLATE.format(version=re.escape(version_without_v))
    )
    if not release_re.search(changelog):
        raise ReleaseCheckError(
            f"CHANGELOG.md must contain a dated release heading: ## [{version_without_v}] - YYYY-MM-DD"
        )


def require_git_state(root: Path, version: str) -> None:
    try:
        inside = run_git(root, "rev-parse", "--is-inside-work-tree").stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise ReleaseCheckError("release dry run requires an initialized Git worktree") from exc
    if inside != "true":
        raise ReleaseCheckError("release dry run requires an initialized Git worktree")

    status = run_git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout
    if status.strip():
        raise ReleaseCheckError("Git worktree must be clean before a release dry run")

    tag_check = run_git(root, "rev-parse", "-q", "--verify", f"refs/tags/{version}", check=False)
    if tag_check.returncode == 0:
        raise ReleaseCheckError(f"tag {version} already exists; released versions are immutable")

    for path in sorted(REQUIRED_TRACKED):
        tracked = run_git(root, "ls-files", "--error-unmatch", "--", path, check=False)
        if tracked.returncode != 0:
            raise ReleaseCheckError(f"required release file is not tracked by Git: {path}")


def inspect_archive_member(name: str, data: bytes | None) -> None:
    normalized = str(PurePosixPath(name))
    if normalized.startswith("../") or normalized.startswith("/"):
        raise ReleaseCheckError(f"unsafe path in release archive: {name}")
    if forbidden_operator_path(normalized):
        raise ReleaseCheckError(f"forbidden operator/local path is tracked in release snapshot: {normalized}")
    if data is not None and PRIVATE_KEY_CONTENT_RE.search(data):
        raise ReleaseCheckError(f"private-key material detected in release snapshot: {normalized}")


def inspect_git_archive(root: Path) -> int:
    try:
        archive = subprocess.run(
            ["git", "archive", "--format=tar", "HEAD"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise ReleaseCheckError("git archive HEAD failed during dry run") from exc

    member_count = 0
    with tempfile.TemporaryDirectory(prefix="solo-vps-release-"):
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tf:
            for member in tf.getmembers():
                member_count += 1
                if member.issym() or member.islnk():
                    raise ReleaseCheckError(f"release snapshot contains a symbolic/hard link: {member.name}")
                if member.isdir():
                    continue
                data = None
                if member.isfile():
                    extracted = tf.extractfile(member)
                    data = extracted.read() if extracted is not None else b""
                inspect_archive_member(member.name, data)
    if member_count == 0:
        raise ReleaseCheckError("release snapshot is empty")
    return member_count


def inspect_reachable_history(root: Path) -> int:
    """Inspect every locally reachable ref, including files deleted before HEAD."""
    names = run_git(root, "log", "--all", "--name-only", "--format=").stdout
    historical_paths = {line.strip().replace("\\", "/") for line in names.splitlines() if line.strip()}
    for normalized in sorted(historical_paths):
        if forbidden_operator_path(normalized):
            raise ReleaseCheckError(f"forbidden operator/local path exists in reachable Git history: {normalized}")

    try:
        patches = subprocess.run(
            ["git", "log", "--all", "--format=", "--patch", "--binary", "--no-ext-diff"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise ReleaseCheckError("reachable Git history inspection failed") from exc
    if PRIVATE_KEY_CONTENT_RE.search(patches):
        raise ReleaseCheckError("private-key material detected in reachable Git history")

    revision_count = int(run_git(root, "rev-list", "--count", "--all").stdout.strip() or "0")
    if revision_count == 0:
        raise ReleaseCheckError("reachable Git history is empty")
    return revision_count


def run_checks(root: Path, version: str) -> list[str]:
    version_without_v = validate_version(version)
    require_release_files(root, version_without_v)
    require_git_state(root, version)
    revision_count = inspect_reachable_history(root)
    member_count = inspect_git_archive(root)
    return [
        f"PASS release version: {version}",
        "PASS license/changelog prerequisites",
        "PASS clean Git state and absent release tag",
        f"PASS reachable Git history inspection: {revision_count} revisions",
        f"PASS tracked release snapshot inspection: {member_count} entries",
        "PASS DRY RUN ONLY: no tag, push, release, upload, or external write was performed",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="project repository root")
    parser.add_argument("--version", required=True, help="candidate release tag, e.g. v0.1.0")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    try:
        messages = run_checks(root, args.version)
    except ReleaseCheckError as exc:
        print(f"ERROR release dry run: {exc}", file=sys.stderr)
        print("NO RELEASE ACTIONS WERE PERFORMED", file=sys.stderr)
        return 2

    for message in messages:
        print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
