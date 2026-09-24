#!/usr/bin/env python3
"""Fail closed when public Solo VPS source contains operator-specific state/evidence."""

from __future__ import annotations

import argparse
import ipaddress
from pathlib import Path
import re
import subprocess
import sys


class ContractError(RuntimeError):
    pass


NARRATIVE_FILES = ("README.md", "CHANGELOG.md", "ROADMAP.md")
NARRATIVE_DIRS = ("docs",)

# Public integration docs should describe invariants with placeholders, not preserve
# a maintainer's raw deployment diary.
_FORBIDDEN_EVIDENCE_PATTERNS = (
    (re.compile(r"\bTEST_\d+\b"), "private maintainer test labels"),
    (re.compile(r"\bOWNER\b"), "owner-specific validation label"),
    (re.compile(r"\bowner-target\b", re.IGNORECASE), "maintainer-target wording"),
    (
        re.compile(r"\bowner-(?:driven|controlled|validated|tested|provided|workstation)\b", re.IGNORECASE),
        "owner-specific integration diary wording",
    ),
    (re.compile(r"\bowner\s+(?:rerun|revision|proof)\b", re.IGNORECASE), "owner-specific integration diary wording"),
    (re.compile(r"sha256:[0-9a-f]{64}"), "concrete runtime image digest"),
    (re.compile(r"\bcommit\s+`?[0-9a-f]{40}`?", re.IGNORECASE), "concrete application commit SHA"),
    (re.compile(r"\bdeployment[_ -]?uuid\s*[=:]\s*`?[a-z0-9]{12,}`?", re.IGNORECASE), "concrete deployment UUID"),
    (re.compile(r"\bage1[0-9a-z]{40,}\b"), "real age public recipient"),
)

_IP_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")


_CONCRETE_PUBLIC_IDENTITY_PATTERNS = (
    (
        re.compile(
            r'\b(?:GITHUB_OWNER|GITHUB_USER(?:NAME)?|REGISTRY_USERNAME|GHCR_OWNER|GHCR_USER(?:NAME)?)\s*=\s*["\'](?!CHANGE_ME_|<)[A-Za-z0-9][A-Za-z0-9-]{0,38}["\']'
        ),
        "concrete GitHub/GHCR operator identity",
    ),
)


def _iter_narrative_files(root: Path):
    for rel in NARRATIVE_FILES:
        path = root / rel
        if path.is_file():
            yield path
    for rel in NARRATIVE_DIRS:
        base = root / rel
        if base.is_dir():
            yield from sorted(base.rglob("*.md"))



def _iter_identity_scan_files(root: Path):
    for path in sorted(root.glob("*.md")):
        if path.is_file():
            yield path
    for rel in ("docs", "legacy"):
        base = root / rel
        if base.is_dir():
            yield from sorted(base.rglob("*.md"))


def _is_tracked(root: Path, rel: str) -> bool | None:
    if not (root / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", rel],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def validate(root: Path) -> None:
    root = root.resolve()
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    for line in ("/.sops.yaml", "/secrets/recipients/production.txt"):
        if line not in gitignore.splitlines():
            raise ContractError(f".gitignore must keep operator-local state ignored: {line}")

    for rel in (".sops.yaml", "secrets/recipients/production.txt", "config/config.yml", "ansible/inventories/local/hosts.yml"):
        tracked = _is_tracked(root, rel)
        if tracked:
            raise ContractError(f"operator-specific file must not be tracked in public product source: {rel}")

    for path in _iter_narrative_files(root):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(root)
        for pattern, label in _FORBIDDEN_EVIDENCE_PATTERNS:
            match = pattern.search(text)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                raise ContractError(f"{rel}:{line} contains {label}; use a placeholder or invariant summary")

        for match in _IP_RE.finditer(text):
            raw = match.group(0)
            try:
                ip = ipaddress.ip_address(raw)
            except ValueError:
                continue
            # RFC 5737 documentation addresses are not is_global in Python;
            # loopback/private/link-local/reserved values are product mechanics, not owner state.
            if ip.is_global:
                line = text.count("\n", 0, match.start()) + 1
                raise ContractError(f"{rel}:{line} contains a public routable IP ({raw}); use RFC 5737/example data")


    for path in _iter_identity_scan_files(root):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(root)
        for pattern, label in _CONCRETE_PUBLIC_IDENTITY_PATTERNS:
            match = pattern.search(text)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                raise ContractError(f"{rel}:{line} contains {label}; use CHANGE_ME_/placeholder data")

    first_app = (root / "docs" / "operations" / "first-app.md").read_text(encoding="utf-8")
    if "app.example.com" not in first_app:
        raise ContractError("first-app guide must use app.example.com for the example application hostname")

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if "operator-specific validation values stay outside public source" not in changelog.lower():
        raise ContractError("CHANGELOG must record the public-product hygiene boundary")

    contributing = (root / "CONTRIBUTING.md").read_text(encoding="utf-8")
    for needle in (
        "operator-specific state",
        "RFC 5737",
        "image digests",
        "deployment UUIDs",
        "public age recipient",
    ):
        if needle not in contributing:
            raise ContractError(f"CONTRIBUTING.md must document public-product hygiene: {needle}")

    print("PASS public product hygiene: examples/placeholders only; operator-specific runtime evidence stays local")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate(Path(args.root))
    except (OSError, ContractError) as exc:
        print(f"ERROR public product hygiene: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
