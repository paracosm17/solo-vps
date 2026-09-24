#!/usr/bin/env python3
"""Validate the M24 Coolify-native Grafana Cloud application-log drain contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


class ContractError(RuntimeError):
    pass


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        raise ContractError(f"{where} missing observability log-drain contract: {needle}")


def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        raise ContractError(f"{where} contains forbidden observability log-drain behavior: {needle}")


def validate(root: Path) -> None:
    root = root.resolve()
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    windows_copy = (root / "scripts/windows/copy-observability-log-drain.ps1").read_text(encoding="utf-8")
    playbook = (root / "ansible/playbooks/verify-observability-log-drain.yml").read_text(encoding="utf-8")
    disabled_playbook = (root / "ansible/playbooks/verify-observability-log-drain-disabled.yml").read_text(encoding="utf-8")
    diagnose_playbook = (root / "ansible/playbooks/diagnose-observability-log-drain.yml").read_text(encoding="utf-8")
    smoke_playbook = (root / "ansible/playbooks/test-observability-loki.yml").read_text(encoding="utf-8")
    smoke_tasks = (root / "ansible/roles/observability/tasks/test-loki-delivery.yml").read_text(encoding="utf-8")
    tasks = (root / "ansible/roles/observability/tasks/verify-log-drain.yml").read_text(encoding="utf-8")
    disabled_tasks = (root / "ansible/roles/observability/tasks/verify-log-drain-disabled.yml").read_text(encoding="utf-8")
    diagnose_tasks = (root / "ansible/roles/observability/tasks/diagnose-log-drain.yml").read_text(encoding="utf-8")
    docs = (root / "docs/operations/grafana-cloud-log-drain.md").read_text(encoding="utf-8")
    observability = (root / "docs/operations/observability.md").read_text(encoding="utf-8")
    roadmap = (root / "ROADMAP.md").read_text(encoding="utf-8")

    for needle in (
        "validate-observability-log-drain:",
        "test-observability-log-drain:",
        "verify-observability-log-drain:",
        "verify-observability-log-drain.yml",
        "verify-observability-log-drain-disabled:",
        "verify-observability-log-drain-disabled.yml",
        "diagnose-observability-log-drain:",
        "diagnose-observability-log-drain.yml",
        "test-observability-loki:",
        "test-observability-loki.yml",
    ):
        require(makefile, needle, "Makefile")

    for needle in (
        "Set-Clipboard",
        "Custom FluentBit Configuration",
        "Name              forward",
        "Port              24224",
        "Name        loki",
        "TLS         On",
        "TLS.Verify  On",
        "HTTP_User",
        "HTTP_Passwd",
        "Rename            container_name container",
        "Rename            COOLIFY_APP_NAME service_name",
        "Label_Keys  `$service_name,`$source",
        "Line_Format json",
        "plaintext file created: no",
        "token printed: no",
        "Logs user ID must be numeric",
        "Clipboard History/sync",
    ):
        require(windows_copy, needle, "scripts/windows/copy-observability-log-drain.ps1")

    for forbidden in (
        "/var/run/docker.sock",
        "chmod 666",
        "docker group",
        "GRAFANA_CLOUD_API_KEY =",
        "Label_Keys  `$service_name,`$container",
    ):
        forbid(windows_copy, forbidden, "scripts/windows/copy-observability-log-drain.ps1")

    for needle in ("ansible.builtin.import_role:", "tasks_from: verify-log-drain"):
        require(playbook, needle, "verify-observability-log-drain.yml")
    forbid(playbook, "roles:\n    - role: observability\n      tasks_from:", "verify-observability-log-drain.yml")

    for needle in ("ansible.builtin.import_role:", "tasks_from: verify-log-drain-disabled"):
        require(disabled_playbook, needle, "verify-observability-log-drain-disabled.yml")
    for needle in (
        "docker\n      - inspect\n      - coolify-log-drain",
        "127.0.0.1",
        "24224",
        "connect_ex",
        "collector_container_absent: true",
        "host_loopback_listener_24224_absent: true",
        "host_loopback_tcp_connect_rejected: true",
        "Do not remove containers or edit /data/coolify/log-drains manually",
        "make verify-observability-log-drain",
        "Enabled checkbox",
        "changed: false",
    ):
        require(disabled_tasks, needle, "verify-log-drain-disabled.yml")

    for needle in ("ansible.builtin.import_role:", "tasks_from: diagnose-log-drain"):
        require(diagnose_playbook, needle, "diagnose-observability-log-drain.yml")
    for needle in (
        "docker\n      - network\n      - inspect",
        "com.docker.compose.project",
        "collector_network_count",
        "collector_compose_network_count",
        "collector_extra_network_count",
        "collector_extra_networks_attached",
        "HostConfig.PortBindings",
        "NetworkSettings.Ports",
        "runtime_port_mapping_missing_after_create",
        "docker_network_names_printed: false",
        "provider_credentials_printed: false",
        "diagnostic_only: true",
        "changed_when: false",
        "'{{ \"{{\" }}.Server.Version{{ \"}}\" }}'",
    ):
        require(diagnose_tasks, needle, "diagnose-log-drain.yml")
    forbid(diagnose_tasks, "'{{\"{{\"}}.Server.Version{{\"}}\"}}'", "diagnose-log-drain.yml")
    for forbidden in (
        "docker network connect",
        "docker network disconnect",
        "docker rm",
        "/data/coolify/log-drains/fluent-bit.conf",
    ):
        forbid(diagnose_tasks, forbidden, "diagnose-log-drain.yml")

    for needle in ("ansible.builtin.import_role:", "tasks_from: test-loki-delivery"):
        require(smoke_playbook, needle, "test-observability-loki.yml")
    for needle in (
        "/etc/solo-vps/observability/grafana-cloud.json",
        "service_name: solo-vps-smoke",
        "solo-vps retained-log connectivity smoke",
        "status_code:",
        "- 204",
        "force_basic_auth: true",
        "no_log: true",
        "No credential value was printed",
    ):
        require(smoke_tasks, needle, "test-loki-delivery.yml")
    if smoke_tasks.count("no_log: true") < 4:
        raise ContractError("test-loki-delivery.yml must keep credentials and provider-auth tasks no_log")
    for needle in (
        "coolify-log-drain",
        "127.0.0.1:24224",
        "HostConfig.LogConfig.Type",
        "fluentd",
        "docker\n      - logs",
        "/var/run/docker.sock",
        "local_docker_logs: readable",
        "COOLIFY_APP_NAME",
        "collector_auth_failure_401_403",
        "collector_bad_request_400",
        "collector_config_failure",
        "/data/coolify/log-drains/docker-compose.yml",
        "/data/coolify/log-drains/fluent-bit.conf",
        "HostConfig.PortBindings",
        "NetworkSettings.Ports",
        "ss",
        "connect_ex",
        "generated_compose_loopback_publication",
        "docker_hostconfig_loopback_binding",
        "docker_networksettings_loopback_binding",
        "host_loopback_tcp_connect",
        "Do not hand-edit /data/coolify/log-drains",
        "test-observability-loki",
        "changed: false",
        "public_listener: none",
        "Docker socket access: not required",
    ):
        require(tasks, needle, "verify-log-drain.yml")


    for forbidden in (
        "solo_vps_log_drain_port",
        "docker\n      - port\n      - coolify-log-drain",
    ):
        forbid(tasks, forbidden, "verify-log-drain.yml")

    for needle in (
        "Rejected Coolify-native",
        "not the maintained application-log setup",
        "Custom FluentBit",
        "Grafana Cloud",
        "COOLIFY_APP_NAME",
        ".\\scripts\\windows\\copy-observability-log-drain.ps1",
        "Configuration > Log Drains",
        "Advanced",
        "Drain Logs",
        "make verify-observability-log-drain",
        "make verify-observability-log-drain-disabled",
        "make diagnose-observability-log-drain",
        "make test-observability-loki",
        "service_name",
        "127.0.0.1:24224",
        "COOLIFY_APP_NAME",
        "ordinary Coolify",
        "clear the clipboard",
    ):
        require(docs, needle, "docs/operations/grafana-cloud-log-drain.md")

    # Keep the rejected Fluent Bit experiment documented in the maintainer
    # reference above. The public chapter only needs to tell an operator which
    # supported path to use now.
    for needle in (
        "Grafana Alloy",
        "You do not need to configure a Coolify Log Drain",
    ):
        require(observability, needle, "docs/operations/observability.md")
    for needle in (
        "Custom FluentBit",
        "M24",
        "restricted Docker API proxy",
    ):
        forbid(observability, needle, "beginner observability guide")

    for needle in (
        "Coolify-native Custom FluentBit experiment is **rejected as the maintained default**",
        "Grafana Cloud credential encryption/delivery integration PASS",
        "Repository-managed non-root Alloy",
    ):
        require(roadmap, needle, "ROADMAP.md")

    print("PASS historical log-drain contract: rejected Coolify Fluent Bit experiment remains diagnosable without becoming the maintained path")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate(Path(args.root))
    except (OSError, ContractError) as exc:
        print(f"ERROR observability log-drain contract: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
