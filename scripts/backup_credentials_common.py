#!/usr/bin/env python3
"""Shared strict schema helpers for M14 backup runtime credentials."""

from __future__ import annotations

import json
from typing import Any

REQUIRED_KEYS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "RESTIC_PASSWORD")
OPTIONAL_KEYS = ("AWS_SESSION_TOKEN",)
ALL_KEYS = frozenset(REQUIRED_KEYS + OPTIONAL_KEYS)
MAX_JSON_BYTES = 32 * 1024


class BackupCredentialError(RuntimeError):
    """Raised when backup credential material does not satisfy the M14 contract."""


def _validate_value(name: str, value: Any, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise BackupCredentialError(f"{name} must be a string")
    if not value:
        raise BackupCredentialError(f"{name} must not be empty")
    if len(value) > maximum:
        raise BackupCredentialError(f"{name} is unexpectedly long")
    if any(char in value for char in ("\x00", "\r", "\n")):
        raise BackupCredentialError(f"{name} must be a single-line value")
    return value


def validate_payload(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise BackupCredentialError("backup credentials must be a JSON/YAML mapping")

    keys = set(payload)
    missing = sorted(set(REQUIRED_KEYS) - keys)
    unknown = sorted(keys - ALL_KEYS)
    if missing:
        raise BackupCredentialError(f"missing required backup credential keys: {', '.join(missing)}")
    if unknown:
        raise BackupCredentialError(f"unknown backup credential keys: {', '.join(unknown)}")

    validated = {
        "AWS_ACCESS_KEY_ID": _validate_value(
            "AWS_ACCESS_KEY_ID", payload["AWS_ACCESS_KEY_ID"], maximum=512
        ),
        "AWS_SECRET_ACCESS_KEY": _validate_value(
            "AWS_SECRET_ACCESS_KEY", payload["AWS_SECRET_ACCESS_KEY"], maximum=2048
        ),
        "RESTIC_PASSWORD": _validate_value(
            "RESTIC_PASSWORD", payload["RESTIC_PASSWORD"], maximum=1024
        ),
    }
    if "AWS_SESSION_TOKEN" in payload:
        validated["AWS_SESSION_TOKEN"] = _validate_value(
            "AWS_SESSION_TOKEN", payload["AWS_SESSION_TOKEN"], maximum=8192
        )
    return validated


def parse_json_bytes(raw: bytes) -> dict[str, str]:
    if len(raw) > MAX_JSON_BYTES:
        raise BackupCredentialError("backup credential payload exceeds 32 KiB")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupCredentialError("backup credential payload is not valid UTF-8 JSON") from exc
    return validate_payload(payload)


def canonical_json_bytes(payload: Any) -> bytes:
    validated = validate_payload(payload)
    return (json.dumps(validated, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
