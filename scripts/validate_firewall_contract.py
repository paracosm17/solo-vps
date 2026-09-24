#!/usr/bin/env python3
"""Validate the M5 UFW verification parser contract without contacting a host."""

from __future__ import annotations

import pathlib
import re
import sys

import yaml


class ContractError(ValueError):
    pass


EXPECTED_TARGETS = sorted(["22/tcp", "80/tcp", "443/tcp"])

ALLOW_IN_FIXTURE = """\
Status: active

     To                         Action      From
     --                         ------      ----
[ 1] 22/tcp                     ALLOW IN    Anywhere
[ 2] 80/tcp                     ALLOW IN    Anywhere
[ 3] 443/tcp                    ALLOW IN    Anywhere
[ 4] 22/tcp (v6)                ALLOW IN    Anywhere (v6)
[ 5] 80/tcp (v6)                ALLOW IN    Anywhere (v6)
[ 6] 443/tcp (v6)               ALLOW IN    Anywhere (v6)
"""

ALLOW_PLAIN_FIXTURE = """\
Status: active

     To                         Action      From
     --                         ------      ----
[ 1] 22/tcp                     ALLOW       Anywhere
[ 2] 80/tcp                     ALLOW       Anywhere
[ 3] 443/tcp                    ALLOW       Anywhere
[ 4] 22/tcp (v6)                ALLOW       Anywhere (v6)
[ 5] 80/tcp (v6)                ALLOW       Anywhere (v6)
[ 6] 443/tcp (v6)               ALLOW       Anywhere (v6)
"""

OUTBOUND_FIXTURE = """\
Status: active
[ 1] 22/tcp                     ALLOW OUT   Anywhere
[ 2] 80/tcp                     ALLOW FWD   Anywhere
"""


def load_yaml(path: pathlib.Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"cannot read YAML {path}: {exc}") from exc


def extract_pattern(root: pathlib.Path) -> str:
    data = load_yaml(root / "ansible/roles/firewall/defaults/main.yml")
    if not isinstance(data, dict):
        raise ContractError("firewall defaults must be a mapping")
    pattern = data.get("solo_vps_firewall_ufw_inbound_allow_pattern")
    if not isinstance(pattern, str) or not pattern:
        raise ContractError("missing firewall inbound UFW status parser pattern")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ContractError(f"invalid firewall UFW status regex: {exc}") from exc
    return pattern


def parse_targets(pattern: str, text: str) -> list[str]:
    return sorted(set(re.findall(pattern, text)))


def validate_parser(pattern: str) -> None:
    if parse_targets(pattern, ALLOW_IN_FIXTURE) != EXPECTED_TARGETS:
        raise ContractError("UFW parser must accept numbered inbound `ALLOW IN` rows")
    if parse_targets(pattern, ALLOW_PLAIN_FIXTURE) != EXPECTED_TARGETS:
        raise ContractError("UFW parser must accept numbered inbound `ALLOW` rows")
    if parse_targets(pattern, OUTBOUND_FIXTURE):
        raise ContractError("UFW parser must never classify `ALLOW OUT/FWD` rows as inbound")


def validate_verify_task(root: pathlib.Path) -> None:
    path = root / "ansible/roles/firewall/tasks/verify.yml"
    text = path.read_text(encoding="utf-8")
    if text.endswith("\n\n"):
        raise ContractError("firewall verifier must not contain a trailing blank line rejected by yamllint")

    required = [
        "regex_findall(solo_vps_firewall_ufw_inbound_allow_pattern)",
        "expected_ufw_allow_targets",
        "observed_ufw_allow_targets",
        "Report current host exposure evidence before enforcing it",
        "wildcard_tcp_listeners_outside_expected_edge",
        "tcp_listener_evidence",
        "-lntp",
    ]
    for token in required:
        if token not in text:
            raise ContractError(f"firewall verifier is missing runtime evidence contract: {token}")

    forbidden = [
        "solo_vps_firewall_wildcard_tcp_ports | difference(solo_vps_firewall_expected_tcp_ports) | length == 0",
        "no unexpected wildcard TCP listener outside the expected SSH/edge port set",
    ]
    for token in forbidden:
        if token in text:
            raise ContractError(
                "M5 must not treat a listener as public exposure solely because it binds wildcard; "
                f"remove stale wildcard-listener enforcement: {token}"
            )

    debug_pos = text.index("Report current host exposure evidence before enforcing it")
    assert_pos = text.index("Verify the UFW host exposure baseline")
    if debug_pos > assert_pos:
        raise ContractError("firewall exposure evidence must be printed before the enforcing assert")


def validate_root(root: pathlib.Path) -> None:
    pattern = extract_pattern(root)
    validate_parser(pattern)
    validate_verify_task(root)


def main() -> int:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    try:
        validate_root(root)
    except (ContractError, OSError) as exc:
        print(f"ERROR firewall contract: {exc}", file=sys.stderr)
        return 2
    print("PASS firewall contract: exact UFW ingress is enforced; wildcard listeners remain diagnostic evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
