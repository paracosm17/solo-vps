#!/usr/bin/env python3
"""Validate the opinionated M11 GitHub Actions/GHCR/Coolify template contract."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


ACTION_PIN_RE = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@(?P<sha>[0-9a-f]{40})$")
ALLOWED_ACTIONS = {
    "actions/checkout",
    "docker/setup-buildx-action",
    "docker/login-action",
    "docker/metadata-action",
    "docker/build-push-action",
}


def fail(message: str) -> None:
    raise ValueError(message)


def as_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        fail(f"{label} must be a mapping")
    return value


def as_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        fail(f"{label} must be a list")
    return value


def scalar(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def validate_actions(jobs: dict[str, object]) -> None:
    seen: set[str] = set()
    for job_name, raw_job in jobs.items():
        job = as_mapping(raw_job, f"jobs.{job_name}")
        steps = as_list(job.get("steps"), f"jobs.{job_name}.steps")
        for index, raw_step in enumerate(steps):
            step = as_mapping(raw_step, f"jobs.{job_name}.steps[{index}]")
            uses = step.get("uses")
            if uses is None:
                continue
            match = ACTION_PIN_RE.fullmatch(scalar(uses))
            if not match:
                fail(f"all actions must use a full 40-character commit SHA: {uses!r}")
            action = match.group("name")
            if action not in ALLOWED_ACTIONS:
                fail(f"unexpected action dependency: {action}")
            seen.add(action)

    missing = ALLOWED_ACTIONS - seen
    if missing:
        fail(f"missing required pinned actions: {', '.join(sorted(missing))}")


def find_action(steps: list[dict[str, object]], prefix: str) -> dict[str, object]:
    matches = [step for step in steps if scalar(step.get("uses")).startswith(prefix)]
    if len(matches) != 1:
        fail(f"expected exactly one {prefix} step")
    return matches[0]


def validate(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "pull_request_target" in text:
        fail("pull_request_target is forbidden for this untrusted-code build template")
    if re.search(r"(?i)appleboy/|ssh-action|strictHostKeyChecking\s*=\s*no|ssh-keyscan", text):
        fail("unreviewed SSH actions, ssh-keyscan trust, and disabled host-key verification are forbidden")
    if "latest" in re.sub(r"(?m)^\s*#.*$", "", text):
        fail("mutable latest identity is forbidden in the workflow")

    try:
        data = yaml.load(text, Loader=yaml.BaseLoader)
    except yaml.YAMLError as exc:
        fail(f"invalid YAML: {exc}")
    root = as_mapping(data, "workflow")
    allowed_root_keys = {"name", "on", "permissions", "env", "jobs"}
    if set(root) != allowed_root_keys:
        unexpected = set(root) - allowed_root_keys
        missing = allowed_root_keys - set(root)
        details = []
        if unexpected:
            details.append(f"unexpected: {', '.join(sorted(unexpected))}")
        if missing:
            details.append(f"missing: {', '.join(sorted(missing))}")
        fail(f"workflow top-level keys must match the M11 contract ({'; '.join(details)})")

    triggers = as_mapping(root.get("on"), "on")
    if set(triggers) != {"pull_request", "push"}:
        fail("workflow must trigger only on pull_request and push")
    push = as_mapping(triggers.get("push"), "on.push")
    branches = [scalar(item) for item in as_list(push.get("branches"), "on.push.branches")]
    if branches != ["main"]:
        fail("push publishing/deployment must be limited to main")

    permissions = as_mapping(root.get("permissions"), "permissions")
    if permissions != {"contents": "read"}:
        fail("workflow default permissions must be exactly contents: read")

    env = as_mapping(root.get("env"), "env")
    if env.get("REGISTRY") != "ghcr.io":
        fail("REGISTRY must be ghcr.io")
    if env.get("IMAGE_NAME") != "${{ github.repository }}":
        fail("IMAGE_NAME must follow github.repository")
    if env.get("APP_DIR") != "examples/hello-app":
        fail("initial template must target examples/hello-app")

    jobs = as_mapping(root.get("jobs"), "jobs")
    expected_jobs = {"test", "migration-preflight", "build", "publish", "verify-published", "deploy"}
    if set(jobs) != expected_jobs:
        fail("workflow must contain exactly test, migration-preflight, build, publish, verify-published, and deploy jobs")

    test_job = as_mapping(jobs["test"], "jobs.test")
    migration_job = as_mapping(jobs["migration-preflight"], "jobs.migration-preflight")
    build_job = as_mapping(jobs["build"], "jobs.build")
    publish_job = as_mapping(jobs["publish"], "jobs.publish")
    verify_job = as_mapping(jobs["verify-published"], "jobs.verify-published")
    deploy_job = as_mapping(jobs["deploy"], "jobs.deploy")

    for name, job in (
        ("test", test_job),
        ("migration-preflight", migration_job),
        ("build", build_job),
        ("publish", publish_job),
        ("verify-published", verify_job),
        ("deploy", deploy_job),
    ):
        if job.get("runs-on") != "ubuntu-24.04":
            fail(f"jobs.{name} must use ubuntu-24.04")

    if migration_job.get("needs") != ["test"]:
        fail("migration-preflight must depend only on test")
    migration_permissions = as_mapping(migration_job.get("permissions"), "jobs.migration-preflight.permissions")
    if migration_permissions != {"contents": "read"}:
        fail("migration-preflight permissions must be exactly contents: read")
    if "environment" in migration_job:
        fail("migration-preflight must not attach the production environment")
    if build_job.get("needs") != ["migration-preflight"]:
        fail("pull-request build must be gated by migration-preflight")
    if publish_job.get("needs") != ["migration-preflight"]:
        fail("publish must be gated by migration-preflight")

    if build_job.get("if") != "github.event_name == 'pull_request'":
        fail("build job must be pull-request-only")
    if publish_job.get("if") != "github.event_name == 'push'":
        fail("publish job must be push-only")
    if verify_job.get("if") != "github.event_name == 'push'":
        fail("verify-published job must be push-only")
    if deploy_job.get("if") != "github.event_name == 'push' && vars.SOLO_VPS_DEPLOY_ENABLED == 'true'":
        fail("deploy job must be push-only and explicitly enabled after the initial image")
    if verify_job.get("needs") != ["publish"]:
        fail("verify-published job must depend only on publish")
    if deploy_job.get("needs") != ["publish", "verify-published"]:
        fail("deploy job must wait for both publish and verify-published")

    publish_permissions = as_mapping(publish_job.get("permissions"), "jobs.publish.permissions")
    if publish_permissions != {"contents": "read", "packages": "write"}:
        fail("publish job permissions must be exactly contents: read + packages: write")

    verify_permissions = as_mapping(verify_job.get("permissions"), "jobs.verify-published.permissions")
    if verify_permissions != {"contents": "read", "packages": "read"}:
        fail("verify-published permissions must be exactly contents: read + packages: read")

    deploy_permissions = as_mapping(deploy_job.get("permissions"), "jobs.deploy.permissions")
    if deploy_permissions != {"contents": "read"}:
        fail("deploy job permissions must be exactly contents: read")
    if deploy_job.get("environment") != "production":
        fail("deploy job must use the GitHub production environment")
    deploy_concurrency = as_mapping(deploy_job.get("concurrency"), "jobs.deploy.concurrency")
    if deploy_concurrency != {"group": "solo-vps-production", "cancel-in-progress": "false"}:
        fail("deploy job must serialize production deployments without cancelling an in-progress deployment")

    deploy_env = as_mapping(deploy_job.get("env"), "jobs.deploy.env")
    expected_deploy_env = {
        "IMAGE_REF": "${{ needs.publish.outputs.image_ref }}",
        "SOLO_VPS_DEPLOY_HOST": "${{ vars.SOLO_VPS_DEPLOY_HOST }}",
        "SOLO_VPS_SSH_KNOWN_HOSTS": "${{ vars.SOLO_VPS_SSH_KNOWN_HOSTS }}",
        "SOLO_VPS_DEPLOY_SSH_FINGERPRINT": "${{ vars.SOLO_VPS_DEPLOY_SSH_FINGERPRINT }}",
        "COOLIFY_RESOURCE_UUID": "${{ vars.COOLIFY_RESOURCE_UUID }}",
    }
    if deploy_env != expected_deploy_env:
        fail("deploy job must consume only the reviewed production environment variables and publish.image_ref")

    outputs = as_mapping(publish_job.get("outputs"), "jobs.publish.outputs")
    if set(outputs) != {"digest", "image_ref"}:
        fail("publish job must expose digest and image_ref outputs")

    test_steps = as_list(test_job.get("steps"), "jobs.test.steps")
    test_runs = [scalar(as_mapping(step, "test step").get("run")) for step in test_steps]
    if not any("python3 -m unittest discover" in command and "${APP_DIR}" in command for command in test_runs):
        fail("test job must run the sample application unittest suite")
    if not any("python3 -m unittest discover -s tests -p 'test_*.py'" in command for command in test_runs):
        fail("test job must run the deployment helper contract suite")

    migration_steps = [
        as_mapping(step, "migration-preflight step")
        for step in as_list(migration_job.get("steps"), "jobs.migration-preflight.steps")
    ]
    migration_runs = [step for step in migration_steps if step.get("run") is not None]
    if len(migration_runs) != 1:
        fail("migration-preflight must contain exactly one application-owned run step")
    if scalar(migration_runs[0].get("name")) != "Run application-owned migration preflight":
        fail("migration-preflight run step must remain explicitly application-owned")
    if scalar(migration_runs[0].get("run")) != 'python3 "${APP_DIR}/migration_preflight.py"':
        fail("migration-preflight must execute the application-owned migration_preflight.py hook")
    if migration_runs[0].get("env") is not None:
        fail("migration-preflight hook must not receive workflow secrets or production credentials")

    build_steps = [as_mapping(step, "build step") for step in as_list(build_job.get("steps"), "jobs.build.steps")]
    publish_steps = [as_mapping(step, "publish step") for step in as_list(publish_job.get("steps"), "jobs.publish.steps")]
    verify_steps = [as_mapping(step, "verify step") for step in as_list(verify_job.get("steps"), "jobs.verify-published.steps")]
    deploy_steps = [as_mapping(step, "deploy step") for step in as_list(deploy_job.get("steps"), "jobs.deploy.steps")]

    if any(scalar(step.get("uses")).startswith("docker/login-action@") for step in build_steps):
        fail("pull-request build must not authenticate to a registry")

    pr_build = find_action(build_steps, "docker/build-push-action@")
    pr_build_with = as_mapping(pr_build.get("with"), "pull request build.with")
    if pr_build_with.get("pull") != "true":
        fail("pull-request build must use pull: true for fresh base-image resolution")
    if pr_build_with.get("push") != "false":
        fail("pull-request build must use push: false")

    publish_build = find_action(publish_steps, "docker/build-push-action@")
    publish_build_with = as_mapping(publish_build.get("with"), "publish build.with")
    if publish_build_with.get("pull") != "true":
        fail("publish build must use pull: true for fresh base-image resolution")
    if publish_build_with.get("push") != "true":
        fail("publish build must use push: true")

    for label, with_map in (("build", pr_build_with), ("publish", publish_build_with)):
        if with_map.get("context") != "${{ env.APP_DIR }}":
            fail(f"{label} context must use APP_DIR")
        if with_map.get("file") != "${{ env.APP_DIR }}/Dockerfile":
            fail(f"{label} Dockerfile must use APP_DIR/Dockerfile")

    login = find_action(publish_steps, "docker/login-action@")
    login_with = as_mapping(login.get("with"), "login.with")
    expected_login = {
        "registry": "${{ env.REGISTRY }}",
        "username": "${{ github.actor }}",
        "password": "${{ secrets.GITHUB_TOKEN }}",
    }
    if login_with != expected_login:
        fail("GHCR login must use registry/github.actor/GITHUB_TOKEN only")

    verify_login = find_action(verify_steps, "docker/login-action@")
    verify_login_with = as_mapping(verify_login.get("with"), "verify login.with")
    if verify_login_with != expected_login:
        fail("GHCR verify login must use registry/github.actor/GITHUB_TOKEN only")

    metadata_steps = [
        step
        for step in build_steps + publish_steps
        if scalar(step.get("uses")).startswith("docker/metadata-action@")
    ]
    if len(metadata_steps) != 2:
        fail("both build and publish jobs need deterministic metadata")
    for metadata in metadata_steps:
        metadata_with = as_mapping(metadata.get("with"), "metadata.with")
        if metadata_with.get("images") != "${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}":
            fail("metadata image name must use REGISTRY/IMAGE_NAME")
        if scalar(metadata_with.get("tags")).strip() != "type=sha,format=long":
            fail("image tag contract must be full commit SHA only")

    validate_actions(jobs)

    if "${{ steps.build.outputs.digest }}" not in text:
        fail("workflow must consume the build-push digest output")
    if "@${IMAGE_DIGEST}" not in text:
        fail("workflow must export name@digest immutable identity")
    if "^sha256:[0-9a-f]{64}$" not in text:
        fail("workflow must validate the registry digest format before exporting it")
    if text.count("persist-credentials: false") != 5:
        fail("every checkout must disable persisted credentials")

    verify_runs = [scalar(step.get("run")) for step in verify_steps if step.get("run") is not None]
    verify_text = "\n".join(verify_runs)
    pull_steps = [step for step in verify_steps if 'docker pull "${IMAGE_REF}"' in scalar(step.get("run"))]
    smoke_steps = [step for step in verify_steps if "--publish 127.0.0.1:18080:8080" in scalar(step.get("run"))]
    if len(pull_steps) != 1:
        fail("verify-published must contain exactly one immutable docker pull step")
    if len(smoke_steps) != 1:
        fail("verify-published must contain exactly one loopback smoke-test step")
    expected_image_env = {"IMAGE_REF": "${{ needs.publish.outputs.image_ref }}"}
    if as_mapping(pull_steps[0].get("env"), "verify pull.env") != expected_image_env:
        fail("verify-published pull must consume publish.image_ref")
    if as_mapping(smoke_steps[0].get("env"), "verify smoke.env") != expected_image_env:
        fail("verify-published smoke test must consume publish.image_ref")
    if "--pull never" not in verify_text:
        fail("verify-published smoke test must run the already-pulled immutable image without another pull")
    if "http://127.0.0.1:18080/healthz" not in verify_text:
        fail("verify-published must exercise the fixture health endpoint")
    if '{"status":"ok"}' not in verify_text:
        fail("verify-published must assert the exact hello-app health JSON")

    deploy_checkouts = [step for step in deploy_steps if scalar(step.get("uses")).startswith("actions/checkout@")]
    deploy_runs = [step for step in deploy_steps if step.get("run") is not None]
    if len(deploy_checkouts) != 1 or len(deploy_runs) != 1:
        fail("deploy job must contain exactly one checkout and one reviewed deployment shell step")
    checkout_with = as_mapping(deploy_checkouts[0].get("with"), "deploy checkout.with")
    if checkout_with != {"persist-credentials": "false"}:
        fail("deploy checkout must not persist repository credentials")

    deploy_step = deploy_runs[0]
    if deploy_step.get("shell") != "bash":
        fail("deploy step must use bash")
    deploy_secret_env = as_mapping(deploy_step.get("env"), "deploy run.env")
    expected_secret_env = {
        "GITHUB_TOKEN": "${{ github.token }}",
        "SOLO_VPS_DEPLOY_SSH_KEY": "${{ secrets.SOLO_VPS_DEPLOY_SSH_KEY }}",
        "COOLIFY_API_TOKEN": "${{ secrets.COOLIFY_API_TOKEN }}",
        "COOLIFY_API_DEPLOY_CONFIRM": "I_HAVE_REVIEWED_THE_LOOPBACK_COOLIFY_API_DEPLOYMENT",
    }
    if deploy_secret_env != expected_secret_env:
        fail("deploy secrets must be scoped only to the deployment step with explicit API mutation confirmation")

    deploy_text = scalar(deploy_step.get("run"))
    required_fragments = (
        'trap cleanup EXIT',
        'rm -f "${key_path}" "${public_key_path}" "${known_hosts_path}"',
        'ssh-keygen -y -P \'\' -f "${key_path}"',
        '[[ "${actual_fingerprint}" == "${SOLO_VPS_DEPLOY_SSH_FINGERPRINT}" ]]',
        'SOLO_VPS_SSH_KNOWN_HOSTS',
        'ssh -F /dev/null -N -T',
        '-o BatchMode=yes',
        '-o PreferredAuthentications=publickey',
        '-o PasswordAuthentication=no',
        '-o KbdInteractiveAuthentication=no',
        '-o IdentitiesOnly=yes',
        '-o UserKnownHostsFile="${known_hosts_path}"',
        '-o GlobalKnownHostsFile=/dev/null',
        '-o StrictHostKeyChecking=yes',
        '-o HostKeyAlgorithms=ssh-ed25519',
        '-o ExitOnForwardFailure=yes',
        '-o ForwardAgent=no',
        '-L 127.0.0.1:18000:127.0.0.1:8000',
        '"solo-vps-ci@${SOLO_VPS_DEPLOY_HOST}"',
        'http://127.0.0.1:18000/api/health',
        'python3 scripts/coolify_deploy_api.py',
        '--base-url http://127.0.0.1:18000/api/v1',
        '--resource-uuid "${COOLIFY_RESOURCE_UUID}"',
        '--image-ref "${IMAGE_REF}"',
        '--check',
        '--apply',
    )
    for fragment in required_fragments:
        if fragment not in deploy_text:
            fail(f"deploy job is missing required restricted transport/API fragment: {fragment}")
    if deploy_text.count("--base-url http://127.0.0.1:18000/api/v1") != 2:
        fail("deploy job must use the fixed runner-local Coolify API endpoint for both check and apply")
    if deploy_text.index("--check") > deploy_text.index("--apply"):
        fail("deploy job must perform read-only Coolify API check before mutation")
    if deploy_text.count("--allow-domain") != 2:
        fail("both check and apply must accept the application's public domain")
    if "python3 scripts/check_release_revision.py || revision_status=$?" not in deploy_text:
        fail("deployment must verify the current main revision before mutating the VPS")
    if deploy_text.index("scripts/check_release_revision.py") > deploy_text.index('printf \'%s\\n\' "${SOLO_VPS_DEPLOY_SSH_KEY}"'):
        fail("release revision must be checked before creating deployment credentials")
    if "-R " in deploy_text or "127.0.0.1:6001" in deploy_text or "127.0.0.1:6002" in deploy_text:
        fail("deploy job must not request remote forwarding or unapproved Coolify realtime destinations")
    if text.count("${{ secrets.COOLIFY_API_TOKEN }}") != 1:
        fail("COOLIFY_API_TOKEN must be referenced exactly once and only in the deploy step")
    if text.count("${{ secrets.SOLO_VPS_DEPLOY_SSH_KEY }}") != 1:
        fail("SOLO_VPS_DEPLOY_SSH_KEY must be referenced exactly once and only in the deploy step")
    if "${{ needs.publish.outputs.image_ref }}" not in scalar(deploy_env.get("IMAGE_REF")):
        fail("deploy job must consume the exact immutable image_ref emitted by publish")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workflow", type=Path)
    args = parser.parse_args()

    try:
        validate(args.workflow)
    except (OSError, ValueError) as exc:
        print(f"ERROR CI template contract: {exc}", file=sys.stderr)
        return 2

    print(f"PASS CI template contract: {args.workflow}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
