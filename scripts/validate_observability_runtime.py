#!/usr/bin/env python3
"""Validate the M24 Alloy + identity-gated Docker API proxy retained-log contract."""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import sys

class ContractError(RuntimeError):
    pass

def req(text: str, needle: str, where: str) -> None:
    if needle not in text:
        raise ContractError(f"{where} missing retained-log runtime contract: {needle}")

def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        raise ContractError(f"{where} contains forbidden retained-log runtime behavior: {needle}")

def validate(root: Path) -> None:
    root = root.resolve()
    read = lambda rel: (root / rel).read_text(encoding="utf-8")
    defaults = read("ansible/roles/observability/defaults/main.yml")
    install = read("ansible/roles/observability/tasks/install-runtime.yml")
    verify = read("ansible/roles/observability/tasks/verify-runtime.yml")
    confidentiality = read("ansible/roles/observability/tasks/audit-confidentiality.yml")
    config = read("ansible/roles/observability/templates/config.alloy.j2")
    unit = read("ansible/roles/observability/templates/solo-vps-alloy.service.j2")
    tmpfiles = read("ansible/roles/observability/templates/solo-vps-observability.tmpfiles.j2")
    apply_pb = read("ansible/playbooks/observability-runtime.yml")
    verify_pb = read("ansible/playbooks/verify-observability-runtime.yml")
    confidentiality_pb = read("ansible/playbooks/audit-observability-confidentiality.yml")
    make = read("Makefile")
    docs = read("docs/operations/observability.md")
    arch = read("docs/architecture.md")
    testing = read("docs/testing.md")
    state = read("docs/state-layout.md")
    roadmap = read("ROADMAP.md")
    changelog = read("CHANGELOG.md")

    for needle in (
        'solo_vps_docker_api_proxy_version: "0.5.0"',
        'ghcr.io/tecnativa/docker-socket-proxy:v0.5.0@sha256:753044cb0851ce53ab44c2504872ff02ae37be9c294fa8abea3754074e61eab4',
        'ghcr.io/tecnativa/docker-socket-proxy:v0.5.0@sha256:c50ae24d0d3ec88b8cf07fbd9e7e262eba91caf846e632e1a01ad5bbfaa9f47d',
        'solo_vps_docker_api_proxy_runtime_dir: /run/solo-vps-docker-api',
        'solo_vps_docker_api_proxy_host_socket: /run/solo-vps-docker-api/docker-api.sock',
        'solo_vps_docker_api_proxy_container_socket_dir: /proxy',
        'solo_vps_docker_api_proxy_container_socket: /proxy/docker-api.sock',
        'solo_vps_docker_api_proxy_bind_config: /proxy/docker-api.sock mode 666',
        'solo_vps_docker_api_proxy_tmpfiles_path: /etc/tmpfiles.d/solo-vps-observability.conf',
        'solo_vps_alloy_docker_host: unix:///run/solo-vps-docker-api/docker-api.sock',
        'solo_vps_docker_api_proxy_legacy_host: 127.0.0.1',
        'solo_vps_docker_api_proxy_legacy_port: 2375',
        'solo_vps_alloy_http_host: 127.0.0.1',
        'solo_vps_observability_runtime_env_path: /etc/solo-vps/observability/alloy.env',
        'solo_vps_alloy_config_dir: /etc/solo-vps-alloy',
    ):
        req(defaults, needle, "observability defaults")
    for bad in (
        'solo_vps_alloy_docker_host: tcp://',
        'solo_vps_docker_api_proxy_host: 127.0.0.1',
        'solo_vps_docker_api_proxy_port: 2375',
        'solo_vps_alloy_config_dir: /etc/solo-vps/observability',
    ):
        forbid(defaults, bad, "observability defaults")

    for needle in (
        'Create the dedicated non-login Alloy group',
        'Create the dedicated non-login Alloy user',
        'Install the boot-time Docker API proxy runtime-directory contract',
        'solo-vps-observability.tmpfiles.j2',
        '/usr/bin/systemd-tmpfiles',
        'Enforce the Alloy-only Docker API proxy runtime-directory boundary now',
        'mode: "0750"',
        'Classify exact desired or exact legacy Docker API proxy state before mutation',
        'solo_vps_docker_api_proxy_existing_desired',
        'solo_vps_docker_api_proxy_existing_legacy',
        'Refuse implicit takeover of an unexpected Docker API proxy container',
        'Remove only the exact known V3 loopback proxy before Unix-socket migration',
        'Create the Alloy-only Unix-socket Docker API proxy when absent or migrated',
        '      - --network\n      - none\n', '--privileged', '--read-only',
        'BIND_CONFIG={{ solo_vps_docker_api_proxy_bind_config }}',
        'CONTAINERS=1', 'EVENTS=1', 'PING=1', 'VERSION=1',
        '      - --env\n      - NETWORKS=1\n',
        '      - --env\n      - POST=0\n',
        '      - --env\n      - AUTH=0\n',
        '      - --env\n      - EXEC=0\n',
        '      - --env\n      - IMAGES=0\n',
        '      - --env\n      - INFO=0\n',
        '      - --env\n      - SECRETS=0\n',
        '      - --env\n      - VOLUMES=0\n',
        '--mount',
        'type=bind,source={{ solo_vps_docker_api_proxy_runtime_dir }},target={{ solo_vps_docker_api_proxy_container_socket_dir }}',
        ':{{ solo_vps_docker_api_proxy_socket }}:ro',
        'Wait for the managed Docker API proxy Unix socket to appear',
        'Prove the non-root Alloy identity can reach the managed proxy socket path',
        'Create the Alloy configuration directory outside the root-only credential tree',
        'mode: "0640"',
        'Prove the non-root Alloy identity can access managed runtime paths',
        'Prove the non-root Alloy identity can read its managed configuration',
        'Remove the obsolete PRE-ALPHA Alloy config from the root-only credential tree',
        'stat.S_IMODE(st.st_mode) == 0o600', 'os.chmod(temporary, 0o600)', 'os.chown(temporary, 0, 0)',
        'no_log: true', 'os.replace', 'os.execve', 'validate', 'systemd_service:',
    ):
        req(install, needle, "install-runtime.yml")
    for bad in (
        '--publish', '--publish-all', '0.0.0.0:2375',
        '- --env\n      - POST=1', '- --env\n      - EXEC=1', '- --env\n      - AUTH=1', '- --env\n      - SECRETS=1',
        'ansible.builtin.slurp:',
    ):
        forbid(install, bad, "install-runtime.yml")
    if install.index('Classify exact desired or exact legacy Docker API proxy state before mutation') > install.index('Remove only the exact known V3 loopback proxy before Unix-socket migration'):
        raise ContractError("install-runtime.yml must classify legacy state before removal")
    if install.index('Refuse implicit takeover of an unexpected Docker API proxy container') > install.index('Remove only the exact known V3 loopback proxy before Unix-socket migration'):
        raise ContractError("install-runtime.yml must refuse unknown state before migration mutation")
    if install.index('Create the dedicated non-login Alloy group') > install.index('Install the boot-time Docker API proxy runtime-directory contract'):
        raise ContractError("Alloy group must exist before creating the group-gated runtime directory")

    for needle in (
        'd {{ solo_vps_docker_api_proxy_runtime_dir }} 0750 root {{ solo_vps_alloy_group }} -',
    ):
        req(tmpfiles, needle, "tmpfiles template")
    for bad in ('0777', '0755 root'):
        forbid(tmpfiles, bad, "tmpfiles template")

    for needle in (
        'discovery.docker "coolify"', 'host             = "{{ solo_vps_alloy_docker_host }}"',
        'coolify.managed=true', 'coolify_type', '(application|service)',
        '__meta_docker_container_label_coolify_serviceName', 'target_label  = "service_name"',
        'loki.source.docker "coolify"', 'loki.write "grafana_cloud"',
        'sys.env("LOKI_URL")', 'sys.env("LOKI_USERNAME")', 'sys.env("GRAFANA_CLOUD_API_KEY")',
    ):
        req(config, needle, "config.alloy.j2")
    for bad in ('unix:///var/run/docker.sock', 'tcp://127.0.0.1:2375', 'container_name"\n    target_label  = "service_name"'):
        forbid(config, bad, "config.alloy.j2")

    for needle in (
        'User={{ solo_vps_alloy_user }}', 'EnvironmentFile={{ solo_vps_observability_runtime_env_path }}',
        'WorkingDirectory={{ solo_vps_alloy_state_dir }}', '--disable-reporting', '--server.http.enable-pprof=false',
        '--server.http.listen-addr={{ solo_vps_alloy_http_host }}:{{ solo_vps_alloy_http_port }}',
        'NoNewPrivileges=true', 'ProtectSystem=strict', 'CapabilityBoundingSet=',
        'RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6',
    ):
        req(unit, needle, "solo-vps-alloy.service.j2")
    forbid(unit, 'User=root', "solo-vps-alloy.service.j2")

    for needle in ('tasks_from: install-runtime.yml', 'gather_facts: true'):
        req(apply_pb, needle, "observability-runtime.yml")
    for needle in ('tasks_from: verify-runtime.yml', 'gather_facts: true'):
        req(verify_pb, needle, "verify-observability-runtime.yml")
    for needle in ('tasks_from: verify-runtime.yml', 'tasks_from: audit-confidentiality.yml', 'gather_facts: true'):
        req(confidentiality_pb, needle, "audit-observability-confidentiality.yml")

    for needle in (
        'Inspect the group-gated Docker API proxy runtime directory',
        'Inspect the managed Docker API proxy Unix socket',
        'Inspect the boot-time tmpfiles contract for the proxy runtime directory',
        'Prove Alloy can traverse the managed proxy runtime directory',
        'Prove an unrelated host identity cannot traverse the proxy runtime directory',
        'Prove Alloy still cannot read the real Docker daemon socket directly',
        'socket.AF_UNIX', 'sock.connect(self.path)',
        'Probe the managed proxy as an unrelated host identity without reading response content',
        'solo_vps_alloy_runtime_proxy_unrelated_status == -1',
        '      - solo_vps_alloy_runtime_direct_socket_read.rc != 0',
        '      - solo_vps_alloy_runtime_proxy_networks_status == 200',
        '      - solo_vps_alloy_runtime_proxy_info_status == 403',
        "      - \"'AUTH=0' in solo_vps_alloy_runtime_proxy_env\"",
        "      - \"'EXEC=0' in solo_vps_alloy_runtime_proxy_env\"",
        "      - \"'IMAGES=0' in solo_vps_alloy_runtime_proxy_env\"",
        "      - \"'INFO=0' in solo_vps_alloy_runtime_proxy_env\"",
        "      - \"'SECRETS=0' in solo_vps_alloy_runtime_proxy_env\"",
        "      - \"'VOLUMES=0' in solo_vps_alloy_runtime_proxy_env\"",
        "':2375' not in (solo_vps_alloy_runtime_listeners.stdout | default(''))",
        'solo_vps_alloy_runtime_proxy.HostConfig.NetworkMode == \'none\'',
        '(solo_vps_alloy_runtime_proxy_portbindings | length) == 0',
        "('BIND_CONFIG=' ~ solo_vps_docker_api_proxy_bind_config) in solo_vps_alloy_runtime_proxy_env",
        "(solo_vps_alloy_runtime_proxy_socket_stat.stat.mode | default('')) == '0666'",
        'docker_api_proxy_transport: Unix socket only',
        'docker_api_proxy_tcp_listener: absent',
        'docker_api_proxy_unrelated_identity_probe: denied before HTTP response',
        'docker_api_proxy_read_scope: coarse CONTAINERS + NETWORKS API read boundary inside trusted Alloy-only Unix boundary',
        'alloy_direct_docker_socket_readable: false',
        'runtime_env_owner: root:root', 'runtime_env_mode: "0600"',
        'Read detailed Alloy service state without exposing environment values', '--property=NRestarts', '--property=ExecMainStatus',
        'Read the current Alloy systemd invocation identifier without exposing runtime data', '--property=InvocationID',
        'Read only current-invocation Alloy logs before readiness probes without printing payloads',
        "_SYSTEMD_INVOCATION_ID={{ solo_vps_alloy_runtime_invocation_id.stdout | default('') | trim }}",
        'Wait briefly for the loopback Alloy HTTP listener', 'timeout: 15',
        'Report sanitized Alloy current-invocation diagnostics when runtime or diagnostics are unhealthy',
        'journal_scope: current-systemd-invocation', 'journal_scope_available:', 'journal_scope_query_ok:',
        'startup_unknown_flag_error:', 'startup_permission_error:', 'startup_relative_storage_permission_error:',
        'startup_bind_error:', 'startup_config_error:', 'raw_journal_printed: false',
        "(loki|grafana|remote[_ -]?write|prometheus)",
        "(401|403|unauthorized|forbidden)",
        '(solo_vps_alloy_runtime_recent_logs.rc | default(-1)) == 0',
        '(solo_vps_alloy_runtime_ready.status | default(-1)) == 200',
        'current_invocation_diagnostic_errors: false',
    ):
        req(verify, needle, "verify-runtime.yml")
    if "regex_search('(?i)(401|403|unauthorized|forbidden)')" in verify:
        raise ContractError("provider auth diagnostics must not classify a bare Docker-proxy 403 as Grafana auth failure")

    for bad in (
        'http://{{ solo_vps_docker_api_proxy_',
        'solo_vps_docker_api_proxy_host }}:{{ solo_vps_docker_api_proxy_port',
        'docker_api_proxy_http: 127.0.0.1:2375 only',
    ):
        forbid(verify, bad, "verify-runtime.yml")
    if verify.index('Read only current-invocation Alloy logs before readiness probes without printing payloads') > verify.index('Probe Alloy readiness on loopback without hiding startup diagnostics'):
        raise ContractError("current-invocation diagnostics must be collected before readiness probes")
    if verify.index('Wait briefly for the loopback Alloy HTTP listener') > verify.index('Read the current Alloy systemd invocation identifier without exposing runtime data'):
        raise ContractError("journal scoping must occur after bounded startup wait")
    if verify.count('(solo_vps_alloy_runtime_recent_logs.rc | default(-1)) == 0') < 2:
        raise ContractError("verification must fail closed when current-invocation journal evidence is unavailable")

    for needle in (
        'Confirm the unrelated low-privilege audit identity exists', '/usr/bin/getent', 'passwd', 'nobody',
        'Select one running Coolify-managed container without returning container metadata', 'label=coolify.managed=true',
        'Prove Alloy does not have direct read access to the Docker Unix socket',
        'Prove the unrelated identity cannot traverse the managed proxy directory',
        'Probe proxy ping as the intended Alloy identity without reading response content',
        'Probe proxy ping as an unrelated host identity without reading response content',
        'Probe container inspect as an unrelated host identity without reading response content',
        '/containers/{{ solo_vps_observability_confidentiality_container_id }}/json',
        'Probe one bounded container log request as an unrelated host identity without reading response content',
        '/containers/{{ solo_vps_observability_confidentiality_container_id }}/logs?stdout=1&stderr=1&tail=1',
        'Probe explicitly disabled Docker API sections as Alloy without reading response content',
        'socket.AF_UNIX', 'sock.connect(self.path)',
        'path: /info', 'path: /images/json', 'path: /volumes', 'path: /secrets', 'path: /exec/solo-vps-negative-probe/json',
        'response = conn.getresponse()', 'print(response.status)', 'response.close()',
        'proxy_transport: Unix socket inside root:solo-vps-alloy 0750 runtime directory',
        'unrelated_identity_runtime_dir_traversable:',
        'inspect_payload_printed: false', 'container_env_printed: false', 'container_log_payload_printed: false',
        'Enforce the CRIT-005 observability confidentiality gate',
        'solo_vps_observability_confidentiality_alloy_socket_read.rc != 0',
        '(solo_vps_observability_confidentiality_unrelated_dir_access.rc | default(0)) != 0',
        'solo_vps_observability_confidentiality_alloy_ping_status == 200',
        'solo_vps_observability_confidentiality_unrelated_ping_status == -1',
        'solo_vps_observability_confidentiality_unrelated_inspect_status == -1',
        'solo_vps_observability_confidentiality_unrelated_logs_status == -1',
        'solo_vps_observability_confidentiality_info_status == 403',
        'solo_vps_observability_confidentiality_images_status == 403',
        'solo_vps_observability_confidentiality_volumes_status == 403',
        'solo_vps_observability_confidentiality_secrets_status == 403',
        'solo_vps_observability_confidentiality_exec_status == 403',
    ):
        req(confidentiality, needle, "audit-confidentiality.yml")
    if confidentiality.count('no_log: true') < 6:
        raise ContractError("audit must suppress container identifiers/status probe internals")
    if 'no_log: true\n  register: solo_vps_observability_confidentiality_container_ids' not in confidentiality:
        raise ContractError("audit must suppress selected container identifier")
    for bad in ('return_content: true', 'ansible.builtin.slurp:', 'docker inspect', 'Config.Env', 'response.read(', '.read()'):
        forbid(confidentiality, bad, "audit-confidentiality.yml")

    for needle in (
        'OBSERVABILITY_RUNTIME_VALIDATOR := scripts/validate_observability_runtime.py',
        'validate-observability-runtime:', 'test-observability-runtime:',
        'observability-runtime: doctor-admin-local', 'verify-observability-runtime: doctor-admin-local',
        '$(PLAYBOOK_DIR)/observability-runtime.yml --syntax-check',
        '$(PLAYBOOK_DIR)/verify-observability-runtime.yml --syntax-check',
        '$(PLAYBOOK_DIR)/audit-observability-confidentiality.yml --syntax-check',
        'audit-observability-confidentiality: doctor-admin-local',
    ):
        req(make, needle, "Makefile")
    audit_target = re.search(r'^audit-observability-confidentiality:.*$', make, re.M)
    if not audit_target or '##' in audit_target.group(0):
        raise ContractError("maintainer-only CRIT-005 audit must stay hidden from make help")
    aggregate = re.search(r'^validate:\s+([^#\n]+)', make, re.M)
    if not aggregate or not {'validate-observability-runtime', 'test-observability-runtime'} <= set(aggregate.group(1).split()):
        raise ContractError("aggregate validate must include M24 runtime validator/tests")

    # The beginner guide should describe the supported workflow and observable
    # result, not the internal Docker-proxy/security-audit implementation.
    for needle in (
        'Grafana Alloy', 'Grafana Cloud', 'service_name',
        'make observability-runtime', 'make verify-observability-runtime',
        'Coolify Log Drain',
    ):
        req(docs, needle, "observability docs")
    for needle in (
        'CRIT-005', 'M24', 'audit-observability-confidentiality',
        '/run/solo-vps-docker-api', '/etc/solo-vps-alloy/config.alloy',
        'root-only credential tree', 'host-local unprivileged',
        'CONTAINERS', 'NETWORKS', '/containers/<id>/json', '/containers/<id>/logs',
    ):
        forbid(docs, needle, "beginner observability docs")
    for needle in ('restricted Docker API proxy', 'Unix socket', 'Alloy', 'retained historical application logs'):
        req(arch, needle, "architecture docs")
    for needle in ('audit-observability-confidentiality', 'Unix socket'):
        req(testing, needle, "testing docs")
    for needle in ('/run/solo-vps-docker-api', '/etc/tmpfiles.d/solo-vps-observability.conf'):
        req(state, needle, "state-layout docs")
    for needle in ('Repository-managed Alloy', 'Coolify-native Custom FluentBit', 'CRIT-005', 'Unix socket'):
        req(roadmap, needle, "ROADMAP.md")
    for needle in ('CRIT-005', 'Unix socket'):
        req(changelog, needle, "CHANGELOG.md")

    print('PASS observability runtime contract: non-root Alloy -> restricted Docker API proxy -> Grafana Cloud')

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('root', nargs='?', default='.')
    args = parser.parse_args()
    try:
        validate(Path(args.root))
    except (OSError, ContractError) as exc:
        print(f'ERROR observability runtime contract: {exc}', file=sys.stderr)
        return 2
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
