#!/usr/bin/env python3
"""Validate the CRIT-011 Docker/Coolify lifecycle source contract."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


class ContractError(ValueError):
    pass


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def validate(root: Path) -> None:
    policy_path = root / "docs/contracts/platform-lifecycle-policy.yml"
    policy = yaml.safe_load(read(policy_path))
    require(isinstance(policy, dict), "platform lifecycle policy must be a mapping")

    docker = policy.get("docker", {})
    require(docker.get("supported_major_versions") == [29], "alpha Docker support window must be major 29 only")
    require(docker.get("version_floor_inclusive") == "29.0.0", "Docker floor must be 29.0.0")
    require(docker.get("version_ceiling_exclusive") == "30.0.0", "Docker ceiling must fail closed before major 30")
    require(docker.get("fresh_install_candidate_policy") == "fail-closed-before-package-install", "fresh Docker candidate policy must fail closed")
    require(docker.get("automatic_major_upgrade") is False, "automatic Docker major upgrades must stay disabled")

    coolify = policy.get("coolify", {})
    require(coolify.get("current_supported") == "4.1.2", "current supported Coolify must match the pinned M9 version")
    require(coolify.get("previous_supported") == "4.1.1", "previous supported Coolify must be explicit")
    upgrade = coolify.get("supported_upgrade", {})
    require(upgrade.get("from") == "4.1.1" and upgrade.get("to") == "4.1.2", "exact previous -> current Coolify path missing")
    for key in (
        "exact_target_artifacts",
        "require_local_control_plane_checkpoint",
        "require_m7_docker_ownership",
        "require_loopback_management_ports",
    ):
        require(upgrade.get(key) is True, f"Coolify upgrade safety requirement must stay enabled: {key}")
    require(upgrade.get("automatic_downgrade_on_failure") is False, "automatic Coolify downgrade must remain disabled")
    require(upgrade.get("failure_recovery") == "explicit-forward-resume-or-m16-restore", "Coolify failure recovery boundary drifted")

    docker_defaults_text = read(root / "ansible/roles/docker/defaults/main.yml")
    docker_defaults = yaml.safe_load(docker_defaults_text)
    require(isinstance(docker_defaults, dict), "Docker defaults must be a mapping")
    require(docker_defaults.get("solo_vps_docker_supported_major_versions") == [29], "Docker runtime support window must be exactly [29]")
    require(docker_defaults.get("solo_vps_docker_minimum_major_version") == 29, "Docker minimum major must be 29")
    require(docker_defaults.get("solo_vps_docker_maximum_major_version") == 29, "Docker maximum major must be 29")
    docker_main = read(root / "ansible/roles/docker/tasks/main.yml")
    docker_verify = read(root / "ansible/roles/docker/tasks/verify.yml")
    for token in (
        "Derive the Docker CE candidate major version",
        "Refuse an untested Docker major before first installation",
        "solo_vps_docker_ce_candidate_major in solo_vps_docker_supported_major_versions",
    ):
        require(token in docker_main, f"fresh Docker candidate fail-closed gate missing: {token}")
    require(
        "solo_vps_docker_server_major in solo_vps_docker_supported_major_versions" in docker_verify,
        "installed Docker verification must enforce the same supported major window",
    )

    coolify_defaults = read(root / "ansible/roles/coolify/defaults/main.yml")
    require('solo_vps_coolify_previous_supported_version: "4.1.1"' in coolify_defaults, "Coolify previous supported version missing")
    require('solo_vps_coolify_version: "4.1.2"' in coolify_defaults, "Coolify current supported version must not follow an unproven candidate")
    require('solo_vps_coolify_upgrade_pending_marker: /data/coolify/.solo-vps-upgrading' in coolify_defaults, "Coolify upgrade transaction marker missing")
    require("solo_vps_coolify_supported_docker_majors:\n  - 29" in coolify_defaults, "Coolify readiness must inherit the Docker 29 support boundary")

    preflight = read(root / "ansible/roles/coolify/tasks/upgrade-preflight.yml")
    apply = read(root / "ansible/roles/coolify/tasks/upgrade.yml")
    resume = read(root / "ansible/roles/coolify/tasks/upgrade-resume.yml")
    for token in (
        "previous_supported",
        "current_supported",
        "AUTOUPDATE=false",
        "solo_vps_coolify_expected_docker_config",
        "solo_vps_coolify_upgrade_pending_marker",
    ):
        require(token in preflight, f"Coolify upgrade preflight missing safety boundary: {token}")
    for token in (
        "Record the Coolify upgrade transaction before mutation",
        "Download exact target Coolify release artifacts into the upgrade staging directory",
        "Validate the staged target Compose model without exposing secrets",
        "Promote the verified target Coolify release artifacts",
        "Pin the target Coolify image and keep automatic upgrades disabled",
        "Verify the upgraded Coolify runtime before committing the version marker",
        "Remove the Coolify upgrade transaction marker after successful verification",
    ):
        require(token in apply, f"Coolify upgrade apply flow missing: {token}")
    require("curl -fsSL" not in apply and "install.sh" not in apply, "project-owned upgrade must not call the upstream installer")
    require("previous_supported" in resume and "current_supported" in resume, "upgrade resume must bind the same exact version pair")
    require("automatic downgrade" in resume.lower(), "upgrade resume must reject automatic downgrade semantics")

    makefile = read(root / "Makefile")
    for target in (
        "validate-platform-lifecycle",
        "test-platform-lifecycle",
        "platform-lifecycle-plan",
        "coolify-upgrade-preflight",
        "coolify-upgrade",
        "coolify-upgrade-resume",
    ):
        require(re.search(rf"(?m)^{re.escape(target)}:", makefile) is not None, f"Makefile lifecycle target missing: {target}")
    upgrade_recipe = makefile.split("coolify-upgrade:", 1)[1].split("\ncoolify-upgrade-resume:", 1)[0]
    require("backup-check" not in upgrade_recipe, "core upgrade must not require off-site storage")
    require("coolify_upgrade_checkpoint.py" in apply, "upgrade requires a local checkpoint")
    require(apply.index("coolify_upgrade_checkpoint.py") < apply.index("Record the Coolify upgrade transaction"), "checkpoint must precede upgrade mutation")

    syntax_block = makefile.split("ansible-syntax:", 1)[1].split("\n\n", 1)[0]
    for playbook in (
        "coolify-upgrade-preflight.yml",
        "coolify-upgrade.yml",
        "coolify-upgrade-resume.yml",
    ):
        require(playbook in syntax_block, f"real pinned QA syntax target must include lifecycle playbook: {playbook}")

    candidate_path = root / "ansible/playbooks/coolify-4.3.21-evaluation-vars.yml"
    candidate = yaml.safe_load(read(candidate_path))
    require(isinstance(candidate, dict), "Coolify evaluation candidate vars must be a mapping")
    require(candidate.get("solo_vps_coolify_evaluation_candidate") is True, "Coolify candidate must stay explicitly evaluation-only")
    require(candidate.get("solo_vps_coolify_previous_supported_version") == "4.1.2", "Coolify candidate must start at the current supported release")
    require(candidate.get("solo_vps_coolify_version") == "4.3.21", "reviewed disposable Coolify candidate drifted")
    require(candidate.get("solo_vps_coolify_expected_image") == "ghcr.io/coollabsio/coolify:4.3.21", "candidate Coolify image drifted")
    require(candidate.get("solo_vps_coolify_evaluation_sentinel_version") == "1.0.1", "candidate Sentinel version drifted")
    require(candidate.get("solo_vps_coolify_evaluation_sentinel_image") == "ghcr.io/coollabsio/sentinel:1.0.1", "candidate Sentinel image drifted")
    expected_hashes = {
        "docker-compose.yml": "sha256:0223699dfef8a421116872b050830b21cfedfc58911576a0129c2082aeaadc59",
        "docker-compose.prod.yml": "sha256:77f4723dfac49deeec550b412e366bde70a329ff8c66ceb44d5d10b146a24124",
        ".env.production": "sha256:4a8070a010ac5c919f05919d36a67065f87e8b514a52c38b381f1b1cd7fcbe5c",
    }
    artifacts = candidate.get("solo_vps_coolify_release_artifacts", [])
    require(
        {item.get("name"): item.get("checksum") for item in artifacts} == expected_hashes,
        "candidate release artifact set or SHA-256 drifted",
    )

    candidate_preflight = read(root / "ansible/roles/coolify/tasks/evaluation-preflight.yml")
    sentinel_tasks = read(root / "ansible/roles/coolify/tasks/evaluate-sentinel.yml")
    sentinel_inspector = read(root / "scripts/inspect_coolify_sentinel.py")
    for token in (
        "REGISTRY_URL=ghcr.io",
        "Verify working Sentinel HTTPS communication before upgrade mutation",
    ):
        require(token in candidate_preflight, f"candidate preflight missing boundary: {token}")
    for token in (
        "--expected-push-endpoint",
        "Prove Sentinel does not publish its API to the controller",
        "port: 8888",
    ):
        require(token in sentinel_tasks, f"candidate Sentinel task missing boundary: {token}")
    for token in (
        'host_config.get("PidMode") == "host"',
        'socket_mount.get("RW") is True',
        '"host_ports_published": False',
        '"secrets_printed": False',
    ):
        require(token in sentinel_inspector, f"secret-safe Sentinel inspector missing boundary: {token}")

    candidate_playbooks = (
        "coolify-evaluate-4-3-21-preflight.yml",
        "coolify-evaluate-4-3-21-upgrade.yml",
        "coolify-evaluate-4-3-21-resume.yml",
        "verify-coolify-4-3-21-candidate.yml",
    )
    for playbook in candidate_playbooks:
        require(playbook in syntax_block, f"real pinned QA syntax target must include candidate playbook: {playbook}")
        require((root / "ansible/playbooks" / playbook).is_file(), f"candidate playbook missing: {playbook}")
    for target in (
        "coolify-evaluation-init",
        "coolify-evaluate-4-3-21-preflight",
        "coolify-evaluate-4-3-21-upgrade",
        "coolify-evaluate-4-3-21-resume",
        "verify-coolify-4-3-21-candidate",
    ):
        require(re.search(rf"(?m)^{re.escape(target)}:", makefile) is not None, f"Makefile candidate target missing: {target}")
    for token in (
        "COOLIFY_EVALUATION_DATA_DIR",
        "SOLO_VPS_DEFAULT_DATA_DIR",
        ".coolify-4.3.21-disposable-evaluation",
        "evaluation refuses the normal Solo VPS data directory",
        "SOLO_VPS_DATA_DIR must equal COOLIFY_EVALUATION_DATA_DIR",
    ):
        require(token in makefile, f"candidate controller-state isolation missing: {token}")
    require("EXPECTED EVALUATION INTERRUPTION" in apply, "candidate must exercise deterministic interrupted-upgrade recovery")
    require("solo_vps_coolify_evaluation_candidate" in apply, "fault injection must stay restricted to the evaluation profile")

    exercise = read(root / "docs/coolify-4.3.21-evaluation.md")
    for phrase in (
        "Не запускайте команды обновления на основном сервере",
        "make coolify-evaluation-init",
        'export SOLO_VPS_DATA_DIR="$COOLIFY_EVALUATION_DATA_DIR"',
        "Sentinel In Sync",
        "COOLIFY_EVALUATION_INTERRUPT_AFTER_MARKER=true",
        "make coolify-evaluate-4-3-21-resume",
        "удалите disposable VPS",
    ):
        require(phrase in exercise, f"candidate exercise sheet missing safety step: {phrase!r}")

    docs = read(root / "docs/upgrades.md")
    for phrase in (
        "Docker 29.x",
        "Docker 30",
        "previous supported Coolify: `4.1.1`",
        "current supported Coolify: `4.1.2`",
        "make coolify-upgrade-preflight",
        "make coolify-upgrade",
        "make coolify-upgrade-resume",
        "does not automatically downgrade Coolify",
        "database migrations",
    ):
        require(phrase in docs, f"upgrade guide missing CRIT-011 lifecycle statement: {phrase!r}")

    release = read(root / "docs/release-process.md")
    require("CRIT-011 Coolify lifecycle evidence" in release, "release process must gate on real Coolify lifecycle evidence")
    require("previous-supported" in release and "current-supported" in release, "release process must require previous -> current upgrade proof")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    try:
        validate(root)
    except (OSError, yaml.YAMLError, ContractError) as exc:
        print(f"ERROR platform lifecycle contract: {exc}", file=sys.stderr)
        return 2
    print(
        "PASS platform lifecycle contract: Docker 29.x fail-closed window, "
        "supported Coolify 4.1.1 -> 4.1.2 lifecycle, and isolated 4.3.21/Sentinel "
        "disposable evaluation are explicit"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
