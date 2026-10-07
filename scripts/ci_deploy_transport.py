#!/usr/bin/env python3
"""Plan the restricted SSH tunnel used by GitHub-hosted deploy jobs.

This helper is deliberately plan-only. It does not mutate sshd, create users,
open a network connection, or read private keys. The generated contract is the
source of truth for the next M11 transport implementation/proof.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import pathlib
import re
import shlex
import sys
from dataclasses import dataclass


DEPLOY_USER = "solo-vps-ci"
REMOTE_API_HOST = "127.0.0.1"
REMOTE_API_PORT = 8000
RUNNER_API_HOST = "127.0.0.1"
RUNNER_API_PORT = 18000
RUNNER_API_BASE_URL = f"http://{RUNNER_API_HOST}:{RUNNER_API_PORT}/api/v1"

USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
DNS_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
PUBLIC_KEY_RE = re.compile(
    r"^(ssh-ed25519)[ \t]+([A-Za-z0-9+/=]+)(?:[ \t]+.*)?$"
)


class TransportError(ValueError):
    """Raised when an input would weaken or invalidate the tunnel contract."""


def validate_server_host(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TransportError("server host must be a non-empty value without surrounding whitespace")
    if any(char.isspace() for char in value):
        raise TransportError("server host must not contain whitespace")
    if any(char in value for char in "/:@[]"):
        raise TransportError("server host must be a bare IPv4/IPv6-free DNS name or IPv4 address")

    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        if len(value) > 253 or any(not DNS_LABEL_RE.fullmatch(label) for label in value.split(".")):
            raise TransportError("server host must be a lowercase DNS name or IPv4 address")
        return value

    if parsed.version != 4:
        raise TransportError("the current M11 tunnel contract accepts IPv4 server endpoints only")
    if parsed.is_unspecified or parsed.is_multicast:
        raise TransportError("server host must be a routable/unicast IPv4 endpoint")
    return value


def load_public_key(path: pathlib.Path) -> str:
    try:
        value = path.expanduser().read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise TransportError(f"cannot read deployment public key {path}: {exc}") from exc
    if "\n" in value or "\r" in value:
        raise TransportError("deployment public-key file must contain exactly one OpenSSH public key")
    match = PUBLIC_KEY_RE.fullmatch(value)
    if not match:
        raise TransportError("deployment key must be one Ed25519 OpenSSH public key; never provide a private key")
    return value


def authorized_key_line(public_key: str) -> str:
    if not PUBLIC_KEY_RE.fullmatch(public_key):
        raise TransportError("invalid deployment public key")
    return (
        f'restrict,port-forwarding,permitopen="{REMOTE_API_HOST}:{REMOTE_API_PORT}" '
        f"{public_key}"
    )


def sshd_match_block(user: str = DEPLOY_USER) -> str:
    if not USER_RE.fullmatch(user):
        raise TransportError("invalid deployment SSH account name")
    return "\n".join(
        [
            f"Match User {user}",
            "    PasswordAuthentication no",
            "    KbdInteractiveAuthentication no",
            "    PubkeyAuthentication yes",
            "    AuthenticationMethods publickey",
            "    AllowAgentForwarding no",
            "    AllowTcpForwarding local",
            "    AllowStreamLocalForwarding no",
            "    GatewayPorts no",
            f"    PermitOpen {REMOTE_API_HOST}:{REMOTE_API_PORT}",
            "    PermitListen none",
            "    PermitTTY no",
            "    PermitTunnel no",
            "    PermitUserRC no",
            "    X11Forwarding no",
            "    MaxSessions 0",
        ]
    )


def runner_ssh_argv(server_host: str, user: str = DEPLOY_USER) -> list[str]:
    host = validate_server_host(server_host)
    if not USER_RE.fullmatch(user):
        raise TransportError("invalid deployment SSH account name")
    return [
        "ssh",
        "-F",
        "/dev/null",
        "-N",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "PreferredAuthentications=publickey",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "IdentityFile=$RUNNER_TEMP/solo-vps-ci-deploy-key",
        "-o",
        "UserKnownHostsFile=$RUNNER_TEMP/solo-vps-known_hosts",
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "HostKeyAlgorithms=ssh-ed25519",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-L",
        f"{RUNNER_API_HOST}:{RUNNER_API_PORT}:{REMOTE_API_HOST}:{REMOTE_API_PORT}",
        f"{user}@{host}",
    ]


def shell_join_preserving_runner_temp(argv: list[str]) -> str:
    # shlex.quote would single-quote $RUNNER_TEMP and prevent expansion. Quote
    # every other token normally and keep the two intended runner-temp paths in
    # double quotes so the workflow example is directly usable.
    rendered: list[str] = []
    for token in argv:
        if token.startswith("IdentityFile=$RUNNER_TEMP/") or token.startswith("UserKnownHostsFile=$RUNNER_TEMP/"):
            key, value = token.split("=", 1)
            rendered.append(f'{key}="{value}"')
        else:
            rendered.append(shlex.quote(token))
    return " ".join(rendered)


@dataclass(frozen=True)
class TransportPlan:
    server_host: str
    public_key: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "PASS",
            "transport": "restricted-ssh-local-forward",
            "server_host": self.server_host,
            "deploy_user": DEPLOY_USER,
            "remote_api": f"{REMOTE_API_HOST}:{REMOTE_API_PORT}",
            "runner_api_base_url": RUNNER_API_BASE_URL,
            "authorized_keys_line": authorized_key_line(self.public_key),
            "sshd_match_block": sshd_match_block(),
            "runner_ssh_argv": runner_ssh_argv(self.server_host),
            "github_environment": "production",
            "github_environment_secrets": [
                "SOLO_VPS_DEPLOY_SSH_KEY",
                "COOLIFY_API_TOKEN",
            ],
            "github_environment_variables": [
                "SOLO_VPS_DEPLOY_HOST",
                "SOLO_VPS_SSH_KNOWN_HOSTS",
                "COOLIFY_RESOURCE_UUID",
            ],
            "mutation": "none; plan-only source contract",
        }


def build_plan(server_host: str, public_key_file: pathlib.Path) -> TransportPlan:
    return TransportPlan(
        server_host=validate_server_host(server_host),
        public_key=load_public_key(public_key_file),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan the M11 restricted SSH tunnel from a GitHub-hosted runner to loopback Coolify API."
    )
    parser.add_argument("--server-host", required=True)
    parser.add_argument("--public-key-file", required=True, type=pathlib.Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        plan = build_plan(args.server_host, args.public_key_file)
    except TransportError as exc:
        print(f"ERROR CI deploy transport: {exc}", file=sys.stderr)
        return 2

    data = plan.as_dict()
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0

    print("PASS CI deploy transport plan: restricted SSH local-forward")
    print(f"  server_host: {plan.server_host}")
    print(f"  deploy_user: {DEPLOY_USER}")
    print(f"  remote_api: {REMOTE_API_HOST}:{REMOTE_API_PORT}")
    print(f"  runner_api_base_url: {RUNNER_API_BASE_URL}")
    print("  authorized_keys_line:")
    print(f"    {authorized_key_line(plan.public_key)}")
    print("  sshd_match_block:")
    for line in sshd_match_block().splitlines():
        print(f"    {line}")
    print("  runner_ssh_command:")
    print(f"    {shell_join_preserving_runner_temp(runner_ssh_argv(plan.server_host))}")
    print("  GitHub environment: production")
    print("  environment secrets: SOLO_VPS_DEPLOY_SSH_KEY, COOLIFY_API_TOKEN")
    print("  environment vars: SOLO_VPS_DEPLOY_HOST, SOLO_VPS_SSH_KNOWN_HOSTS, COOLIFY_RESOURCE_UUID")
    print("  mutation: none; this helper only defines the transport contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
