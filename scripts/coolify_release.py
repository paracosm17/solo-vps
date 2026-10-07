#!/usr/bin/env python3
"""Shared, offline loader for the reviewed Coolify release manifest."""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import re
import yaml

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "config/coolify-release.yml"
SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
ARTIFACT_NAMES = ("docker-compose.yml", "docker-compose.prod.yml", ".env.production")

def release_fingerprint(data: dict) -> str:
    """Bind evidence to integration data, excluding the evidence annotation itself."""
    integration = {key: value for key, value in data.items() if key != 'qualification'}
    return 'sha256:' + hashlib.sha256(json.dumps(integration, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def validate_manifest(data: object) -> dict:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Coolify release manifest requires schema_version: 1")
    origin = data.get('upgrade_from')
    if not isinstance(origin, dict):
        raise ValueError('Coolify upgrade origin must be a mapping')
    for item in (data, origin, data.get("sentinel"), origin.get('sentinel')):
        if not isinstance(item, dict) or not isinstance(item.get("version"), str) or not SEMVER.fullmatch(item["version"]):
            raise ValueError("Coolify target, origin and Sentinel require exact semantic versions")
        if item.get("registry") not in ("docker.io", "ghcr.io"):
            raise ValueError("release images must use an official reviewed registry")
    if not isinstance(origin['sentinel'].get('accept_target', False), bool):
        raise ValueError('origin Sentinel accept_target must be a boolean')
    if data["version"] == data["upgrade_from"]["version"]:
        raise ValueError("upgrade origin must differ from target")
    if tuple(map(int, data["version"].split("."))) <= tuple(map(int, data["upgrade_from"]["version"].split("."))):
        raise ValueError("reviewed upgrade target must be newer than its origin; downgrade is unsupported")
    for item in (data, data["upgrade_from"]):
        if item.get("realtime") not in ("embedded", "separate"):
            raise ValueError("release must describe its realtime topology")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(ARTIFACT_NAMES) or not all(isinstance(v, str) and SHA256.fullmatch(v) for v in artifacts.values()):
        raise ValueError("all three release artifacts require committed SHA256 checksums")
    if not SHA256.fullmatch(str(data["sentinel"].get("image_id_x86_64", ""))):
        raise ValueError("Sentinel requires reviewed x86_64 content identity")
    if not SHA256.fullmatch(str(data['upgrade_from']['sentinel'].get('image_id_x86_64', ''))):
        raise ValueError('origin Sentinel requires reviewed x86_64 content identity')
    qualification = data.get("qualification")
    if not isinstance(qualification, dict) or not isinstance(qualification.get("level"), str) or not isinstance(qualification.get("evidence"), str):
        raise ValueError("release qualification and evidence are required")
    if qualification.get('release_sha256') != release_fingerprint(data):
        raise ValueError('release qualification must be renewed for the exact integration fingerprint')
    return data

def load_release(path: Path = DEFAULT_MANIFEST) -> dict:
    return validate_manifest(yaml.safe_load(path.read_text(encoding="utf-8")))

def variables(data: dict) -> dict:
    """Resolve the existing Ansible variable contract without evaluating Jinja."""
    data = validate_manifest(data)
    base = f"https://raw.githubusercontent.com/coollabsio/coolify/v{data['version']}"
    return {
        "solo_vps_coolify_version": data["version"],
        "solo_vps_coolify_previous_supported_version": data["upgrade_from"]["version"],
        "solo_vps_coolify_expected_image": f"{data['registry']}/coollabsio/coolify:{data['version']}",
        "solo_vps_coolify_previous_expected_image": f"{data['upgrade_from']['registry']}/coollabsio/coolify:{data['upgrade_from']['version']}",
        "solo_vps_coolify_release_evidence": data["qualification"]["level"],
        "solo_vps_coolify_sentinel_version": data["sentinel"]["version"],
        "solo_vps_coolify_sentinel_image": f"{data['sentinel']['registry']}/coollabsio/sentinel:{data['sentinel']['version']}",
        "solo_vps_coolify_sentinel_image_id_x86_64": data["sentinel"]["image_id_x86_64"],
        "solo_vps_coolify_release_artifacts": [{"name": name, "url": f"{base}/{name}", "checksum": data["artifacts"][name]} for name in ARTIFACT_NAMES],
    }

def load_defaults(path: Path) -> dict:
    defaults = yaml.safe_load(path.read_text(encoding="utf-8"))
    aliases = {
        'solo_vps_coolify_version': '{{ solo_vps_coolify_release.version }}',
        'solo_vps_coolify_previous_supported_version': '{{ solo_vps_coolify_release.upgrade_from.version }}',
        'solo_vps_coolify_expected_image': '{{ solo_vps_coolify_release.registry }}/coollabsio/coolify:{{ solo_vps_coolify_image_tag }}',
        'solo_vps_coolify_previous_expected_image': '{{ solo_vps_coolify_release.upgrade_from.registry }}/coollabsio/coolify:{{ solo_vps_coolify_previous_supported_version }}',
        'solo_vps_coolify_sentinel_version': '{{ solo_vps_coolify_release.sentinel.version }}',
        'solo_vps_coolify_sentinel_image': '{{ solo_vps_coolify_release.sentinel.registry }}/coollabsio/sentinel:{{ solo_vps_coolify_sentinel_version }}',
        'solo_vps_coolify_sentinel_image_id_x86_64': '{{ solo_vps_coolify_release.sentinel.image_id_x86_64 }}',
        'solo_vps_coolify_release_evidence': '{{ solo_vps_coolify_release.qualification.level }}',
    }
    for key, expression in aliases.items():
        if defaults.get(key) != expression:
            raise ValueError(f'{key} must derive from the shared release manifest')
    artifacts = defaults.get('solo_vps_coolify_release_artifacts', [])
    if len(artifacts) != len(ARTIFACT_NAMES) or {a.get('name') for a in artifacts} != set(ARTIFACT_NAMES):
        raise ValueError('role must consume exactly the three manifest artifacts')
    for artifact in artifacts:
        name = artifact.get('name')
        if name not in ARTIFACT_NAMES or artifact.get('checksum') != "{{ solo_vps_coolify_release.artifacts['" + name + "'] }}":
            raise ValueError('role artifact checksums must derive from the shared release manifest')
        if artifact.get('url') != '{{ solo_vps_coolify_release_base_url }}/' + name:
            raise ValueError('role artifact URLs must derive from the shared release tag')
    return {**defaults, **variables(load_release(path.parents[4] / "config/coolify-release.yml"))}
