#!/usr/bin/env python3
"""Validate the M20 controller QA contract without installing tooling."""

from __future__ import annotations

import argparse
import configparser
import pathlib
import re
import sys

import yaml

EXPECTED_PYTHON_PACKAGES = {
    "ansible-core": "2.21.3",
    "ansible-lint": "26.6.0",
    "yamllint": "1.38.0",
}
EXPECTED_COLLECTION = {"community.general": "13.0.1"}
REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)$")


class ContractError(ValueError):
    pass


def load_yaml(path: pathlib.Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"cannot read YAML {path}: {exc}") from exc


def parse_exact_requirements(path: pathlib.Path) -> dict[str, str]:
    found: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ContractError(f"cannot read {path}: {exc}") from exc

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = REQUIREMENT_RE.fullmatch(line)
        if not match:
            raise ContractError(f"QA dependency must use an exact == pin: {line!r}")
        name, version = match.groups()
        if name in found:
            raise ContractError(f"duplicate QA dependency: {name}")
        found[name] = version
    return found


def validate_requirements(path: pathlib.Path) -> None:
    found = parse_exact_requirements(path)
    if found != EXPECTED_PYTHON_PACKAGES:
        raise ContractError(
            f"QA dependency contract drift: expected {EXPECTED_PYTHON_PACKAGES}, found {found}"
        )


def validate_collection_requirements(path: pathlib.Path) -> None:
    data = load_yaml(path)
    collections = data.get("collections") if isinstance(data, dict) else None
    if not isinstance(collections, list):
        raise ContractError("ansible/requirements.yml must define a collections list")

    found: dict[str, str] = {}
    for item in collections:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ContractError("each Ansible collection dependency must be a mapping with name")
        version = item.get("version")
        if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ContractError(f"collection {item['name']} must use an exact X.Y.Z pin")
        found[item["name"]] = version

    if found != EXPECTED_COLLECTION:
        raise ContractError(
            f"Ansible collection contract drift: expected {EXPECTED_COLLECTION}, found {found}"
        )



def validate_ansible_config(path: pathlib.Path) -> None:
    parser = configparser.ConfigParser()
    try:
        with path.open(encoding="utf-8") as handle:
            parser.read_file(handle)
    except (OSError, configparser.Error) as exc:
        raise ContractError(f"cannot read Ansible config {path}: {exc}") from exc

    roles_path = parser.get("defaults", "roles_path", fallback="").strip()
    if roles_path != "roles":
        raise ContractError(
            "ansible/ansible.cfg roles_path must be 'roles'; paths in this config are "
            "resolved relative to the ansible/ config directory"
        )

def validate_ansible_lint(path: pathlib.Path) -> None:
    data = load_yaml(path)
    if not isinstance(data, dict):
        raise ContractError(".ansible-lint must be a mapping")
    if data.get("profile") != "basic":
        raise ContractError("M20 foundation intentionally uses ansible-lint profile: basic")
    if data.get("offline") is not True:
        raise ContractError("ansible-lint must run offline after QA tooling is bootstrapped")
    excluded = data.get("exclude_paths")
    if not isinstance(excluded, list) or "legacy/" not in excluded:
        raise ContractError("legacy/ must remain outside new-implementation ansible-lint scope")

    skipped = data.get("skip_list")
    expected_skips = ["var-naming[no-role-prefix]"]
    if skipped != expected_skips:
        raise ContractError(
            "ansible-lint skip_list must contain only the reviewed "
            "var-naming[no-role-prefix] exception for the project-wide solo_vps_* namespace"
        )


def validate_yamllint(path: pathlib.Path) -> None:
    data = load_yaml(path)
    if not isinstance(data, dict):
        raise ContractError(".yamllint must be a mapping")
    if data.get("extends") != "default":
        raise ContractError("yamllint must extend the default ruleset")
    ignored = data.get("ignore")
    if not isinstance(ignored, str) or "legacy/" not in ignored:
        raise ContractError("legacy/ must remain outside new-implementation yamllint scope")
    rules = data.get("rules")
    if not isinstance(rules, dict) or rules.get("document-start") != "disable":
        raise ContractError("yamllint document-start policy drift")
    line_length = rules.get("line-length")
    if not isinstance(line_length, dict) or line_length.get("max") != 240:
        raise ContractError("yamllint line-length baseline must remain max 240 for M20")

    comments = rules.get("comments")
    if not isinstance(comments, dict) or comments.get("min-spaces-from-content") != 1:
        raise ContractError("yamllint comments policy must remain compatible with ansible-lint")
    if rules.get("comments-indentation") is not False:
        raise ContractError("yamllint comments-indentation must be false for ansible-lint compatibility")
    braces = rules.get("braces")
    if not isinstance(braces, dict) or braces.get("max-spaces-inside") != 1:
        raise ContractError("yamllint braces policy must remain compatible with ansible-lint")
    octal = rules.get("octal-values")
    if not isinstance(octal, dict) or octal.get("forbid-implicit-octal") is not True or octal.get("forbid-explicit-octal") is not True:
        raise ContractError("yamllint octal policy must remain compatible with ansible-lint")


def validate_named_playbook_imports(playbook_dir: pathlib.Path) -> None:
    for path in sorted(playbook_dir.glob("*.yml")):
        data = load_yaml(path)
        if not isinstance(data, list):
            continue
        for index, item in enumerate(data, start=1):
            if not isinstance(item, dict) or "ansible.builtin.import_playbook" not in item:
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ContractError(
                    f"top-level import_playbook entries must be named for ansible-lint name[play]: "
                    f"{path}:{index}"
                )



def validate_assert_condition_shapes(ansible_root: pathlib.Path) -> None:
    """Reject YAML shapes that Ansible cannot evaluate as conditional expressions."""

    for path in sorted(ansible_root.rglob("*.yml")):
        data = load_yaml(path)

        def walk(node, location: str = "root") -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in {"assert", "ansible.builtin.assert"} and isinstance(value, dict):
                        conditions = value.get("that")
                        if conditions is not None:
                            items = conditions if isinstance(conditions, list) else [conditions]
                            for index, condition in enumerate(items):
                                if not isinstance(condition, str):
                                    raise ContractError(
                                        "assert.that entries must parse as strings for strict "
                                        "Ansible conditionals; quote the complete expression when it "
                                        "contains YAML-significant text such as ': ': "
                                        f"{path}:{location}/that[{index}] parsed as "
                                        f"{type(condition).__name__}"
                                    )
                    walk(value, f"{location}/{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{location}[{index}]")

        walk(data)

def validate_yaml_eof_policy(root: pathlib.Path) -> None:
    """Mirror yamllint's no-extra-blank-lines-at-EOF policy without QA tooling."""

    ignored_parts = {"legacy", ".venv", "__pycache__"}
    for pattern in ("*.yml", "*.yaml"):
        for path in sorted(root.rglob(pattern)):
            if any(part in ignored_parts for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise ContractError(f"cannot read YAML formatting target {path}: {exc}") from exc
            if text.endswith("\n\n"):
                raise ContractError(
                    "YAML files must end after the final content line with exactly one newline; "
                    f"remove trailing blank lines: {path}"
                )


def validate_set_fact_sibling_dependencies(ansible_root: pathlib.Path) -> None:
    """Reject set_fact assignments that depend on siblings from the same task.

    Ansible evaluates the mapping used by one set_fact task without guaranteeing
    that a variable assigned by one key is available to another key in that same
    mapping. Keep dependent derivations in a later set_fact task instead.
    """

    def scalar_strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for nested in value.values():
                yield from scalar_strings(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from scalar_strings(nested)

    for path in sorted(ansible_root.rglob("*.yml")):
        data = load_yaml(path)

        def walk(node, location: str = "root") -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in {"set_fact", "ansible.builtin.set_fact"} and isinstance(value, dict):
                        assigned = {name for name in value if isinstance(name, str) and name != "cacheable"}
                        for assigned_name, assigned_value in value.items():
                            if assigned_name not in assigned:
                                continue
                            for candidate in assigned - {assigned_name}:
                                pattern = re.compile(
                                    rf"(?<![A-Za-z0-9_]){re.escape(candidate)}(?![A-Za-z0-9_])"
                                )
                                if any(pattern.search(fragment) for fragment in scalar_strings(assigned_value)):
                                    raise ContractError(
                                        "set_fact assignments must not depend on sibling facts from the same task; "
                                        "derive dependent facts in a later set_fact task: "
                                        f"{path}:{location}/{assigned_name} references {candidate}"
                                    )
                    walk(value, f"{location}/{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{location}[{index}]")

        walk(data)


def recipe_block(makefile: str, target: str) -> str:
    match = re.search(rf"^{re.escape(target)}:[^\n]*\n((?:\t[^\n]*\n)+)", makefile, re.MULTILINE)
    if not match:
        raise ContractError(f"missing Makefile target: {target}")
    return match.group(1)


def validate_makefile(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    required_targets = [
        "validate-qa-contract",
        "test-qa-contract",
        "qa-tools",
        "qa-check",
        "qa-static",
    ]
    for target in required_targets:
        if not re.search(rf"^{re.escape(target)}:", text, re.MULTILINE):
            raise ContractError(f"missing Makefile target: {target}")

    for assignment in (
        "QA_VENV ?= $(SOLO_VPS_TOOLCHAIN_DIR)/qa",
        "QA_COLLECTIONS_DIR ?= $(SOLO_VPS_TOOLCHAIN_DIR)/ansible-collections",
    ):
        if assignment not in text:
            raise ContractError(f"QA/controller tooling must default outside the Git checkout: {assignment}")

    for assignment in (
        "ANSIBLE_PLAYBOOK ?= $(QA_ANSIBLE_PLAYBOOK)",
        "ANSIBLE_GALAXY ?= $(QA_ANSIBLE_GALAXY)",
        "ANSIBLE_DOC ?= $(QA_ANSIBLE_DOC)",
        "ANSIBLE_COLLECTIONS_PATH ?= $(abspath $(QA_COLLECTIONS_DIR))",
        "export ANSIBLE_COLLECTIONS_PATH",
    ):
        if assignment not in text:
            raise ContractError(
                f"project runtime must default to the pinned persistent Ansible toolchain: {assignment}"
            )

    qa_tools = recipe_block(text, "qa-tools")
    if "sudo" in qa_tools or "/usr/local" in qa_tools:
        raise ContractError("qa-tools must remain controller-local and unprivileged")
    for token in (
        "sys.version_info >= (3, 12)",
        "-m venv",
        "qa-requirements.txt",
        "collection install",
        "ansible/requirements.yml",
    ):
        if token not in qa_tools:
            raise ContractError(f"qa-tools is missing required bootstrap step: {token}")
    if 'touch "$(QA_READY_MARKER)"' not in qa_tools:
        raise ContractError("qa-tools must mark readiness only after all install steps succeed")

    deps = recipe_block(text, "deps")
    if "$(ANSIBLE_COLLECTIONS_PATH)" not in deps or "-p" not in deps:
        raise ContractError("make deps must install into the persistent collection path")

    qa_check = recipe_block(text, "qa-check")
    if "QA_READY_MARKER" not in qa_check:
        raise ContractError("qa-check must reject partial QA bootstrap state")
    if '[ -f "$(QA_READY_MARKER)" ]' not in text:
        raise ContractError("make validate must only auto-run QA after the ready marker exists")

    qa_static = recipe_block(text, "qa-static")
    positions = [qa_static.find(token) for token in ("QA_YAMLLINT", "ansible-syntax", "QA_ANSIBLE_LINT")]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        raise ContractError("qa-static must run yamllint -> ansible-syntax -> ansible-lint")
    if "pip install" in qa_static or "collection install" in qa_static:
        raise ContractError("qa-static must not install dependencies or contact registries")


def validate_root(root: pathlib.Path) -> None:
    validate_requirements(root / "tools/qa-requirements.txt")
    validate_collection_requirements(root / "ansible/requirements.yml")
    validate_ansible_config(root / "ansible/ansible.cfg")
    validate_ansible_lint(root / ".ansible-lint")
    validate_yamllint(root / ".yamllint")
    validate_named_playbook_imports(root / "ansible/playbooks")
    validate_assert_condition_shapes(root / "ansible")
    validate_set_fact_sibling_dependencies(root / "ansible")
    validate_yaml_eof_policy(root)
    validate_makefile(root / "Makefile")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()
    try:
        validate_root(root)
    except (ContractError, OSError) as exc:
        print(f"ERROR QA contract: {exc}", file=sys.stderr)
        return 2
    print("PASS QA contract: pinned controller tools, lint policy, and Makefile sequencing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
