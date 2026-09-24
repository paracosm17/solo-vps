#!/usr/bin/env python3
"""Validate the M29 upgrade-guide contract against current project sources."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml


class ContractError(ValueError):
    pass


REQUIRED_HEADINGS = (
    "## Upgrade safety model",
    "## Update Solo VPS source",
    "## Project automation and host configuration",
    "## Docker Engine and Compose",
    "## Coolify",
    "## Pinned controller and project dependencies",
    "## SOPS, age, and restic",
    "## Optional modules",
    "## Rollback and recovery",
    "## Upgrade checklist",
    "## Current limitations",
)

REQUIRED_SAFETY_PHRASES = (
    "PRE-ALPHA",
    "controller state is now external to the checkout",
    "make paths",
    "A previous project checkout is **not** a generic runtime rollback.",
    "make validate",
    "make doctor",
    "make verify",
    "make audit",
    "If a change cannot describe its recovery path, it is not ready for production execution.",
    "new checkout of a reviewed release",
    "not by running `git pull` in the active checkout",
    "RELEASE_VERSION='v0.1.0'",
    "test \"$(git describe --tags --exact-match)\" = \"$RELEASE_VERSION\"",
)


ADR_STATUS_RE = re.compile(
    r"^Status:\s*(Proposed|Accepted|Superseded|Deprecated|Rejected)\s*$", re.MULTILINE
)


def read(path: Path) -> str:
    if not path.is_file():
        raise ContractError(f"required file missing: {path}")
    return path.read_text(encoding="utf-8")


def yaml_load(path: Path):
    return yaml.safe_load(read(path))


def parse_exact_requirements(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in read(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise ContractError(f"QA requirement is not exact-pinned: {line}")
        name, version = line.split("==", 1)
        result[name.strip()] = version.strip()
    return result


def docker_apt_state(root: Path) -> str:
    data = yaml_load(root / "ansible" / "roles" / "docker" / "tasks" / "main.yml")
    for task in data:
        apt = task.get("ansible.builtin.apt") if isinstance(task, dict) else None
        if not isinstance(apt, dict):
            continue
        if "solo_vps_docker_packages" in str(apt.get("name", "")):
            return str(apt.get("state", ""))
    raise ContractError("cannot find Docker package install task using solo_vps_docker_packages")


def adr_status(path: Path) -> str:
    match = ADR_STATUS_RE.search(read(path))
    if not match:
        raise ContractError(f"ADR has no canonical status: {path}")
    return match.group(1)


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
            raise ContractError(f"upgrade guide link escapes repository: {target}") from exc
        if not resolved.exists():
            raise ContractError(f"upgrade guide link target does not exist: {target}")


def validate_upgrade_guide(root: Path) -> None:
    guide_path = root / "docs" / "upgrades.md"
    guide = read(guide_path)
    readme = read(root / "README.md")
    docs_index = read(root / "docs" / "index.md")
    roadmap = read(root / "ROADMAP.md")

    if not guide.startswith("# Upgrade guide\n"):
        raise ContractError("upgrade guide must start with '# Upgrade guide'")

    positions = []
    for heading in REQUIRED_HEADINGS:
        position = guide.find(heading)
        if position < 0:
            raise ContractError(f"upgrade guide missing required heading: {heading}")
        positions.append(position)
    if positions != sorted(positions):
        raise ContractError("upgrade guide sections are out of required order")

    for phrase in REQUIRED_SAFETY_PHRASES:
        if phrase not in guide:
            raise ContractError(f"upgrade guide missing required safety phrase: {phrase!r}")

    if docker_apt_state(root) != "present":
        raise ContractError("Docker role package-state contract changed; update M29 guide and validator")
    for phrase in (
        "Docker 29.x",
        "Docker 30",
        "`make docker` does not upgrade an already-installed Docker Engine",
        "fail closed",
    ):
        if phrase not in guide:
            raise ContractError(f"upgrade guide missing Docker lifecycle boundary: {phrase!r}")

    docker_defaults = yaml_load(root / "ansible" / "roles" / "docker" / "defaults" / "main.yml")
    if docker_defaults.get("solo_vps_docker_supported_major_versions") != [29]:
        raise ContractError("Docker alpha support window must remain major 29 only")

    coolify_status = adr_status(root / "docs" / "adr" / "0001-coolify-installation-boundary.md")
    if coolify_status != "Accepted":
        raise ContractError("M29 expects ADR-0001 to remain Accepted")
    required = (
        "Solo VPS manages Coolify through a pinned, reviewed integration.",
        "previous supported Coolify: `4.1.1`",
        "current supported Coolify: `4.1.2`",
        "make coolify-upgrade-preflight",
        "make coolify-upgrade",
        "make coolify-upgrade-resume",
        "does not automatically downgrade Coolify",
        "database migrations",
        "AUTOUPDATE=false",
    )
    for phrase in required:
        if phrase not in guide:
            raise ContractError(f"Accepted ADR-0001 requires Coolify lifecycle boundary: {phrase!r}")

    requirements = yaml_load(root / "ansible" / "requirements.yml")
    collections = requirements.get("collections", []) if isinstance(requirements, dict) else []
    community = next((item for item in collections if item.get("name") == "community.general"), None)
    if not community or not re.fullmatch(r"\d+\.\d+\.\d+", str(community.get("version", ""))):
        raise ContractError("community.general must remain exact-version pinned")

    qa = parse_exact_requirements(root / "tools" / "qa-requirements.txt")
    for name in ("ansible-core", "ansible-lint", "yamllint"):
        if name not in qa:
            raise ContractError(f"QA source of truth missing {name}")

    secrets = json.loads(read(root / "tools" / "secrets-toolchain.json"))
    for name in ("sops", "age"):
        version = str(secrets.get("tools", {}).get(name, {}).get("version", ""))
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ContractError(f"secrets tool is not exact-version pinned: {name}")

    backup_defaults = yaml_load(root / "ansible" / "roles" / "backup" / "defaults" / "main.yml")
    restic_version = str(backup_defaults.get("solo_vps_restic_version", ""))
    if not re.fullmatch(r"\d+\.\d+\.\d+", restic_version):
        raise ContractError("restic source of truth is not exact-version pinned")

    dockerfile = read(root / "examples" / "hello-app" / "Dockerfile")
    if not re.search(r"^FROM python:\d+\.\d+\.\d+-slim-bookworm$", dockerfile, re.MULTILINE):
        raise ContractError("sample Python base image must remain exact patch-tagged")

    # Keep the guide anchored to source files rather than duplicated ad-hoc update knobs.
    for source in (
        "ansible/requirements.yml",
        "tools/qa-requirements.txt",
        "tools/secrets-toolchain.json",
        "ansible/roles/backup/defaults/main.yml",
        "examples/hello-app/Dockerfile",
        "templates/github-actions/hello-app-ci.yml",
        "docs/contracts/platform-lifecycle-policy.yml",
    ):
        if f"`{source}`" not in guide:
            raise ContractError(f"upgrade guide missing authoritative source reference: {source}")

    dangerous = (
        r"git\s+pull\s+(?:origin\s+)?main",
        r"apt(?:-get)?\s+(?:dist-|full-)?upgrade\s+-y",
        r"curl[^\n|]*coolify/install\.sh\s*\|\s*bash",
        r"restic\s+self-update",
    )
    # Unsafe commands may be discussed only as explicitly rejected examples, not inside executable shell fences.
    code_blocks = "\n".join(
        re.findall(r"^```(?:bash|sh)\s*$\n(.*?)^```\s*$", guide, flags=re.DOTALL | re.MULTILINE)
    )
    for pattern in dangerous:
        if re.search(pattern, code_blocks, flags=re.IGNORECASE):
            raise ContractError(f"upgrade guide contains unsafe executable upgrade shortcut: {pattern}")

    if "](docs/upgrades.md)" not in readme:
        raise ContractError("README must link docs/upgrades.md")
    if "](upgrades.md)" not in docs_index:
        raise ContractError("docs/index.md must link upgrades.md")
    if "M29 — Upgrade Guide" not in roadmap:
        raise ContractError("ROADMAP no longer contains M29 Upgrade Guide milestone")

    validate_local_links(root, guide_path, guide)
    print(
        "PASS upgrade guide contract: safety sequence, Docker/Coolify boundaries, "
        "authoritative pins, recovery semantics, and public navigation are consistent"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate_upgrade_guide(Path(args.root).resolve())
    except (OSError, ValueError, ContractError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"ERROR upgrade guide contract: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
