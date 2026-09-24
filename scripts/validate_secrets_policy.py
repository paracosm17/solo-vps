#!/usr/bin/env python3
"""Static/local validation for the M13 SOPS + age repository policy."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

import yaml

from sops_policy import (
    AGE_RECIPIENT_PLACEHOLDER,
    SOPS_PATH_REGEX,
    resolve_project_root,
    validate_age_recipient,
)

_AGE_PRIVATE_IDENTITY_RE = re.compile(r"(?m)^AGE-SECRET-KEY-1[0-9A-Z]{40,}$")
_PRIVATE_KEY_BLOCKS = (
    ("-----BEGIN " + "OPENSSH PRIVATE KEY-----", "-----END " + "OPENSSH PRIVATE KEY-----"),
    ("-----BEGIN " + "RSA PRIVATE KEY-----", "-----END " + "RSA PRIVATE KEY-----"),
    ("-----BEGIN " + "EC PRIVATE KEY-----", "-----END " + "EC PRIVATE KEY-----"),
)
_ALLOWED_SECRET_PLAINTEXT = {
    Path("secrets/README.md"),
    Path("secrets/recipients/production.example.txt"),
}
_REQUIRED_GITIGNORE_LINES = {
    "secrets/**",
    "!secrets/**/",
    "!secrets/**/*.enc.yaml",
    "!secrets/README.md",
    "!secrets/recipients/production.example.txt",
    "/.sops.yaml",
    "/secrets/recipients/production.txt",
    "*.agekey",
    "**/.config/sops/age/keys.txt",
    "**/sops/age/keys.txt",
}


def _load_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot parse YAML {path}: {exc}") from exc


def _validate_policy_mapping(data: object, *, expected_recipient: str) -> None:
    if not isinstance(data, dict):
        raise ValueError("SOPS policy must be a YAML mapping")
    if set(data) != {"creation_rules", "stores"}:
        raise ValueError("SOPS policy top-level keys must be exactly creation_rules and stores")

    rules = data.get("creation_rules")
    if not isinstance(rules, list) or len(rules) != 1 or not isinstance(rules[0], dict):
        raise ValueError("SOPS policy must contain exactly one creation rule")
    rule = rules[0]
    if set(rule) != {"path_regex", "age", "mac_only_encrypted"}:
        raise ValueError("creation rule must contain only path_regex, age, mac_only_encrypted")
    if rule.get("path_regex") != SOPS_PATH_REGEX:
        raise ValueError("creation rule path_regex does not match the project secrets contract")
    if rule.get("mac_only_encrypted") is not False:
        raise ValueError("mac_only_encrypted must be false")
    age = rule.get("age")
    if age != [expected_recipient]:
        raise ValueError("creation rule must contain exactly the expected age recipient")

    stores = data.get("stores")
    if stores != {"yaml": {"indent": 2}}:
        raise ValueError("stores policy must be exactly yaml.indent=2")


def _validate_encrypted_yaml(path: Path, *, expected_recipient: str | None) -> None:
    data = _load_yaml(path)
    if not isinstance(data, dict):
        raise ValueError(f"encrypted secret must be a YAML mapping: {path}")
    sops = data.get("sops")
    if not isinstance(sops, dict):
        raise ValueError(f"*.enc.yaml file lacks SOPS metadata: {path}")
    age_entries = sops.get("age")
    if not isinstance(age_entries, list) or not age_entries:
        raise ValueError(f"SOPS metadata lacks age recipients: {path}")
    recipients = {entry.get("recipient") for entry in age_entries if isinstance(entry, dict)}
    recipients.discard(None)
    if not recipients:
        raise ValueError(f"SOPS metadata contains no age recipient values: {path}")
    for recipient in recipients:
        if not isinstance(recipient, str):
            raise ValueError(f"SOPS metadata contains a non-string age recipient: {path}")
        validate_age_recipient(recipient)
    if expected_recipient is not None and expected_recipient not in recipients:
        raise ValueError(f"encrypted secret does not include the configured production recipient: {path}")
    if not isinstance(sops.get("mac"), str) or not sops["mac"].startswith("ENC["):
        raise ValueError(f"SOPS metadata lacks encrypted MAC: {path}")


def _scan_private_markers(root: Path) -> None:
    excluded_parts = {".git", "__pycache__", ".venv", "venv"}
    for path in root.rglob("*"):
        if not path.is_file() or any(part in excluded_parts for part in path.parts):
            continue
        try:
            if path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        if _AGE_PRIVATE_IDENTITY_RE.search(text):
            raise ValueError(f"age private identity found in {path.relative_to(root)}")

        for begin, end in _PRIVATE_KEY_BLOCKS:
            if begin in text and end in text:
                raise ValueError(f"private-key block found in {path.relative_to(root)}")


def validate(
    root: Path,
    *,
    policy_path: Path | None = None,
    recipient_path: Path | None = None,
) -> None:
    example_path = root / ".sops.yaml.example"
    _validate_policy_mapping(_load_yaml(example_path), expected_recipient=AGE_RECIPIENT_PLACEHOLDER)

    recipient_example = root / "secrets" / "recipients" / "production.example.txt"
    if recipient_example.read_text(encoding="utf-8") != f"{AGE_RECIPIENT_PLACEHOLDER}\n":
        raise ValueError("production.example.txt must contain only the documented public placeholder")

    gitignore_lines = {
        line.strip()
        for line in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing_gitignore = sorted(_REQUIRED_GITIGNORE_LINES - gitignore_lines)
    if missing_gitignore:
        raise ValueError(f".gitignore is missing legacy safety lines: {', '.join(missing_gitignore)}")

    # Generated operator policy is external state. Checkout-local copies are accepted only
    # as legacy files long enough for `make init`/manual migration, never as active policy.
    live_policy = root / ".sops.yaml"
    live_recipient = root / "secrets" / "recipients" / "production.txt"
    if live_policy.exists() or live_recipient.exists():
        raise ValueError(
            "checkout-local .sops.yaml/production.txt is legacy operator state; "
            "move it outside the source checkout before validation"
        )

    configured_recipient: str | None = None
    if policy_path is not None or recipient_path is not None:
        if policy_path is None or recipient_path is None:
            raise ValueError("external SOPS policy and recipient paths must be provided together")
        policy_path = policy_path.expanduser().resolve()
        recipient_path = recipient_path.expanduser().resolve()
        if policy_path.exists() != recipient_path.exists():
            raise ValueError("external SOPS policy and public recipient must exist together")
        if policy_path.exists():
            configured_recipient = recipient_path.read_text(encoding="utf-8").strip()
            validate_age_recipient(configured_recipient)
            _validate_policy_mapping(_load_yaml(policy_path), expected_recipient=configured_recipient)

    secrets_root = root / "secrets"
    for path in secrets_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative in _ALLOWED_SECRET_PLAINTEXT:
            continue
        if path.name.endswith(".enc.yaml"):
            _validate_encrypted_yaml(path, expected_recipient=configured_recipient)
            continue
        raise ValueError(f"plaintext or unsupported file is forbidden below secrets/: {relative}")

    # Avoid secret-bearing environment exports in tracked source. Public recipient variables are fine.
    env_secret_pattern = re.compile(r"\bSOPS_AGE_KEY\s*=")
    for path in (root / "scripts").glob("*.py"):
        if path.name == "validate_secrets_policy.py":
            continue
        text = path.read_text(encoding="utf-8")
        if env_secret_pattern.search(text):
            raise ValueError(f"tracked script assigns SOPS_AGE_KEY directly: {path.relative_to(root)}")

    _scan_private_markers(root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the M13 repository SOPS + age policy")
    parser.add_argument("root", nargs="?", default=".", help="project root")
    parser.add_argument("--policy", type=Path, default=None, help="external persistent SOPS policy")
    parser.add_argument("--recipient-file", type=Path, default=None, help="external persistent public recipient")
    args = parser.parse_args()

    try:
        root = resolve_project_root(args.root)
        validate(root, policy_path=args.policy, recipient_path=args.recipient_file)
    except (OSError, ValueError) as exc:
        print(f"ERROR secrets policy: {exc}", file=sys.stderr)
        return 2

    print("PASS secrets policy: source is free of private/plaintext material; external generated policy is valid when present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
