#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


class ContractError(ValueError):
    pass


CONTRACT = "docs/contracts/external-uptime-policy.yml"
GUIDE = "docs/operations/external-uptime.md"
MAKEFILE = "Makefile"
README = "README.md"
MKDOCS = "mkdocs.yml"
RUNTIME = "scripts/external_uptime.py"


def read(root: Path, rel: str) -> str:
    path = root / rel
    if not path.is_file():
        raise ContractError(f"required external uptime source missing: {rel}")
    return path.read_text(encoding="utf-8")


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        raise ContractError(f"{where} must contain {needle!r}")


def load_contract(root: Path) -> dict[str, object]:
    try:
        data = yaml.safe_load(read(root, CONTRACT))
    except yaml.YAMLError as exc:
        raise ContractError(f"cannot parse {CONTRACT}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError(f"{CONTRACT} must be a mapping")
    return data


def validate_policy(data: dict[str, object]) -> None:
    if data.get("version") != 1 or data.get("owner") != "external-http-monitor":
        raise ContractError("external uptime policy version/owner drift")

    purpose = data.get("purpose")
    if not isinstance(purpose, dict) or purpose != {
        "detect_total_vps_loss": True,
        "same_vps_monitor_is_not_sufficient": True,
    }:
        raise ContractError("external uptime purpose must require total-host detection outside the VPS")

    target = data.get("health_target")
    if not isinstance(target, dict):
        raise ContractError("health_target must be a mapping")
    expected_target = {
        "kind": "public-application-health-endpoint",
        "scheme": "https",
        "method": "GET",
        "expected_status": 200,
        "authentication": "none",
        "follow_redirects": False,
        "raw_coolify_management_ports_allowed": False,
    }
    for key, value in expected_target.items():
        if target.get(key) != value:
            raise ContractError(f"health_target.{key} must remain {value!r}")

    monitor = data.get("monitor_policy")
    if not isinstance(monitor, dict):
        raise ContractError("monitor_policy must be a mapping")
    expected_monitor = {
        "default_interval_seconds": 300,
        "min_interval_seconds": 60,
        "max_interval_seconds": 300,
        "default_timeout_seconds": 10,
        "min_timeout_seconds": 1,
        "max_timeout_seconds": 10,
        "provider_confirmation_retries_required": True,
        "max_alert_detection_seconds": 660,
        "max_recovery_notification_seconds": 600,
    }
    if monitor != expected_monitor:
        raise ContractError(f"monitor_policy drift: expected {expected_monitor}, found {monitor}")

    notification = data.get("notification")
    if not isinstance(notification, dict) or not all(notification.get(key) is True for key in (
        "destination_must_be_off_vps",
        "test_notification_required",
        "outage_alert_required",
        "recovery_notification_required",
    )):
        raise ContractError("notification contract must require off-VPS test/outage/recovery delivery")

    validation = data.get("validation")
    if not isinstance(validation, dict):
        raise ContractError("validation must be a mapping")
    expected_validation = {
        "provider_api_automation_required": False,
        "source_plan_makes_network_request": False,
        "source_plan_mutates_provider": False,
        "crit015_v3_requires_whole_target_shutdown": True,
        "provider_event_or_ui_artifact_review_required": True,
        "provider_artifact_sha256_required": True,
        "evidence_must_not_store_health_url": True,
    }
    if validation != expected_validation:
        raise ContractError("external uptime validation/evidence boundary drift")


def validate_sources(root: Path) -> None:
    runtime = read(root, RUNTIME)
    for needle in (
        "I_HAVE_REVIEWED_THE_EXTERNAL_UPTIME_PROOF",
        "I_HAVE_REVIEWED_THE_EXTERNAL_PROVIDER_EVENT_ARTIFACT",
        "provider_event_artifact_sha256",
        "whole-target-shutdown",
        "public-endpoint-outage",
        '"health_url_retained": False',
        '"raw_provider_logs_retained": False',
        '"network_request": False',
        '"mutation": False',
    ):
        require(runtime, needle, RUNTIME)
    for forbidden in ("requests.get(", "curl ", "Authorization:", "api_token", "provider_token"):
        if forbidden in runtime:
            raise ContractError(f"{RUNTIME} must remain provider-credential/network independent: {forbidden!r}")

    makefile = read(root, MAKEFILE)
    for target in (
        "validate-external-uptime:",
        "test-external-uptime:",
        "uptime-plan:",
        "uptime-evidence:",
    ):
        require(makefile, target, MAKEFILE)
    ci_line = next((line for line in makefile.splitlines() if line.startswith("ci-fast-source:")), "")
    for target in ("validate-external-uptime", "test-external-uptime"):
        require(ci_line, target, "Makefile ci-fast-source")


def validate_docs(root: Path) -> None:
    guide = read(root, GUIDE)
    for needle in (
        "UptimeRobot Free",
        "external uptime monitor",
        "https://app.example.com/healthz",
        "HTTP 200",
        "5 minutes",
        "10 seconds",
        "confirmation retries",
        "8000/6001/6002",
        "Test Notification",
        "DOWN",
        "UP",
        "disposable/test server",
        "make uptime-plan",
    ):
        require(guide, needle, GUIDE)

    readme = read(root, README)
    require(readme, "docs/operations/external-uptime.md", README)
    require(readme, "External uptime", README)

    mkdocs = read(root, MKDOCS)
    require(mkdocs, "operations/external-uptime.md", MKDOCS)


def validate(root: Path) -> None:
    root = root.resolve()
    validate_policy(load_contract(root))
    validate_sources(root)
    validate_docs(root)
    print(
        "PASS external uptime contract: external HTTPS app health check + off-VPS alert/recovery + "
        "whole-target V3 proof are explicit"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate(Path(args.root))
    except (OSError, ContractError) as exc:
        print(f"ERROR external uptime contract: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
