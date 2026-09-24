#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


POLICY = {
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
CONFIRM_REQUIRED = "I_HAVE_REVIEWED_THE_EXTERNAL_UPTIME_PROOF"
ARTIFACT_CONFIRM_REQUIRED = "I_HAVE_REVIEWED_THE_EXTERNAL_PROVIDER_EVENT_ARTIFACT"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROOF_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
CHANNELS = {"email", "push", "chat", "sms", "other-external"}
EXERCISE_MODES = {"whole-target-shutdown", "public-endpoint-outage"}


class UptimeError(ValueError):
    pass


@dataclass(frozen=True)
class HealthTarget:
    fingerprint_sha256: str
    hostname_kind: str


def _public_target(url: str) -> HealthTarget:
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise UptimeError(f"health URL is invalid: {exc}") from exc

    if parsed.scheme != "https":
        raise UptimeError("health URL must use https")
    if parsed.username or parsed.password:
        raise UptimeError("health URL must not contain credentials")
    if not parsed.hostname:
        raise UptimeError("health URL must contain a hostname")
    if parsed.query or parsed.fragment:
        raise UptimeError("health URL must not contain query or fragment components")
    if parsed.port not in (None, 443):
        raise UptimeError("health URL must use the normal HTTPS port 443, not a raw service/management port")
    if parsed.path in ("", "/"):
        raise UptimeError("health URL must target a dedicated application health path such as /healthz")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise UptimeError("health URL must be externally reachable, not localhost/.local")

    hostname_kind = "dns"
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        hostname_kind = "ip"
        if not address.is_global:
            raise UptimeError("health URL literal IP must be globally routable")

    canonical = parsed.geturl()
    return HealthTarget(
        fingerprint_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        hostname_kind=hostname_kind,
    )


def _require_policy(interval_seconds: int, timeout_seconds: int) -> None:
    if not POLICY["min_interval_seconds"] <= interval_seconds <= POLICY["max_interval_seconds"]:
        raise UptimeError(
            "external uptime interval must remain between "
            f"{POLICY['min_interval_seconds']} and {POLICY['max_interval_seconds']} seconds"
        )
    if not POLICY["min_timeout_seconds"] <= timeout_seconds <= POLICY["max_timeout_seconds"]:
        raise UptimeError(
            "external uptime timeout must remain between "
            f"{POLICY['min_timeout_seconds']} and {POLICY['max_timeout_seconds']} seconds"
        )

def build_plan(
    *,
    health_url: str,
    interval_seconds: int = POLICY["default_interval_seconds"],
    timeout_seconds: int = POLICY["default_timeout_seconds"],
) -> dict[str, object]:
    target = _public_target(health_url)
    _require_policy(interval_seconds, timeout_seconds)
    return {
        "operation": "plan",
        "target": {
            "kind": "public-application-health-endpoint",
            "scheme": "https",
            "hostname_kind": target.hostname_kind,
            "endpoint_fingerprint_sha256": target.fingerprint_sha256,
        },
        "monitor": {
            "method": "GET",
            "expected_status": 200,
            "authentication": "none",
            "follow_redirects": False,
            "interval_seconds": interval_seconds,
            "timeout_seconds": timeout_seconds,
            "provider_confirmation_retries_required": POLICY["provider_confirmation_retries_required"],
        },
        "notification": {
            "destination": "off-vps",
            "test_notification_required": True,
            "outage_alert_required": True,
            "recovery_notification_required": True,
        },
        "acceptance": {
            "max_alert_detection_seconds": POLICY["max_alert_detection_seconds"],
            "max_recovery_notification_seconds": POLICY["max_recovery_notification_seconds"],
            "crit015_v3_requires_whole_target_shutdown": True,
        },
        "provider_credentials_required": False,
        "network_request": False,
        "mutation": False,
    }


def _parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UptimeError(f"{label} must be ISO-8601 with timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise UptimeError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def build_evidence(
    *,
    proof_id: str,
    health_url: str,
    exercise_mode: str,
    notification_channel: str,
    provider_artifact_sha256: str,
    notification_test_received_at: str,
    outage_started_at: str,
    alert_received_at: str,
    service_restored_at: str,
    recovery_received_at: str,
    interval_seconds: int = POLICY["default_interval_seconds"],
    timeout_seconds: int = POLICY["default_timeout_seconds"],
) -> dict[str, object]:
    if not PROOF_ID_RE.fullmatch(proof_id):
        raise UptimeError("proof id must match [a-z0-9][a-z0-9._-]{2,63}")
    if exercise_mode not in EXERCISE_MODES:
        raise UptimeError(f"exercise mode must be one of: {', '.join(sorted(EXERCISE_MODES))}")
    if notification_channel not in CHANNELS:
        raise UptimeError(f"notification channel must be one of: {', '.join(sorted(CHANNELS))}")
    if not SHA256_RE.fullmatch(provider_artifact_sha256):
        raise UptimeError("provider artifact SHA-256 must be exactly 64 lowercase hexadecimal characters")

    plan = build_plan(
        health_url=health_url,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
    )

    notification_test = _parse_time(notification_test_received_at, "notification_test_received_at")
    outage_started = _parse_time(outage_started_at, "outage_started_at")
    alert_received = _parse_time(alert_received_at, "alert_received_at")
    service_restored = _parse_time(service_restored_at, "service_restored_at")
    recovery_received = _parse_time(recovery_received_at, "recovery_received_at")

    if notification_test > outage_started:
        raise UptimeError("notification_test_received_at must be at or before outage_started_at")
    if alert_received < outage_started:
        raise UptimeError("alert_received_at cannot be before outage_started_at")
    if service_restored < outage_started:
        raise UptimeError("service_restored_at cannot be before outage_started_at")
    if recovery_received < service_restored:
        raise UptimeError("recovery_received_at cannot be before service_restored_at")

    alert_latency = int((alert_received - outage_started).total_seconds())
    recovery_latency = int((recovery_received - service_restored).total_seconds())
    alert_within_policy = alert_latency <= POLICY["max_alert_detection_seconds"]
    recovery_within_policy = recovery_latency <= POLICY["max_recovery_notification_seconds"]
    alert_before_restore = alert_received <= service_restored
    total_host_loss_proven = exercise_mode == "whole-target-shutdown"
    crit015_v3_acceptance_candidate = (
        alert_within_policy and recovery_within_policy and alert_before_restore and total_host_loss_proven
    )

    target = plan["target"]
    assert isinstance(target, dict)
    return {
        "schema_version": 1,
        "proof_id": proof_id,
        "evidence_kind": "operator-attested-sanitized-summary",
        "public_safe": True,
        "target": {
            "kind": target["kind"],
            "scheme": target["scheme"],
            "endpoint_fingerprint_sha256": target["endpoint_fingerprint_sha256"],
            "health_url_retained": False,
        },
        "monitor": plan["monitor"],
        "notification": {
            "channel_type": notification_channel,
            "destination_off_vps": True,
            "test_notification_received_at": _iso(notification_test),
            "outage_alert_received": True,
            "recovery_notification_received": True,
            "provider_event_artifact_sha256": provider_artifact_sha256,
            "provider_event_artifact_reviewed": True,
        },
        "exercise": {
            "mode": exercise_mode,
            "outage_started_at": _iso(outage_started),
            "alert_received_at": _iso(alert_received),
            "service_restored_at": _iso(service_restored),
            "recovery_received_at": _iso(recovery_received),
            "alert_detection_seconds": alert_latency,
            "recovery_notification_seconds": recovery_latency,
            "alert_within_policy": alert_within_policy,
            "alert_before_service_restore": alert_before_restore,
            "recovery_within_policy": recovery_within_policy,
            "total_host_loss_proven": total_host_loss_proven,
        },
        "acceptance": {
            "crit015_v3_acceptance_candidate": crit015_v3_acceptance_candidate,
            "provider_event_or_ui_artifact_review_required": True,
            "raw_provider_logs_retained": False,
        },
    }


def _write_private_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    if path.exists() or path.is_symlink():
        raise UptimeError(f"refusing to overwrite existing uptime evidence: {path}")
    data = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise
    os.chmod(path, 0o600)


def record(args: argparse.Namespace) -> int:
    if args.confirm != CONFIRM_REQUIRED:
        raise UptimeError(f"record requires --confirm {CONFIRM_REQUIRED}")
    if args.provider_artifact_review_confirm != ARTIFACT_CONFIRM_REQUIRED:
        raise UptimeError(
            f"record requires --provider-artifact-review-confirm {ARTIFACT_CONFIRM_REQUIRED}"
        )
    evidence = build_evidence(
        proof_id=args.proof_id,
        health_url=args.health_url,
        exercise_mode=args.exercise_mode,
        notification_channel=args.notification_channel,
        provider_artifact_sha256=args.provider_artifact_sha256,
        notification_test_received_at=args.notification_test_received_at,
        outage_started_at=args.outage_started_at,
        alert_received_at=args.alert_received_at,
        service_restored_at=args.service_restored_at,
        recovery_received_at=args.recovery_received_at,
        interval_seconds=args.interval_seconds,
        timeout_seconds=args.timeout_seconds,
    )
    output = Path(args.evidence_dir).expanduser().resolve() / "external-uptime-evidence.json"
    _write_private_json(output, evidence)

    acceptance = evidence["acceptance"]
    assert isinstance(acceptance, dict)
    if acceptance["crit015_v3_acceptance_candidate"]:
        print("PASS CRIT-015 sanitized V3 evidence candidate (provider artifact hash recorded/reviewed)")
    else:
        print("PASS external uptime exercise captured (partial: CRIT-015 whole-target/timing acceptance not met)")
    exercise = evidence["exercise"]
    assert isinstance(exercise, dict)
    print(f"  total_host_loss_proven: {str(exercise['total_host_loss_proven']).lower()}")
    print(f"  alert_detection_seconds: {exercise['alert_detection_seconds']}")
    print(f"  recovery_notification_seconds: {exercise['recovery_notification_seconds']}")
    print("  health_url_retained: false")
    print("  raw_provider_logs_retained: false")
    print(f"  sanitized_evidence: {output}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Plan and sanitize evidence for the provider-neutral Solo VPS external uptime contract.")
    sub = root.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--health-url", required=True)
    common.add_argument("--interval-seconds", type=int, default=POLICY["default_interval_seconds"])
    common.add_argument("--timeout-seconds", type=int, default=POLICY["default_timeout_seconds"])

    sub.add_parser("plan", parents=[common], help="Print the reviewed monitor policy without network access or provider mutation.")

    evidence = sub.add_parser("record", parents=[common], help="Record a sanitized operator-attested external outage/recovery exercise.")
    evidence.add_argument("--proof-id", required=True)
    evidence.add_argument("--exercise-mode", required=True, choices=sorted(EXERCISE_MODES))
    evidence.add_argument("--notification-channel", required=True, choices=sorted(CHANNELS))
    evidence.add_argument("--provider-artifact-sha256", required=True)
    evidence.add_argument("--provider-artifact-review-confirm", required=True)
    evidence.add_argument("--notification-test-received-at", required=True)
    evidence.add_argument("--outage-started-at", required=True)
    evidence.add_argument("--alert-received-at", required=True)
    evidence.add_argument("--service-restored-at", required=True)
    evidence.add_argument("--recovery-received-at", required=True)
    evidence.add_argument("--confirm", required=True)
    evidence.add_argument("--evidence-dir", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "plan":
            print(json.dumps(build_plan(
                health_url=args.health_url,
                interval_seconds=args.interval_seconds,
                timeout_seconds=args.timeout_seconds,
            ), indent=2, sort_keys=True))
            print("provider_credentials_required: false")
            print("network_request: false")
            print("mutation: false")
            return 0
        return record(args)
    except (OSError, UptimeError) as exc:
        print(f"ERROR external uptime: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
