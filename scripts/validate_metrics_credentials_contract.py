#!/usr/bin/env python3
"""Validate the source-only Grafana Cloud Metrics credential boundary."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


class ContractError(RuntimeError):
    pass


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        raise ContractError(f"{where} missing metrics credential contract: {needle}")


def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        raise ContractError(f"{where} contains forbidden metrics credential behavior: {needle}")


def validate(root: Path) -> None:
    root = root.resolve()
    make = (root / "Makefile").read_text(encoding="utf-8")
    common = (root / "scripts/metrics_credentials_common.py").read_text(encoding="utf-8")
    bundle = (root / "scripts/metrics_secret_bundle.py").read_text(encoding="utf-8")
    installer = (root / "scripts/install_metrics_credentials.py").read_text(encoding="utf-8")
    win_init = (root / "scripts/windows/init-metrics-secrets.ps1").read_text(encoding="utf-8")
    win_test = (root / "scripts/windows/test-metrics-secrets.ps1").read_text(encoding="utf-8")
    win_push = (root / "scripts/windows/push-metrics-secrets.ps1").read_text(encoding="utf-8")
    docs = (root / "docs/operations/metrics.md").read_text(encoding="utf-8")
    docs_ru = (root / "docs/operations/metrics.ru.md").read_text(encoding="utf-8")

    for needle in (
        "METRICS_SECRET_FILE ?= $(SOLO_VPS_SECRET_DIR)/metrics.enc.yaml",
        "metrics-secrets-init:", "metrics-secrets-check:", "metrics-secrets-push:",
        "verify-metrics-credentials:", "validate-metrics-credentials:", "test-metrics-credentials:",
    ):
        require(make, needle, "Makefile")

    for needle in (
        "PROMETHEUS_URL", "PROMETHEUS_USERNAME", "GRAFANA_CLOUD_METRICS_API_KEY",
        "/api/prom/push", "must use HTTPS", "must be the numeric Grafana Cloud Metrics user/instance ID",
    ):
        require(common, needle, "scripts/metrics_credentials_common.py")

    for needle in (
        'SOPS_FILENAME_OVERRIDE = "secrets/metrics.enc.yaml"',
        "refusing symlink metrics ciphertext destination",
        "install_metrics_credentials.py apply",
        "already exists; reusing it",
        "workstation-to-VPS metrics credential delivery",
    ):
        require(bundle, needle, "scripts/metrics_secret_bundle.py")

    for needle in (
        'DEFAULT_DIRECTORY = Path("/etc/solo-vps/metrics")',
        'DEFAULT_PATH = DEFAULT_DIRECTORY / "grafana-cloud.json"',
        "mode: 0600", "telemetry sent: no", "refusing non-regular metrics credential path",
    ):
        require(installer, needle, "scripts/install_metrics_credentials.py")

    for text, where in ((win_init, "Windows init"), (win_test, "Windows test"), (win_push, "Windows push")):
        for needle in ("metrics.enc.yaml", "PROMETHEUS_URL", "PROMETHEUS_USERNAME", "GRAFANA_CLOUD_METRICS_API_KEY"):
            require(text, needle, where)
        forbid(text, "Loki push endpoint", where)
        forbid(text, "Logs user ID", where)
        forbid(text, "Observability credential", where)

    for needle in (
        ".\\scripts\\windows\\init-metrics-secrets.ps1",
        ".\\scripts\\windows\\test-metrics-secrets.ps1",
        ".\\scripts\\windows\\push-metrics-secrets.ps1",
        "make metrics-secrets-init", "make metrics-secrets-check", "make metrics-secrets-push",
        "/etc/solo-vps/metrics/grafana-cloud.json", "metrics:write",
    ):
        require(docs + docs_ru, needle, "chapter 7 metrics docs")

    for forbidden in ("GRAFANA_CLOUD_METRICS_API_KEY=", "PROMETHEUS_USERNAME=123", "glc_"):
        forbid(docs + docs_ru, forbidden, "chapter 7 metrics docs")

    print("PASS metrics credential contract: workstation SOPS ciphertext -> root-only VPS runtime file")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path.cwd())
    args = parser.parse_args()
    try:
        validate(args.root)
    except (ContractError, OSError) as exc:
        print(f"ERROR metrics credential contract: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
