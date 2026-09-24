#!/usr/bin/env python3
"""Shared helpers for the repository SOPS + age policy."""

from __future__ import annotations

from pathlib import Path

AGE_RECIPIENT_PLACEHOLDER = "age1REPLACE_WITH_YOUR_PUBLIC_RECIPIENT"
SOPS_PATH_REGEX = r"(^|[\\/])secrets[\\/].*\.enc\.yaml$"
LEGACY_SOPS_PATH_REGEX = r"(^|/)secrets/.*\.enc\.yaml$"

_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32_VALUES = {char: index for index, char in enumerate(_BECH32_CHARSET)}


def _bech32_polymod(values: list[int]) -> int:
    generators = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    checksum = 1
    for value in values:
        top = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ value
        for index, generator in enumerate(generators):
            if (top >> index) & 1:
                checksum ^= generator
    return checksum


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(char) >> 5 for char in hrp] + [0] + [ord(char) & 31 for char in hrp]


def _convertbits(data: list[int], from_bits: int, to_bits: int, *, pad: bool) -> bytes:
    accumulator = 0
    bits = 0
    result = bytearray()
    max_value = (1 << to_bits) - 1
    max_accumulator = (1 << (from_bits + to_bits - 1)) - 1

    for value in data:
        if value < 0 or value >> from_bits:
            raise ValueError("invalid bech32 data value")
        accumulator = ((accumulator << from_bits) | value) & max_accumulator
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            result.append((accumulator >> bits) & max_value)

    if pad:
        if bits:
            result.append((accumulator << (to_bits - bits)) & max_value)
    elif bits >= from_bits or ((accumulator << (to_bits - bits)) & max_value):
        raise ValueError("invalid bech32 padding")

    return bytes(result)


def validate_age_recipient(recipient: str) -> str:
    """Validate a lowercase age X25519 recipient and return it unchanged."""

    if not isinstance(recipient, str):
        raise ValueError("age recipient must be a string")
    if recipient != recipient.strip():
        raise ValueError("age recipient must not contain surrounding whitespace")
    if recipient.lower() != recipient:
        raise ValueError("age recipient must be lowercase")
    if not recipient.startswith("age1"):
        raise ValueError("age recipient must start with age1")
    if len(recipient) > 90:
        raise ValueError("age recipient is too long for bech32")

    separator = recipient.rfind("1")
    if separator <= 0 or separator + 7 > len(recipient):
        raise ValueError("invalid age recipient bech32 separator/checksum")

    hrp = recipient[:separator]
    if hrp != "age":
        raise ValueError("age recipient HRP must be 'age'")

    try:
        values = [_BECH32_VALUES[char] for char in recipient[separator + 1 :]]
    except KeyError as exc:
        raise ValueError("age recipient contains a non-bech32 character") from exc

    if _bech32_polymod(_bech32_hrp_expand(hrp) + values) != 1:
        raise ValueError("age recipient bech32 checksum is invalid")

    payload = _convertbits(values[:-6], 5, 8, pad=False)
    if len(payload) != 32:
        raise ValueError("age X25519 recipient payload must be 32 bytes")

    return recipient


def render_sops_config(recipient: str, *, path_regex: str = SOPS_PATH_REGEX) -> str:
    recipient = validate_age_recipient(recipient)
    return (
        "---\n"
        "creation_rules:\n"
        f"  - path_regex: '{path_regex}'\n"
        "    age:\n"
        f"      - {recipient}\n"
        "    mac_only_encrypted: false\n"
        "\n"
        "stores:\n"
        "  yaml:\n"
        "    indent: 2\n"
    )


def resolve_project_root(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"project root is not a directory: {root}")
    return root
