#!/usr/bin/env python3
"""Strict schema helpers for Grafana Cloud Metrics runtime credentials."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

REQUIRED_KEYS = ("PROMETHEUS_URL", "PROMETHEUS_USERNAME", "GRAFANA_CLOUD_METRICS_API_KEY")
ALL_KEYS = frozenset(REQUIRED_KEYS)
MAX_JSON_BYTES = 32 * 1024


class MetricsCredentialError(RuntimeError):
    """Raised when metrics credential material violates the supported contract."""


def _single_line(name: str, value: Any, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise MetricsCredentialError(f"{name} must be a string")
    if not value:
        raise MetricsCredentialError(f"{name} must not be empty")
    if len(value) > maximum:
        raise MetricsCredentialError(f"{name} is unexpectedly long")
    if any(char in value for char in ("\x00", "\r", "\n")):
        raise MetricsCredentialError(f"{name} must be a single-line value")
    return value


def _prometheus_url(value: Any) -> str:
    url = _single_line("PROMETHEUS_URL", value, maximum=2048)
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise MetricsCredentialError("PROMETHEUS_URL must use HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise MetricsCredentialError("PROMETHEUS_URL must be an HTTPS endpoint without embedded credentials")
    if parsed.query or parsed.fragment:
        raise MetricsCredentialError("PROMETHEUS_URL must not contain query parameters or a fragment")
    if not parsed.path.rstrip("/").endswith("/api/prom/push"):
        raise MetricsCredentialError("PROMETHEUS_URL must end with /api/prom/push")
    return url


def validate_payload(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise MetricsCredentialError("metrics credentials must be a JSON/YAML mapping")

    keys = set(payload)
    missing = sorted(set(REQUIRED_KEYS) - keys)
    unknown = sorted(keys - ALL_KEYS)
    if missing:
        raise MetricsCredentialError(f"missing required metrics credential keys: {', '.join(missing)}")
    if unknown:
        raise MetricsCredentialError(f"unknown metrics credential keys: {', '.join(unknown)}")

    username = _single_line("PROMETHEUS_USERNAME", payload["PROMETHEUS_USERNAME"], maximum=512)
    if not re.fullmatch(r"[0-9]+", username):
        raise MetricsCredentialError("PROMETHEUS_USERNAME must be the numeric Grafana Cloud Metrics user/instance ID")

    return {
        "PROMETHEUS_URL": _prometheus_url(payload["PROMETHEUS_URL"]),
        "PROMETHEUS_USERNAME": username,
        "GRAFANA_CLOUD_METRICS_API_KEY": _single_line(
            "GRAFANA_CLOUD_METRICS_API_KEY", payload["GRAFANA_CLOUD_METRICS_API_KEY"], maximum=8192
        ),
    }


def parse_json_bytes(raw: bytes) -> dict[str, str]:
    if len(raw) > MAX_JSON_BYTES:
        raise MetricsCredentialError("metrics credential payload exceeds 32 KiB")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MetricsCredentialError("metrics credential payload is not valid UTF-8 JSON") from exc
    return validate_payload(payload)


def canonical_json_bytes(payload: Any) -> bytes:
    validated = validate_payload(payload)
    return (json.dumps(validated, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
