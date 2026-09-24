#!/usr/bin/env python3
"""Validate the non-secret M14 backup policy and repository metadata contract."""

from __future__ import annotations

import argparse
import ipaddress
import pathlib
import re
import sys
from typing import Any
from urllib.parse import urlsplit

try:
    import yaml
except ModuleNotFoundError:
    print("ERROR backup policy: PyYAML is required.", file=sys.stderr)
    raise SystemExit(127)

ENDPOINT_RE = re.compile(r"^https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?/?$")
BUCKET_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{1,61}[a-z0-9])$")
PREFIX_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._/-]*[a-z0-9])?$")
REGION_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
CREDENTIAL_KEY_RE = re.compile(r"(?:password|secret|token|credential|access[_-]?key)", re.I)
EXPECTED_SOURCES = ["/data/coolify"]
EXPECTED_EXCLUDES = ["/data/coolify/ssh/mux", "/data/coolify/databases", "/data/coolify/backups"]
EXPECTED_FORBIDDEN_PREFIXES = ["/var/lib/docker", "/var/lib/postgresql"]
EXPECTED_RETENTION = {
    "keep_last": 3,
    "keep_daily": 14,
    "keep_weekly": 8,
    "keep_monthly": 12,
    "keep_yearly": 3,
}
EXPECTED_TAG = "solo-vps"
EXPECTED_GROUP_BY = "host,tags"


class BackupPolicyError(ValueError):
    pass


def mapping(parent: dict[str, Any], key: str, path: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise BackupPolicyError(f"'{path}' must be a YAML mapping")
    return value


def text(parent: dict[str, Any], key: str, path: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value or value != value.strip():
        raise BackupPolicyError(f"'{path}' must be a non-empty string without surrounding whitespace")
    if "CHANGE_ME" in value.upper():
        raise BackupPolicyError(f"'{path}' still contains a CHANGE_ME placeholder")
    return value


def reject_credential_keys(value: Any, path: str = "backup") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if CREDENTIAL_KEY_RE.search(str(key)):
                raise BackupPolicyError(
                    f"'{path}.{key}' looks like credential material; public backup config is metadata-only"
                )
            reject_credential_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_credential_keys(child, f"{path}[{index}]")


def normalized_endpoint(endpoint: str) -> tuple[str, str]:
    if not ENDPOINT_RE.fullmatch(endpoint):
        raise BackupPolicyError("'backup.repository.endpoint' must be an HTTPS DNS/IPv4 origin without a path")
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https":
        raise BackupPolicyError("'backup.repository.endpoint' must use HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise BackupPolicyError("'backup.repository.endpoint' must not contain credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise BackupPolicyError("'backup.repository.endpoint' must be an origin only, without a path")
    if not parsed.hostname:
        raise BackupPolicyError("'backup.repository.endpoint' must contain a hostname")
    try:
        port = parsed.port
    except ValueError as exc:
        raise BackupPolicyError("'backup.repository.endpoint' contains an invalid TCP port") from exc
    if port is not None and not (1 <= port <= 65535):
        raise BackupPolicyError("'backup.repository.endpoint' contains an invalid TCP port")
    endpoint = endpoint.rstrip("/")
    return endpoint, parsed.hostname.rstrip(".").lower()


def obvious_same_host(endpoint_host: str, server_host: str, server_hostname: str) -> bool:
    candidates = {server_host.rstrip(".").lower(), server_hostname.rstrip(".").lower()}
    if endpoint_host in {"localhost", "localhost.localdomain"} or endpoint_host in candidates:
        return True
    try:
        ip = ipaddress.ip_address(endpoint_host)
    except ValueError:
        return False
    return ip.is_loopback or endpoint_host in candidates


def validate(config: Any, defaults: Any, *, allow_documentation_endpoint: bool = False) -> str:
    if not isinstance(config, dict):
        raise BackupPolicyError("config top-level value must be a mapping")
    if not isinstance(defaults, dict):
        raise BackupPolicyError("backup defaults top-level value must be a mapping")

    server = mapping(config, "server", "server")
    backup = mapping(config, "backup", "backup")
    reject_credential_keys(backup)
    repository = mapping(backup, "repository", "backup.repository")

    server_host = text(server, "host", "server.host")
    server_hostname = text(server, "hostname", "server.hostname")
    endpoint_raw = text(repository, "endpoint", "backup.repository.endpoint")
    bucket = text(repository, "bucket", "backup.repository.bucket")
    prefix = text(repository, "prefix", "backup.repository.prefix")
    region = text(repository, "region", "backup.repository.region")

    endpoint, endpoint_host = normalized_endpoint(endpoint_raw)
    if not allow_documentation_endpoint and (endpoint_host == "example.com" or endpoint_host.endswith(".example.com")):
        raise BackupPolicyError("'backup.repository.endpoint' still uses the documentation-only example.com domain")
    if obvious_same_host(endpoint_host, server_host, server_hostname):
        raise BackupPolicyError(
            "'backup.repository.endpoint' points to localhost or the configured VPS; an off-site repository must be independent"
        )
    if not BUCKET_RE.fullmatch(bucket) or ".." in bucket:
        raise BackupPolicyError("'backup.repository.bucket' must be a conservative DNS-compatible bucket name")
    if not PREFIX_RE.fullmatch(prefix) or "//" in prefix or any(part in {".", ".."} for part in prefix.split("/")):
        raise BackupPolicyError("'backup.repository.prefix' must be a safe relative object-key prefix")
    if not REGION_RE.fullmatch(region):
        raise BackupPolicyError("'backup.repository.region' must be a lowercase region identifier")

    sources = defaults.get("solo_vps_backup_sources")
    excludes = defaults.get("solo_vps_backup_excludes")
    forbidden = defaults.get("solo_vps_backup_forbidden_source_prefixes")
    retention = defaults.get("solo_vps_backup_retention")
    tag = defaults.get("solo_vps_backup_snapshot_tag")
    group_by = defaults.get("solo_vps_backup_group_by")

    if sources != EXPECTED_SOURCES:
        raise BackupPolicyError(f"backup sources drifted from the reviewed core scope: expected {EXPECTED_SOURCES}")
    if excludes != EXPECTED_EXCLUDES:
        raise BackupPolicyError(f"backup exclusions drifted from the reviewed core scope: expected {EXPECTED_EXCLUDES}")
    if forbidden != EXPECTED_FORBIDDEN_PREFIXES:
        raise BackupPolicyError("forbidden live-storage source prefixes drifted from the reviewed policy")
    if retention != EXPECTED_RETENTION:
        raise BackupPolicyError(f"retention policy drifted: expected {EXPECTED_RETENTION}")
    if tag != EXPECTED_TAG or group_by != EXPECTED_GROUP_BY:
        raise BackupPolicyError("snapshot tag/grouping policy drifted from 'solo-vps' + 'host,tags'")

    for source in sources:
        for prefix_path in forbidden:
            if source == prefix_path or source.startswith(prefix_path + "/"):
                raise BackupPolicyError(f"unsafe live-storage backup source: {source}")

    return f"s3:{endpoint}/{bucket}/{prefix}/{server_hostname}"


def validate_readiness_sources(role_dir: pathlib.Path) -> None:
    readiness = (role_dir / "tasks" / "readiness.yml").read_text(encoding="utf-8")
    playbook = (role_dir.parents[1] / "playbooks" / "backup-readiness.yml").read_text(encoding="utf-8")

    allowed_modules = {
        "ansible.builtin.import_tasks",
        "ansible.builtin.stat",
        "ansible.builtin.assert",
        "ansible.builtin.debug",
    }
    modules = set(
        re.findall(r"^\s+(ansible\.builtin\.[a-zA-Z0-9_]+):\s*$", readiness, flags=re.MULTILINE)
    )
    unexpected = sorted(modules - allowed_modules)
    if unexpected:
        raise BackupPolicyError(f"backup readiness contains non-read-only modules: {unexpected}")

    for marker in ("restic init", "restic backup", "restic forget", "restic prune", "ansible.builtin.uri:", "ansible.builtin.get_url:"):
        if marker in readiness:
            raise BackupPolicyError(f"backup readiness contains out-of-scope repository behavior: {marker}")

    required_report_markers = (
        "repository_contacted: false",
        "repository_initialized: false",
        "backup_scheduled: false",
        "snapshot_verified: false",
        "restore_verified: false",
    )
    for report_marker in required_report_markers:
        if report_marker not in readiness:
            raise BackupPolicyError(f"backup readiness lost evidence boundary marker: {report_marker}")

    if "ansible.builtin.import_playbook: preflight.yml" not in playbook:
        raise BackupPolicyError("backup readiness playbook must run the normal preflight first")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=pathlib.Path)
    parser.add_argument("defaults", type=pathlib.Path)
    parser.add_argument(
        "--allow-documentation-endpoint",
        action="store_true",
        help="Allow the example.com endpoint only when validating the committed public example.",
    )
    return parser.parse_args()


def load_yaml(path: pathlib.Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BackupPolicyError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise BackupPolicyError(f"invalid YAML in {path}: {exc}") from exc


def main() -> int:
    args = parse_args()
    try:
        defaults = load_yaml(args.defaults)
        repository = validate(
            load_yaml(args.config),
            defaults,
            allow_documentation_endpoint=args.allow_documentation_endpoint,
        )
        validate_readiness_sources(args.defaults.parent.parent)
    except BackupPolicyError as exc:
        print(f"ERROR backup policy: {exc}", file=sys.stderr)
        return 2
    print(f"PASS backup policy: {repository}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
