#!/usr/bin/env python3
"""Validate the CRIT-016 application migration/image-rollback boundary."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


class MigrationContractError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MigrationContractError(message)


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MigrationContractError(f"{path} must contain a YAML mapping")
    return value


def validate(root: Path) -> None:
    policy_path = root / "docs/contracts/application-migration-policy.yml"
    workflow_path = root / "templates/github-actions/hello-app-ci.yml"
    hook_path = root / "examples/hello-app/migration_preflight.py"
    deploy_helper_path = root / "scripts/coolify_deploy_api.py"
    rollback_doc_path = root / "docs/operations/deployment-rollback.md"
    ci_doc_path = root / "docs/ci-ghcr.md"
    template_readme_path = root / "templates/github-actions/README.md"

    for path in (policy_path, workflow_path, hook_path, deploy_helper_path, rollback_doc_path, ci_doc_path, template_readme_path):
        require(path.is_file(), f"required CRIT-016 source is missing: {path.relative_to(root)}")

    policy = load_yaml(policy_path)
    require(policy.get("version") == 1, "migration policy version must be 1")
    require(policy.get("owner") == "application", "application must own migrations")
    boundary = policy.get("solo_vps_deployment_boundary")
    require(isinstance(boundary, dict), "migration policy must define solo_vps_deployment_boundary")
    require(boundary.get("rollback_scope") == "container-image-only", "rollback scope must be container-image-only")
    for key in ("database_schema_rollback", "application_data_rollback", "external_side_effect_rollback"):
        require(boundary.get(key) is False, f"{key} must explicitly be false")

    preflight = policy.get("migration_preflight")
    require(isinstance(preflight, dict), "migration policy must define migration_preflight")
    require(preflight.get("workflow_job") == "migration-preflight", "migration preflight job id must remain stable")
    require(preflight.get("workflow_name") == "Application migration preflight", "migration preflight job name must remain stable")
    require(preflight.get("sample_hook") == "examples/hello-app/migration_preflight.py", "sample hook path must remain explicit")
    require(preflight.get("production_credentials") is False, "migration preflight must not receive production credentials")
    require(preflight.get("production_mutation") is False, "migration preflight must be non-mutating")

    strategy = policy.get("recommended_strategy")
    require(isinstance(strategy, dict) and strategy.get("name") == "expand-contract", "expand-contract must remain recommended")
    irreversible = policy.get("irreversible_change")
    require(isinstance(irreversible, dict), "irreversible-change policy is required")
    requirements = irreversible.get("requires_before_deploy")
    require(isinstance(requirements, list) and len(requirements) >= 2, "irreversible changes need backup and recovery prerequisites")
    require(irreversible.get("image_rollback_is_not_recovery") is True, "irreversible migration policy must reject image rollback as DB recovery")

    workflow = load_yaml(workflow_path)
    jobs = workflow.get("jobs")
    require(isinstance(jobs, dict), "workflow.jobs must be a mapping")
    migration_job = jobs.get("migration-preflight")
    require(isinstance(migration_job, dict), "workflow must contain migration-preflight job")
    require(migration_job.get("name") == "Application migration preflight", "migration-preflight display name changed")
    require(migration_job.get("needs") == ["test"], "migration-preflight must run only after application/helper tests")
    require(migration_job.get("permissions") == {"contents": "read"}, "migration-preflight must remain read-only")
    require("environment" not in migration_job, "migration-preflight must not receive the production environment")
    steps = migration_job.get("steps")
    require(isinstance(steps, list), "migration-preflight steps must be a list")
    run_steps = [step for step in steps if isinstance(step, dict) and step.get("name") == "Run application-owned migration preflight"]
    require(len(run_steps) == 1, "workflow must run exactly one application-owned migration preflight hook")
    require(run_steps[0].get("run") == 'python3 "${APP_DIR}/migration_preflight.py"', "migration hook command changed")

    for job_name in ("build", "publish"):
        job = jobs.get(job_name)
        require(isinstance(job, dict), f"workflow job missing: {job_name}")
        needs = job.get("needs")
        require(needs == ["migration-preflight"], f"{job_name} must be gated by migration-preflight")

    hook = hook_path.read_text(encoding="utf-8")
    for marker in (
        'MIGRATION_MODE = "none"',
        "PASS application migration preflight",
        "database_mutation: false",
        "rollback_scope: container-image-only",
        "database_schema_rollback: false",
        "does not implement\na generic migration engine",
    ):
        require(marker in hook, f"sample migration hook missing marker: {marker}")

    helper = deploy_helper_path.read_text(encoding="utf-8")
    for marker in (
        'ROLLBACK_SCOPE = "container-image-only"',
        '"database_schema_rollback": False',
        '"application_data_rollback": False',
        '"external_side_effect_rollback": False',
        "rollback_scope: container-image-only",
    ):
        require(marker in helper, f"deployment helper must expose rollback boundary: {marker}")

    combined_docs = "\n".join(
        path.read_text(encoding="utf-8") for path in (rollback_doc_path, ci_doc_path, template_readme_path)
    )
    for marker in (
        "container image rollback",
        "expand/contract",
        "Application migration preflight",
        "application owns",
        "database rollback",
    ):
        require(marker.lower() in combined_docs.lower(), f"migration documentation missing boundary: {marker}")

    print("PASS application migration contract: app-owned non-mutating preflight + image-only rollback boundary are explicit")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate(Path(args.root).resolve())
    except MigrationContractError as exc:
        print(f"ERROR application migration contract: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
