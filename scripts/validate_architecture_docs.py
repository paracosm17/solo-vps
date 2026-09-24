#!/usr/bin/env python3
"""Validate the M27 architecture overview and ADR status contract."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


class ContractError(ValueError):
    pass


REQUIRED_HEADINGS = (
    "## Source-of-truth hierarchy",
    "## Accepted baseline",
    "## System map",
    "## Main flows",
    "## Ownership matrix",
    "## Accepted ADR decisions",
    "## Trust and exposure boundaries",
    "## Current evidence boundary",
    "## Architecture change rule",
)

REQUIRED_BASELINE_PHRASES = (
    "Ansible",
    "Coolify",
    "GitHub Actions",
    "GHCR",
    "SOPS + age",
    "restic + off-site storage",
)


ADR_TITLE_RE = re.compile(r"^# (ADR-\d{4}):\s+(.+)$", re.MULTILINE)
ADR_STATUS_RE = re.compile(r"^Status:\s*(Proposed|Accepted|Superseded|Deprecated|Rejected)\s*$", re.MULTILINE)


def parse_adr(path: Path) -> tuple[str, str, str]:
    text = path.read_text(encoding="utf-8")
    title_match = ADR_TITLE_RE.search(text)
    status_match = ADR_STATUS_RE.search(text)
    if not title_match:
        raise ContractError(f"ADR missing canonical title line: {path}")
    if not status_match:
        raise ContractError(f"ADR missing canonical status: {path}")
    return title_match.group(1), title_match.group(2).strip(), status_match.group(1)


def validate_local_links(root: Path, path: Path, markdown: str) -> None:
    for target in re.findall(r"\]\(([^)]+)\)", markdown):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        clean = target.split("#", 1)[0]
        if not clean:
            continue
        resolved = (path.parent / clean).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise ContractError(f"architecture link escapes repository: {target}") from exc
        if not resolved.exists():
            raise ContractError(f"architecture link target does not exist: {target}")


def validate_architecture(root: Path) -> None:
    architecture_path = root / "docs" / "architecture.md"
    docs_index_path = root / "docs" / "index.md"
    readme_path = root / "README.md"
    passport_path = root / "PROJECT_PASSPORT.md"
    roadmap_path = root / "ROADMAP.md"
    adr_dir = root / "docs" / "adr"

    architecture = architecture_path.read_text(encoding="utf-8")
    docs_index = docs_index_path.read_text(encoding="utf-8")
    readme = readme_path.read_text(encoding="utf-8")
    passport = passport_path.read_text(encoding="utf-8")
    roadmap = roadmap_path.read_text(encoding="utf-8")

    if not architecture.startswith("# Solo VPS architecture\n"):
        raise ContractError("architecture page must start with '# Solo VPS architecture'")

    positions = []
    for heading in REQUIRED_HEADINGS:
        position = architecture.find(heading)
        if position < 0:
            raise ContractError(f"architecture page missing required heading: {heading}")
        positions.append(position)
    if positions != sorted(positions):
        raise ContractError("architecture sections are out of the required order")

    for phrase in REQUIRED_BASELINE_PHRASES:
        if phrase not in architecture:
            raise ContractError(f"architecture page missing accepted baseline layer: {phrase}")

    # Repository-level sources live outside docs_dir. Keep their canonical
    # names visible without Markdown links so MkDocs link validation remains clean.
    required_source_mentions = (
        "README.md",
        "PROJECT_PASSPORT.md",
        "ROADMAP.md",
        ".agents/skills/solo-vps-project-engineer/SKILL.md",
    )
    for target in required_source_mentions:
        if target not in architecture:
            raise ContractError(f"architecture page missing canonical source mention: {target}")

    for phrase in ("north-star product/architecture boundary", "current user-facing supported contract"):
        if phrase not in architecture:
            raise ContractError(f"architecture page missing documentation truth boundary: {phrase}")

    if "This diagram is a responsibility map" not in architecture:
        raise ContractError("architecture diagram must state that it is not implementation evidence")
    if "PRE-ALPHA" not in architecture:
        raise ContractError("architecture page must preserve PRE-ALPHA evidence boundary")
    if "Acceptance establishes the architecture boundary" not in architecture:
        raise ContractError("architecture page must distinguish ADR acceptance from implementation evidence")

    # Localized ADR copies use the i18n suffix and must not be treated as
    # additional canonical architecture decisions.
    adrs = [
        path
        for path in sorted(adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md"))
        if not path.name.endswith(".ru.md")
    ]
    if not adrs:
        raise ContractError("no ADR files found")

    for adr_path in adrs:
        adr_id, _title, status = parse_adr(adr_path)
        relative = adr_path.relative_to(root / "docs").as_posix()
        link = f"]({relative})"
        if link not in architecture:
            raise ContractError(f"architecture page missing ADR link: {adr_id}")
        row_pattern = re.compile(
            rf"^\| \[`{re.escape(adr_id)}`\]\({re.escape(relative)}\) \| \*\*{re.escape(status)}\*\* \|",
            re.MULTILINE,
        )
        if not row_pattern.search(architecture):
            raise ContractError(f"architecture ADR status drift for {adr_id}: expected {status}")

    if "The project owner accepted all ADRs below" in architecture:
        non_accepted = [parse_adr(path)[0] for path in adrs if parse_adr(path)[2] != "Accepted"]
        if non_accepted:
            raise ContractError(
                "architecture claims all ADRs are Accepted but repository has other statuses: "
                + ", ".join(non_accepted)
            )

    # The Passport remains the accepted baseline. The overview must not silently
    # invent a different primary layer assignment.
    for phrase in (
        "The Ansible project owns the host layer",
        "Coolify owns the application platform",
        "GitHub Actions",
        "GHCR",
    ):
        if phrase not in passport:
            raise ContractError(f"Passport no longer supports architecture baseline phrase: {phrase}")

    if "M27 — Architecture Documentation & ADR" not in roadmap:
        raise ContractError("ROADMAP no longer contains M27 architecture milestone")
    if "](architecture.md)" not in docs_index:
        raise ContractError("docs/index.md must link architecture.md")
    if "docs/architecture.md" not in readme:
        raise ContractError("README documentation section must link docs/architecture.md")

    validate_local_links(root, architecture_path, architecture)
    print(
        "PASS architecture contract: canonical sources, accepted layer boundaries, "
        f"{len(adrs)} ADR statuses, evidence boundaries, and documentation links are consistent"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate_architecture(Path(args.root).resolve())
    except (OSError, ContractError) as exc:
        print(f"ERROR architecture contract: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
