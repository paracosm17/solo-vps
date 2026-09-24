#!/usr/bin/env python3
"""Validate the source-only Solo VPS host metrics runtime contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


class ContractError(RuntimeError):
    pass


def req(text: str, needle: str, where: str) -> None:
    if needle not in text:
        raise ContractError(f"{where} missing host metrics contract: {needle}")


def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        raise ContractError(f"{where} contains forbidden host metrics behavior: {needle}")


def validate(root: Path) -> None:
    root = root.resolve()
    make = (root / "Makefile").read_text(encoding="utf-8")
    defaults = (root / "ansible/roles/metrics/defaults/main.yml").read_text(encoding="utf-8")
    install = (root / "ansible/roles/metrics/tasks/install-runtime.yml").read_text(encoding="utf-8")
    verify = (root / "ansible/roles/metrics/tasks/verify-runtime.yml").read_text(encoding="utf-8")
    config = (root / "ansible/roles/metrics/templates/config.alloy.j2").read_text(encoding="utf-8")
    unit = (root / "ansible/roles/metrics/templates/solo-vps-metrics.service.j2").read_text(encoding="utf-8")
    apply_pb = (root / "ansible/playbooks/metrics-runtime.yml").read_text(encoding="utf-8")
    verify_pb = (root / "ansible/playbooks/verify-metrics-runtime.yml").read_text(encoding="utf-8")
    docs = (root / "docs/operations/metrics.md").read_text(encoding="utf-8")
    docs_ru = (root / "docs/operations/metrics.ru.md").read_text(encoding="utf-8")

    for needle in (
        "solo_vps_metrics_user: solo-vps-metrics", "solo_vps_metrics_http_host: 127.0.0.1",
        "solo_vps_metrics_http_port: 12346", "solo_vps_metrics_scrape_interval: 60s",
    ):
        req(defaults, needle, "metrics defaults")

    for needle in (
        'prometheus.exporter.unix "integrations_node_exporter"',
        'set_collectors = ["cpu", "filesystem", "loadavg", "meminfo", "uname"]',
        'replacement  = constants.hostname', 'replacement  = "integrations/node_exporter"',
        'prometheus.scrape "integrations_node_exporter"', 'prometheus.remote_write "grafana_cloud"',
        'url = sys.env("PROMETHEUS_URL")', 'username = sys.env("PROMETHEUS_USERNAME")',
        'password = sys.env("GRAFANA_CLOUD_METRICS_API_KEY")',
    ):
        req(config, needle, "metrics Alloy config")
    for bad in ("loki.", "docker", "cadvisor", "process_exporter"):
        forbid(config.lower(), bad.lower(), "metrics Alloy config")

    for needle in (
        "User={{ solo_vps_metrics_user }}", "Group={{ solo_vps_metrics_group }}",
        "NoNewPrivileges=true", "ProtectSystem=strict", "CapabilityBoundingSet=",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", "--server.http.listen-addr={{ solo_vps_metrics_http_host }}:{{ solo_vps_metrics_http_port }}",
    ):
        req(unit, needle, "metrics systemd unit")
    forbid(unit, "User=root", "metrics systemd unit")

    for needle in (
        "Require root-only Grafana Cloud Metrics credentials", "mode: \"0700\"", "mode: \"0750\"",
        "mode: \"0640\"", "Validate the host metrics Alloy configuration", "Enable and start host metrics collection",
        "import_tasks: verify-runtime.yml",
    ):
        req(install, needle, "metrics install tasks")
    for needle in (
        "systemctl, is-enabled", "systemctl, is-active", "/-/ready", "running/enabled",
        "collector: prometheus.exporter.unix", "token_printed: false",
    ):
        req(verify, needle, "metrics verify tasks")

    req(apply_pb, "tasks_from: install-runtime.yml", "metrics runtime playbook")
    req(verify_pb, "tasks_from: verify-runtime.yml", "metrics verify playbook")

    for needle in (
        "metrics-tooling:", "metrics-runtime:", "verify-metrics-runtime:",
        "validate-metrics-runtime:", "test-metrics-runtime:",
        "$(PLAYBOOK_DIR)/metrics-runtime.yml --syntax-check", "$(PLAYBOOK_DIR)/verify-metrics-runtime.yml --syntax-check",
    ):
        req(make, needle, "Makefile")
    aggregate = re.search(r"^validate:\s+([^#\n]+)", make, re.M)
    if not aggregate or not {"validate-metrics-runtime", "test-metrics-runtime"} <= set(aggregate.group(1).split()):
        raise ContractError("aggregate validate must include metrics runtime validator/tests")

    for needle in (
        "Grafana Cloud", "Metrics Drilldown", "node_cpu_seconds_total", "node_memory_MemAvailable_bytes",
        "node_filesystem_avail_bytes", "make metrics-runtime", "make verify-metrics-runtime",
        "solo-vps-metrics.service", "15%", "↻ Refresh", "Advanced options",
        "WHEN QUERY", "IS BELOW", "101", "New evaluation group", "Org Settings → Members",
    ):
        req(docs + docs_ru, needle, "chapter 7 metrics docs")
    for bad in (
        "M24", "ADR-", "CRIT-", "/var/run/docker.sock",
        "add a **Reduce** expression", "добавьте **Reduce** expression",
        "add a **Threshold** expression", "добавьте **Threshold** expression",
    ):
        forbid(docs + docs_ru, bad, "chapter 7 metrics docs")

    print("PASS host metrics runtime contract: small non-root Alloy exporter -> Grafana Cloud Metrics")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path.cwd())
    args = parser.parse_args()
    try:
        validate(args.root)
    except (ContractError, OSError) as exc:
        print(f"ERROR host metrics runtime contract: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
