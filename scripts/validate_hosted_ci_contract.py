#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import re
import sys
from typing import Any

import yaml


class ContractError(ValueError):
    pass


WORKFLOW = pathlib.Path(".github/workflows/repository-ci.yml")
MAKEFILE = pathlib.Path("Makefile")
TESTING_DOC = pathlib.Path("docs/testing.md")
RELEASE_DOC = pathlib.Path("docs/release-process.md")


def load_yaml_strings(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"cannot read hosted CI workflow {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError("hosted CI workflow must be a YAML mapping")
    return data


def require_text(path: pathlib.Path, needles: tuple[str, ...]) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"cannot read {path}: {exc}") from exc
    for needle in needles:
        if needle not in text:
            raise ContractError(f"{path} must document {needle!r}")


def validate_workflow(root: pathlib.Path) -> None:
    path = root / WORKFLOW
    data = load_yaml_strings(path)
    raw = path.read_text(encoding="utf-8")

    if data.get("name") != "Repository CI":
        raise ContractError("hosted CI workflow name must remain 'Repository CI'")

    triggers = data.get("on")
    if not isinstance(triggers, dict):
        raise ContractError("hosted CI must define explicit pull_request, push, and workflow_dispatch triggers")
    for trigger in ("pull_request", "push", "workflow_dispatch"):
        if trigger not in triggers:
            raise ContractError(f"hosted CI is missing required trigger: {trigger}")
    push = triggers.get("push")
    branches = push.get("branches") if isinstance(push, dict) else None
    if branches != ["main"]:
        raise ContractError("hosted CI push trigger must use the public main branch")

    permissions = data.get("permissions")
    if permissions != {"contents": "read"}:
        raise ContractError("hosted CI must use only contents: read workflow permissions")

    jobs = data.get("jobs")
    if not isinstance(jobs, dict) or "fast-source" not in jobs:
        raise ContractError("hosted CI must expose a stable fast-source job for branch protection")
    job = jobs["fast-source"]
    if not isinstance(job, dict):
        raise ContractError("hosted CI fast-source job must be a mapping")
    if job.get("name") != "fast-source":
        raise ContractError("hosted CI job display name must remain fast-source for a stable required check")
    if job.get("runs-on") != "ubuntu-24.04":
        raise ContractError("hosted CI must pin the supported Ubuntu runner to ubuntu-24.04")
    try:
        timeout = int(job.get("timeout-minutes", "0"))
    except ValueError as exc:
        raise ContractError("hosted CI timeout-minutes must be an integer") from exc
    if not 1 <= timeout <= 15:
        raise ContractError("hosted CI fast-source timeout must remain bounded to at most 15 minutes")

    env = job.get("env")
    if not isinstance(env, dict) or "runner.temp" not in str(env.get("SOLO_VPS_DATA_BASE", "")):
        raise ContractError("hosted CI mutable Solo VPS state must live under runner.temp")
    if "SOLO_VPS_CHECKOUT_TOKEN" in env:
        raise ContractError("github.token must not be exposed at job scope")

    steps = job.get("steps")
    if not isinstance(steps, list):
        raise ContractError("hosted CI fast-source must define an explicit steps list")
    checkout_steps = [step for step in steps if isinstance(step, dict) and str(step.get("name", "")).startswith("Check out the exact workflow revision")]
    if len(checkout_steps) != 1:
        raise ContractError("hosted CI must define exactly one exact-revision checkout step")
    checkout_step = checkout_steps[0]
    if checkout_step.get("env") != {"SOLO_VPS_CHECKOUT_TOKEN": "${{ github.token }}"}:
        raise ContractError("runner-provided github.token must be scoped only to the checkout step")
    for step in steps:
        if step is checkout_step:
            continue
        if "github.token" in str(step) or "SOLO_VPS_CHECKOUT_TOKEN" in str(step):
            raise ContractError("repository test/tool steps must not receive the checkout token")

    if re.search(r"\buses\s*:", raw):
        raise ContractError("fast hosted CI intentionally avoids external actions; keep checkout/tooling shell-owned")
    if "secrets." in raw or "${{ secrets" in raw:
        raise ContractError("fast hosted CI must not depend on repository or environment secrets")
    if raw.count("${{ github.token }}") != 1:
        raise ContractError("hosted checkout must reference github.token exactly once")
    if "self-hosted" in raw:
        raise ContractError("fast hosted CI must run on a GitHub-hosted disposable Ubuntu runner")
    for forbidden in ("make deploy", "make bootstrap", "make ssh-harden", "make audit", "make validate\n"):
        if forbidden in raw:
            raise ContractError(f"fast hosted CI must not run target-mutating/full aggregate command: {forbidden!r}")

    checkout_needles = (
        'git remote add origin "${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}.git"',
        'GIT_CONFIG_KEY_0="http.${GITHUB_SERVER_URL}/.extraheader"',
        'GIT_CONFIG_VALUE_0="AUTHORIZATION: basic ${auth_header}"',
        'fetch --no-tags --prune --depth=1 origin "${GITHUB_REF}"',
        'unset auth_header SOLO_VPS_CHECKOUT_TOKEN',
        'git checkout --detach FETCH_HEAD',
        'test "$(git rev-parse HEAD)" = "${GITHUB_SHA}"',
    )
    for needle in checkout_needles:
        if needle not in raw:
            raise ContractError(f"hosted CI exact-revision checkout contract is missing: {needle}")

    prerequisites = ("openssh-client", "python3-venv", "python3-yaml")
    for package in prerequisites:
        if package not in raw:
            raise ContractError(f"hosted CI must install deterministic controller prerequisite: {package}")
    if "make ci-fast" not in raw:
        raise ContractError("hosted CI must delegate its bounded source/Ansible gate to make ci-fast")


def target_body(makefile: str, target: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(target)}:[^\n]*\n((?:\t.*\n|\n)*)", makefile)
    if not match:
        raise ContractError(f"Makefile target is missing: {target}")
    return match.group(0)


def validate_makefile(root: pathlib.Path) -> None:
    path = root / MAKEFILE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"cannot read {path}: {exc}") from exc

    source_target = target_body(text, "ci-fast-source")
    fast_target = target_body(text, "ci-fast")

    required_source_checks = (
        "validate-platform-lifecycle",
        "test-platform-lifecycle",
        "validate-documentation-governance",
        "test-documentation-governance",
        "validate-operator-surface",
        "test-operator-surface",
        "validate-application-migration-contract",
        "test-application-migration-contract",
        "validate-hosted-ci-contract",
        "test-hosted-ci-contract",
        "validate-disposable-clean-target",
        "test-disposable-clean-target",
        "validate-disaster-recovery",
        "test-disaster-recovery",
        "validate-backup-runtime",
        "test-backup-runtime",
        "validate-backup-policy",
        "test-backup-policy",
        "validate-database-backup-contract",
        "test-database-backup-contract",
        "validate-database-backup-runtime",
        "test-database-backup-runtime",
        "validate-state-layout",
        "validate-yaml",
        "validate-onboarding-contract",
        "test-onboarding-contract",
        "validate-coolify-contract",
        "test-coolify-install-backend",
        "validate-ci-template",
        "test-ci-template",
        "test-coolify-deploy-api",
        "validate-public-product-hygiene",
        "test-public-product-hygiene",
        "validate-qa-contract",
        "test-qa-contract",
        "validate-release-process",
        "test-release-process",
        "validate-external-uptime",
        "test-external-uptime",
    )
    for target in required_source_checks:
        if target not in source_target:
            raise ContractError(f"ci-fast-source is missing required source gate: {target}")

    if "make validate" in source_target or " validate " in f" {source_target} ":
        raise ContractError("ci-fast-source must stay bounded and must not call the full make validate aggregate")
    for target in ("ci-fast-source", "qa-tools", "qa-static"):
        if target not in fast_target:
            raise ContractError(f"ci-fast must include {target}")

    qa_paths_match = re.search(r"(?m)^QA_YAML_PATHS\s*:=\s*(.+)$", text)
    if not qa_paths_match or WORKFLOW.as_posix() not in qa_paths_match.group(1):
        raise ContractError("qa-static yamllint scope must include the repository hosted CI workflow")


def validate_docs(root: pathlib.Path) -> None:
    require_text(
        root / TESTING_DOC,
        (
            "Repository CI",
            "fast-source",
            "ubuntu-24.04",
            "make ci-fast",
            "does not use deployment secrets",
            "self-repository",
            "Do not add `fast-source` to a consumer repository",
        ),
    )
    require_text(
        root / RELEASE_DOC,
        (
            "fast-source",
            "required status check",
            "must be green",
            "consumer-application checks never satisfy",
        ),
    )


def validate_root(root: pathlib.Path) -> None:
    validate_workflow(root)
    validate_makefile(root)
    validate_docs(root)


def main(argv: list[str]) -> int:
    root = pathlib.Path(argv[1] if len(argv) > 1 else ".").resolve()
    try:
        validate_root(root)
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print("PASS hosted repository CI contract: PR/main/manual fast-source gate is bounded, read-only, and secret-free")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
