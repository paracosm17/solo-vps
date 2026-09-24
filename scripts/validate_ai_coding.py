#!/usr/bin/env python3
"""Validate the repository-local Codex/skill configuration without network access."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path


REQUIRED_AGENTS = {
    "architect": ("gpt-6-astra", "read-only"),
    "explorer": ("gpt-6-luna", "read-only"),
    "reviewer": ("gpt-6-sol", "read-only"),
    "release_guard": ("gpt-6-astra", "read-only"),
    "runtime_planner": ("gpt-6-astra", "read-only"),
}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def parse_skill_frontmatter(path: Path, errors: list[str]) -> tuple[str, str] | None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        fail(errors, f"{path}: SKILL.md must start with YAML front matter")
        return None
    try:
        end = lines.index("---", 1)
    except ValueError:
        fail(errors, f"{path}: missing closing front-matter delimiter")
        return None

    fields: dict[str, str] = {}
    for line in lines[1:end]:
        match = re.match(r"^(name|description):\s*(.+?)\s*$", line)
        if match:
            fields[match.group(1)] = match.group(2)

    name = fields.get("name", "")
    description = fields.get("description", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        fail(errors, f"{path}: name must be non-empty kebab-case")
    if not description:
        fail(errors, f"{path}: description is required")
    elif len(description) > 220:
        fail(errors, f"{path}: description is {len(description)} chars; keep it <= 220 for discovery")
    if len(lines) > 250:
        fail(errors, f"{path}: {len(lines)} lines is too large for a root skill; move detail to references")
    return name, description


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors: list[str] = []

    agents_md = root / "AGENTS.md"
    if not agents_md.is_file():
        fail(errors, "AGENTS.md: missing repository agent guide")
    elif len(agents_md.read_text(encoding="utf-8").splitlines()) > 220:
        fail(errors, "AGENTS.md: keep repository-wide instructions concise (<= 220 lines)")

    config_path = root / ".codex" / "config.toml"
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        fail(errors, f"{config_path}: invalid or missing TOML: {exc}")
        config = {}

    if config.get("model") != "gpt-6-sol":
        fail(errors, f"{config_path}: primary model should be gpt-6-sol")
    if config.get("model_reasoning_effort") != "medium":
        fail(errors, f"{config_path}: primary reasoning effort should be medium")
    agents_cfg = config.get("agents", {})
    if agents_cfg.get("enabled") is not True:
        fail(errors, f"{config_path}: multi-agent tools must be enabled")
    if agents_cfg.get("max_concurrent_threads_per_session") != 3:
        fail(errors, f"{config_path}: concurrency should remain capped at 3")
    if agents_cfg.get("default_subagent_model") != "gpt-6-luna":
        fail(errors, f"{config_path}: default subagent model should be gpt-6-luna")
    if agents_cfg.get("default_subagent_reasoning_effort") != "high":
        fail(errors, f"{config_path}: Luna subagents should default to high reasoning")

    agent_dir = root / ".codex" / "agents"
    seen_agents: set[str] = set()
    for path in sorted(agent_dir.glob("*.toml")):
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            fail(errors, f"{path}: invalid TOML: {exc}")
            continue
        name = data.get("name")
        if not isinstance(name, str) or not name:
            fail(errors, f"{path}: custom agent requires a name")
            continue
        if name in seen_agents:
            fail(errors, f"{path}: duplicate custom-agent name {name!r}")
        seen_agents.add(name)
        if not data.get("description"):
            fail(errors, f"{path}: custom agent requires a description")
        if not data.get("developer_instructions"):
            fail(errors, f"{path}: custom agent requires developer_instructions")

    for name, (model, sandbox) in REQUIRED_AGENTS.items():
        path = agent_dir / f"{name.replace('_', '-')}.toml"
        if not path.is_file():
            fail(errors, f"{path}: missing required custom agent")
            continue
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        if data.get("name") != name:
            fail(errors, f"{path}: expected name={name!r}")
        if data.get("model") != model:
            fail(errors, f"{path}: expected model={model!r}")
        if data.get("sandbox_mode") != sandbox:
            fail(errors, f"{path}: expected sandbox_mode={sandbox!r}")

    skill_paths = sorted((root / ".agents" / "skills").glob("*/SKILL.md"))
    if not skill_paths:
        fail(errors, ".agents/skills: no repository skills found")
    seen_skills: dict[str, Path] = {}
    for path in skill_paths:
        parsed = parse_skill_frontmatter(path, errors)
        if not parsed:
            continue
        name, _ = parsed
        if name in seen_skills:
            fail(errors, f"{path}: duplicate skill name also used by {seen_skills[name]}")
        else:
            seen_skills[name] = path

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        f"PASS AI coding config: {len(skill_paths)} focused skills, "
        f"{len(seen_agents)} custom agents, Sol/Medium primary, Luna/High default subagents"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
