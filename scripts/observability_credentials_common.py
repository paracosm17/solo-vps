#!/usr/bin/env python3
"""Strict schema helpers for M24 managed log-backend runtime credentials."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

REQUIRED_KEYS = ("LOKI_URL", "LOKI_USERNAME", "GRAFANA_CLOUD_API_KEY")
ALL_KEYS = frozenset(REQUIRED_KEYS)
MAX_JSON_BYTES = 32 * 1024


class ObservabilityCredentialError(RuntimeError):
    """Raised when observability credential material violates the M24 contract."""


def _single_line(name: str, value: Any, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise ObservabilityCredentialError(f"{name} must be a string")
    if not value:
        raise ObservabilityCredentialError(f"{name} must not be empty")
    if len(value) > maximum:
        raise ObservabilityCredentialError(f"{name} is unexpectedly long")
    if any(char in value for char in ("\x00", "\r", "\n")):
        raise ObservabilityCredentialError(f"{name} must be a single-line value")
    return value


def _loki_url(value: Any) -> str:
    url = _single_line("LOKI_URL", value, maximum=2048)
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ObservabilityCredentialError("LOKI_URL must use HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ObservabilityCredentialError("LOKI_URL must be an HTTPS endpoint without embedded credentials")
    if parsed.query or parsed.fragment:
        raise ObservabilityCredentialError("LOKI_URL must not contain query parameters or a fragment")
    if not parsed.path.endswith("/loki/api/v1/push"):
        raise ObservabilityCredentialError("LOKI_URL must end with /loki/api/v1/push")
    return url


def validate_payload(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ObservabilityCredentialError("observability credentials must be a JSON/YAML mapping")

    keys = set(payload)
    missing = sorted(set(REQUIRED_KEYS) - keys)
    unknown = sorted(keys - ALL_KEYS)
    if missing:
        raise ObservabilityCredentialError(
            f"missing required observability credential keys: {', '.join(missing)}"
        )
    if unknown:
        raise ObservabilityCredentialError(
            f"unknown observability credential keys: {', '.join(unknown)}"
        )

    return {
        "LOKI_URL": _loki_url(payload["LOKI_URL"]),
        "LOKI_USERNAME": _single_line("LOKI_USERNAME", payload["LOKI_USERNAME"], maximum=512),
        "GRAFANA_CLOUD_API_KEY": _single_line(
            "GRAFANA_CLOUD_API_KEY", payload["GRAFANA_CLOUD_API_KEY"], maximum=8192
        ),
    }


def parse_json_bytes(raw: bytes) -> dict[str, str]:
    if len(raw) > MAX_JSON_BYTES:
        raise ObservabilityCredentialError("observability credential payload exceeds 32 KiB")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObservabilityCredentialError(
            "observability credential payload is not valid UTF-8 JSON"
        ) from exc
    return validate_payload(payload)


def canonical_json_bytes(payload: Any) -> bytes:
    validated = validate_payload(payload)
    return (json.dumps(validated, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
