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

    manifest = yaml.safe_load(read(root / "ansible/roles/coolify/defaults/main.yml"))
    current = manifest["solo_vps_coolify_version"]
    previous = manifest["solo_vps_coolify_previous_supported_version"]
    require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", current) is not None, "exact target release required")
    require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", previous) is not None and previous != current, "exact distinct origin release required")
    coolify = policy.get("coolify", {})
    require(coolify.get("current_supported") == current, "current supported Coolify must match the promoted pin")
    require(coolify.get("previous_supported") == previous, "previous supported Coolify must be explicit")
    upgrade = coolify.get("supported_upgrade", {})
    require(upgrade.get("from") == previous and upgrade.get("to") == current, "exact previous -> current Coolify path missing")
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
    require(manifest["solo_vps_coolify_previous_supported_version"] == previous, "Coolify previous supported version missing")
    require(manifest["solo_vps_coolify_version"] == current, "Coolify promoted version missing")
    require('solo_vps_coolify_expected_image: "docker.io/coollabsio/coolify:' in coolify_defaults, "Coolify promoted image registry missing")
    require('/data/coolify/images' in coolify_defaults, "Coolify promoted image storage missing")
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
        "Remove the Coolify upgrade transaction marker after full verification",
    ):
        require(token in apply, f"Coolify upgrade apply flow missing: {token}")
    require("curl -fsSL" not in apply and "install.sh" not in apply, "project-owned upgrade must not call the upstream installer")
    require(apply.index("Verify the current supported Coolify installation") < apply.index("Remove the Coolify upgrade transaction marker after full verification"), "full verification must precede transaction marker removal")
    require("previous_supported" in resume and "current_supported" in resume, "upgrade resume must bind the same exact version pair")
    require("automatic downgrade" in resume.lower(), "upgrade resume must reject automatic downgrade semantics")
    require(resume.index("Run full current supported Coolify verification") < resume.index("Remove the interrupted Coolify upgrade marker only after full verification"), "resume must retain transaction marker until full verification")
    require("verify-sentinel.yml" in preflight, "supported upgrade must verify Sentinel before mutation")
    require("--require-existing --reverb --check" in preflight, "custom realtime configuration must be rejected before mutation")
    require("release_identity={{ solo_vps_coolify_release_identity }}" in apply, "transaction must bind reviewed artifacts and port override")
    require("'release_identity=' ~ solo_vps_coolify_release_identity" in resume, "resume must enforce the same reviewed artifacts and override")
    marker_checks = [condition for task in yaml.safe_load(resume)
                     for condition in task.get("ansible.builtin.assert", {}).get("that", [])
                     if isinstance(condition, str) and "solo_vps_coolify_upgrade_resume_marker_raw" in condition]
    require(bool(marker_checks) and all(".splitlines()" in condition for condition in marker_checks),
            "resume must compare every exact marker line, not version substrings")
    supported_sentinel = read(root / "ansible/roles/coolify/tasks/verify-sentinel.yml")
    for token in ("--expected-image", "--expected-version", "port: 8888"):
        require(token in supported_sentinel, f"supported Sentinel boundary missing: {token}")
    require("ansible_facts.architecture == 'x86_64'" in supported_sentinel, "x86_64 Sentinel content pin must not be imposed on aarch64")

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

    candidate_path = root / "ansible/playbooks/coolify-evaluation-vars.yml"
    candidate = yaml.safe_load(read(candidate_path))
    require(isinstance(candidate, dict), "Coolify evaluation candidate vars must be a mapping")
    require(candidate.get("solo_vps_coolify_evaluation_candidate") is True, "Coolify candidate must stay explicitly evaluation-only")
    require("solo_vps_coolify_version" not in candidate, "candidate must share the release manifest instead of copying pins")
    artifacts = manifest.get("solo_vps_coolify_release_artifacts", [])
    require({item.get("name") for item in artifacts} == {"docker-compose.yml", "docker-compose.prod.yml", ".env.production"}, "complete target artifact set required")
    require(all(re.fullmatch(r"sha256:[0-9a-f]{64}", item.get("checksum", "")) for item in artifacts), "committed SHA256 artifacts required")

    candidate_preflight = read(root / "ansible/roles/coolify/tasks/evaluation-preflight.yml")
    sentinel_tasks = read(root / "ansible/roles/coolify/tasks/evaluate-sentinel.yml")
    sentinel_inspector = read(root / "scripts/inspect_coolify_sentinel.py")
    for token in (
        "REGISTRY_URL=docker.io",
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
        "coolify-evaluate-preflight.yml",
        "coolify-evaluate-upgrade.yml",
        "coolify-evaluate-resume.yml",
        "verify-coolify-candidate.yml",
    )
    for playbook in candidate_playbooks:
        require(playbook in syntax_block, f"real pinned QA syntax target must include candidate playbook: {playbook}")
        require((root / "ansible/playbooks" / playbook).is_file(), f"candidate playbook missing: {playbook}")
    for target in (
        "coolify-evaluation-init",
        "coolify-evaluate-preflight",
        "coolify-evaluate-upgrade",
        "coolify-evaluate-resume",
        "verify-coolify-candidate",
    ):
        require(re.search(rf"(?m)^{re.escape(target)}:", makefile) is not None, f"Makefile candidate target missing: {target}")
    for token in (
        "COOLIFY_EVALUATION_DATA_DIR",
        "SOLO_VPS_DEFAULT_DATA_DIR",
        ".coolify-disposable-evaluation",
        "evaluation refuses the normal Solo VPS data directory",
        "SOLO_VPS_DATA_DIR must equal COOLIFY_EVALUATION_DATA_DIR",
    ):
        require(token in makefile, f"candidate controller-state isolation missing: {token}")
    require("EXPECTED EVALUATION INTERRUPTION" in apply, "candidate must exercise deterministic interrupted-upgrade recovery")
    require("solo_vps_coolify_evaluation_candidate" in apply, "fault injection must stay restricted to the evaluation profile")

    docs = read(root / "docs/upgrades.md")
    for phrase in (
        "Docker 29.x",
        "Docker 30",
        f"previous supported Coolify: `{previous}`",
        f"current supported Coolify: `{current}`",
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
        "reviewed Coolify lifecycle and Sentinel boundary are explicit"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
