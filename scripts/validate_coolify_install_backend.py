#!/usr/bin/env python3
"""Validate the source-only M9 pinned Coolify installation backend safety contract."""

from __future__ import annotations

import argparse
from pathlib import Path


class ContractError(ValueError):
    pass


def read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise ContractError(f"required M9 file is missing: {relative}")
    return path.read_text(encoding="utf-8")


def require(text: str, phrase: str, label: str) -> None:
    if phrase not in text:
        raise ContractError(f"{label} missing required safety phrase: {phrase!r}")


def reject(text: str, phrase: str, label: str) -> None:
    if phrase in text:
        raise ContractError(f"{label} contains forbidden installation path: {phrase!r}")


def validate(root: Path) -> list[str]:
    defaults = read(root, "ansible/roles/coolify/defaults/main.yml")
    install = read(root, "ansible/roles/coolify/tasks/install.yml")
    reconcile_access = read(root, "ansible/roles/coolify/tasks/reconcile-runtime-access.yml")
    verify = read(root, "ansible/roles/coolify/tasks/verify.yml")
    runtime = read(root, "ansible/roles/coolify/tasks/verify-runtime.yml")
    recover = read(root, "ansible/roles/coolify/tasks/recover.yml")
    playbook = read(root, "ansible/playbooks/coolify.yml")
    recover_playbook = read(root, "ansible/playbooks/recover-coolify.yml")
    verify_playbook = read(root, "ansible/playbooks/verify-coolify.yml")
    makefile = read(root, "Makefile")

    for label, text in (("defaults", defaults), ("install", install), ("playbook", playbook)):
        for forbidden in ("cdn.coollabs.io/coolify/install.sh", "get.coollabs.io/coolify/install.sh", "curl -fsSL"):
            reject(text, forbidden, label)

    for phrase in (
        "solo_vps_coolify_data_parent: /data",
        "solo_vps_coolify_managed_marker: /data/coolify/.solo-vps-managed",
        "solo_vps_coolify_pending_marker: /data/coolify/.solo-vps-installing",
        "id.{{ admin.user }}@host.docker.internal",
        "solo_vps_coolify_expected_image: \"ghcr.io/coollabsio/coolify:{{ solo_vps_coolify_image_tag }}\"",
        'solo_vps_coolify_non_root_parent_mode: "0711"',
        'solo_vps_coolify_non_root_data_root_mode: "0710"',
        'solo_vps_coolify_non_root_resource_root_mode: "0710"',
        'solo_vps_coolify_non_root_backup_root_mode: "0730"',
        'solo_vps_coolify_non_root_resource_roots:',
        '- /data/coolify/applications',
        '- /data/coolify/databases',
        '- /data/coolify/services',
        'solo_vps_coolify_non_root_proxy_mode: "0700"',
    ):
        require(defaults, phrase, "defaults")

    resource_roots_block = defaults.split("solo_vps_coolify_non_root_resource_roots:", 1)[1].split(
        "solo_vps_coolify_non_root_proxy_mode:", 1
    )[0]
    expected_resource_roots = {
        "/data/coolify/applications",
        "/data/coolify/databases",
        "/data/coolify/services",
    }
    actual_resource_roots = {
        line.strip()[2:].strip()
        for line in resource_roots_block.splitlines()
        if line.strip().startswith("- ")
    }
    if actual_resource_roots != expected_resource_roots:
        raise ContractError(
            "non-root Coolify resource roots must be exactly applications/databases/services; "
            "do not broaden the exception to source/ssh/backups or omit a lifecycle namespace"
        )

    require(
        install,
        'path: "{{ solo_vps_coolify_data_parent }}"\n    state: directory\n    owner: root\n    group: root\n    mode: "{{ solo_vps_coolify_non_root_parent_mode }}"',
        "explicit root-owned /data parent contract",
    )

    for phrase in (
        "Prepare Coolify resource namespace roots for non-root lifecycle control",
        'loop: "{{ solo_vps_coolify_non_root_resource_roots }}"',
        'mode: "{{ solo_vps_coolify_non_root_resource_root_mode }}"',
        'group: "{{ solo_vps_coolify_admin_gid }}"',
    ):
        require(install, phrase, "first-install resource namespace access")

    for phrase in (
        "ansible.builtin.get_url",
        'checksum: "{{ item.checksum }}"',
        "LATEST_IMAGE",
        "AUTOUPDATE",
        "ansible.builtin.command",
        "solo_vps_coolify_ssh_keygen_binary",
        "ansible.builtin.lineinfile",
        "authorized_keys",
        "state: absent",
        "network, create, --attachable, coolify",
        "docker-compose.prod.yml",
        "solo_vps_coolify_compose_override_filename",
        "--force-recreate",
        "ansible.builtin.import_tasks: verify-runtime.yml",
        "solo_vps_coolify_pending_marker",
        "state=installing",
        "solo_vps_coolify_managed_marker",
        "Create the host-owned Coolify data parent explicitly",
        'path: "{{ solo_vps_coolify_data_parent }}"',
        'owner: root',
        'mode: "{{ solo_vps_coolify_non_root_parent_mode }}"',
    ):
        require(install, phrase, "install backend")


    require(
        reconcile_access,
        'path: "{{ solo_vps_coolify_data_parent }}"\n    state: directory\n    owner: root\n    group: root\n    mode: "{{ solo_vps_coolify_non_root_parent_mode }}"',
        "managed root-owned /data parent reconciliation",
    )

    for phrase in (
        'database: passwd',
        'key: "{{ admin.user }}"',
        'path: "{{ solo_vps_coolify_data_parent }}"',
        'owner: root',
        'mode: "{{ solo_vps_coolify_non_root_parent_mode }}"',
        'path: "{{ solo_vps_coolify_data_root }}"',
        'owner: "9999"',
        'mode: "{{ solo_vps_coolify_non_root_data_root_mode }}"',
        'loop: "{{ solo_vps_coolify_non_root_resource_roots }}"',
        'mode: "{{ solo_vps_coolify_non_root_resource_root_mode }}"',
        'path: "{{ solo_vps_coolify_data_root }}/backups"',
        'mode: "{{ solo_vps_coolify_non_root_backup_root_mode }}"',
        'path: "{{ solo_vps_coolify_data_root }}/proxy"',
        'owner: "{{ admin.user }}"',
        'mode: "{{ solo_vps_coolify_non_root_proxy_mode }}"',
        'group: "{{ solo_vps_coolify_admin_gid }}"',
    ):
        require(reconcile_access, phrase, "non-root Coolify runtime access reconciler")

    for phrase in (
        'Inspect the private Coolify backup root',
        'solo_vps_coolify_backup_root_state.stat.uid == 9999',
        'solo_vps_coolify_backup_root_state.stat.gid == solo_vps_coolify_verify_admin_gid',
        'solo_vps_coolify_backup_root_state.stat.mode == solo_vps_coolify_non_root_backup_root_mode',
        'Prove admin.user can write and traverse but cannot list the Coolify backup root',
        'flag: -w',
        'flag: -x',
        'flag: -r',
        'register: solo_vps_coolify_backup_root_access_probes',
    ):
        require(verify, phrase, "non-root Coolify backup-root verifier")

    # Generated secrets and merged Compose validation must not be emitted into Ansible logs.
    import yaml
    sensitive = {"solo_vps_coolify_env_init", "solo_vps_coolify_localhost_public_key"}
    for task in yaml.safe_load(install):
        if task.get("register") in sensitive and task.get("no_log") is not True:
            raise ContractError("install backend must suppress generated secret/key output")
    require(install, "initialize_coolify_env.py", "atomic environment initialization")
    require(install, "--require-existing", "configured identity preservation")
    require(install, "config\n      - --quiet", "install backend")

    marker_pos = install.rfind("solo_vps_coolify_managed_marker")
    runtime_pos = install.find("ansible.builtin.import_tasks: verify-runtime.yml")
    if marker_pos <= runtime_pos:
        raise ContractError("managed marker must be written only after runtime verification")

    for phrase in (
        "solo_vps_coolify_expected_docker_config",
        "solo_vps_coolify_expected_image",
        "State.Health.Status",
        "NetworkSettings.Ports['8080/tcp']",
        "NetworkSettings.Ports['6001/tcp']",
        "NetworkSettings.Ports['6002/tcp']",
        "HostIp == solo_vps_coolify_management_bind_address",
        "ansible.builtin.wait_for",
        "state: stopped",
        "delegate_to: localhost",
        "become: false",
        "http://127.0.0.1:8000/api/health",
        "http://127.0.0.1:6001/ready",
        "http://127.0.0.1:6002/ready",
        "solo_vps_coolify_verify_realtime.State.Health.Status == 'healthy'",
        "solo_vps_coolify_realtime_ready_http.status == 200",
        "solo_vps_coolify_terminal_ready_http.status == 200",
    ):
        require(runtime, phrase, "runtime verifier")


    if runtime.count("HostIp == solo_vps_coolify_management_bind_address") != 3:
        raise ContractError("runtime verifier must enforce loopback HostIp for all three management publishes")

    wait_pos = runtime.find("Wait for the Coolify application healthcheck")
    realtime_probe_pos = runtime.find("Probe the loopback Coolify realtime readiness endpoint")
    terminal_probe_pos = runtime.find("Probe the loopback Coolify terminal readiness endpoint")
    refresh_pos = runtime.find("Re-inspect the Coolify application container after health wait")
    derive_pos = runtime.find("Derive runtime verification evidence")
    assert_pos = runtime.find("Assert pinned image, healthy runtime, loopback publishes, and M7 ownership")
    if not (0 <= wait_pos < realtime_probe_pos < terminal_probe_pos < refresh_pos < derive_pos < assert_pos):
        raise ContractError(
            "runtime verifier must prove realtime/terminal readiness and refresh docker inspect evidence before assertion"
        )
    require(runtime, "Report Coolify runtime evidence before enforcing it", "runtime verifier")

    for phrase in (
        "solo_vps_coolify_pending_marker",
        "solo_vps_coolify_recovery_allow_unmarked",
        "Find Coolify-normalized localhost private-key files after production seeding",
        "patterns: '^ssh_key@[^.]+$'",
        "solo_vps_coolify_recovery_key_candidates | length == 1",
        "Derive the effective localhost public key without exposing the private key",
        "solo_vps_coolify_recovery_authorized_keys.content | b64decode",
        "Verify the interrupted Coolify runtime before adopting the transaction",
        "ansible.builtin.import_tasks: verify-runtime.yml",
        "Record successful Solo VPS ownership after recovery verification",
        "state: absent",
    ):
        require(recover, phrase, "Coolify recovery backend")

    if "solo_vps_coolify_recovery_key_state.exists" in recover:
        raise ContractError(
            "recovery must inspect the selected effective key stat; it must not require the pre-seed key path forever"
        )

    recovery_runtime_pos = recover.find("Verify the interrupted Coolify runtime before adopting the transaction")
    recovery_marker_pos = recover.find("Record successful Solo VPS ownership after recovery verification")
    if recovery_marker_pos <= recovery_runtime_pos:
        raise ContractError("recovery must write the managed marker only after runtime verification")

    for phrase in (
        "solo_vps_coolify_managed_marker",
        "checksum_algorithm: sha256",
        "solo_vps_coolify_env_state.stat.mode == '0600'",
        "solo_vps_coolify_data_parent_state.stat.uid == 0",
        "solo_vps_coolify_data_root_state.stat.uid == 9999",
        "solo_vps_coolify_resource_root_states",
        "item.stat.uid == 9999",
        "item.stat.gid == solo_vps_coolify_verify_admin_gid",
        "item.stat.mode == solo_vps_coolify_non_root_resource_root_mode",
        'loop: "{{ solo_vps_coolify_non_root_resource_roots }}"',
        "register: solo_vps_coolify_resource_root_chdir_probes",
        "item.stdout | trim == item.item",
        "solo_vps_coolify_proxy_state.stat.uid == solo_vps_coolify_verify_admin_uid",
        "solo_vps_coolify_proxy_state.stat.gid == solo_vps_coolify_verify_admin_gid",
        "solo_vps_coolify_proxy_state.stat.mode == solo_vps_coolify_non_root_proxy_mode",
        'become_user: "{{ admin.user }}"',
        'chdir: "{{ solo_vps_coolify_data_root }}/proxy"',
        "solo_vps_coolify_proxy_chdir_probe.stdout",
        "ansible.builtin.import_tasks: verify-runtime.yml",
    ):
        require(verify, phrase, "managed verifier")

    for phrase in (
        "solo_vps_coolify_install_pending_marker",
        "tasks_from: resume-install",
        "tasks_from: readiness",
        "tasks_from: install",
        "tasks_from: reconcile-runtime-access",
        "tasks_from: verify",
    ):
        require(playbook, phrase, "Coolify playbook")
    reconcile_pos = playbook.find("tasks_from: reconcile-runtime-access")
    verify_pos = playbook.find("tasks_from: verify")
    if not (0 <= reconcile_pos < verify_pos):
        raise ContractError("managed Coolify runtime access must reconcile before verification")

    require(recover_playbook, "tasks_from: recover", "Coolify recovery playbook")
    require(verify_playbook, "tasks_from: verify", "Coolify verify playbook")

    for phrase in (
        "coolify:",
        "coolify-recover:",
        "COOLIFY_RECOVERY_CONFIRM_REQUIRED := I_HAVE_REVIEWED_THE_PARTIAL_SOLO_VPS_INSTALL",
        "verify-coolify:",
        "$(PLAYBOOK_DIR)/coolify.yml --syntax-check",
        "$(PLAYBOOK_DIR)/recover-coolify.yml --syntax-check",
        "$(PLAYBOOK_DIR)/verify-coolify.yml --syntax-check",
    ):
        require(makefile, phrase, "Makefile")

    return [
        "PASS Coolify install backend: pinned manual flow only",
        "PASS Coolify install safety: transaction marker + fail-closed explicit recovery + secret log suppression",
        "PASS Coolify non-root runtime access: bounded resource traversal + private writable backup root + admin-owned proxy verification",
        "PASS Coolify runtime verification: post-wait evidence refresh, exact image, M7 daemon ownership, loopback + controller isolation",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        messages = validate(Path(args.root).resolve())
    except (OSError, ContractError) as exc:
        print(f"ERROR Coolify install backend contract: {exc}")
        return 2
    for message in messages:
        print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
