#!/usr/bin/env python3
"""Validate the M30 source-only release-process contract."""

from __future__ import annotations

import re
import sys
from pathlib import Path


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def validate(root: Path) -> list[str]:
    docs = (root / "docs/release-process.md").read_text(encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    mkdocs = (root / "mkdocs.yml").read_text(encoding="utf-8")
    script = (root / "scripts/release_dry_run.py").read_text(encoding="utf-8")

    require("## [Unreleased]" in changelog, "CHANGELOG must contain Unreleased")
    require("PRE-ALPHA" in changelog, "CHANGELOG must preserve PRE-ALPHA status")
    require("v0.MINOR.PATCH" in docs and "v1.0.0" in docs, "release version semantics missing")
    require("make release-dry-run RELEASE_VERSION=v0.1.0" in docs, "dry-run command missing")
    require("root `LICENSE`" in docs, "license publication gate missing")
    require("make qa-static" in docs, "real M20 QA publication gate missing")
    require("CRIT-015 external-uptime evidence" in docs and "whole-target outage" in docs, "external uptime release gate missing")
    require(
        "CRIT-011 Coolify lifecycle evidence" in docs
        and "previous-supported" in docs
        and "current-supported" in docs
        and "4.1.1" in docs
        and "4.1.2" in docs,
        "Coolify lifecycle release gate missing",
    )
    require("explicitly approved" in docs or "explicit approval" in docs, "explicit publish approval boundary missing")
    require("does **not** run network requests" in docs, "dry-run no-network boundary missing")
    require("all locally reachable refs" in docs and "Gitleaks" in docs, "public-history secret-scan gate missing")
    require("GitHub automatically exposes source ZIP/tarball" in docs, "initial release artifact expectation missing")
    require("docs/release-process.md" in readme and "CHANGELOG.md" in readme, "README release navigation missing")
    require("release-process.md" in mkdocs and "exclude_docs" in mkdocs, "public docs must keep release evidence out of the user navigation")

    require("RELEASE_PROCESS_VALIDATOR" in makefile, "Makefile release validator wiring missing")
    require("RELEASE_DRY_RUN" in makefile, "Makefile release dry-run wiring missing")
    require("validate-release-process" in makefile and "test-release-process" in makefile, "release validation targets missing")
    require("release-dry-run:" in makefile, "release-dry-run target missing")
    release_recipe = makefile.split("release-dry-run:", 1)[1].split("\n\n", 1)[0]
    for forbidden in ("git tag", "git push", "gh release", "curl ", "wget ", "docker push"):
        require(forbidden not in release_recipe, f"release-dry-run recipe contains external/mutating action: {forbidden}")
    require("validate" in release_recipe, "release-dry-run must depend on source validation")
    require("qa-static" in release_recipe, "release-dry-run must enforce the real pinned M20 QA gate")

    require("VERSION_RE" in script and "^v0\\." in script, "dry-run must enforce v0.x tag form")
    require("root LICENSE is required" in script, "dry-run must fail closed without LICENSE")
    require("status\", \"--porcelain=v1" in script, "dry-run must require clean Git status")
    require("refs/tags/{version}" in script, "dry-run must reject an existing tag")
    require("git\", \"archive\", \"--format=tar\", \"HEAD" in script, "dry-run must inspect the tracked HEAD snapshot")
    require("inspect_reachable_history" in script and '"--all"' in script, "dry-run must inspect reachable Git history")
    require("NO RELEASE ACTIONS WERE PERFORMED" in script, "dry-run failure must preserve no-publish boundary")
    require(not re.search(r"subprocess\.(?:run|call|check_call)\([^\n]+(?:push|tag|release)", script), "dry-run script appears to execute a release mutation")

    if not (root / "LICENSE").exists():
        require("No root `LICENSE` exists yet" in readme, "README must expose current unlicensed state")

    return [
        "PASS release documentation contract",
        "PASS changelog Unreleased contract",
        "PASS fail-closed no-publish dry-run wiring",
        "PASS README maintainer navigation + public-docs separation",
    ]


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    try:
        messages = validate(root)
    except (ContractError, FileNotFoundError) as exc:
        print(f"ERROR release-process contract: {exc}", file=sys.stderr)
        return 2
    for message in messages:
        print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
