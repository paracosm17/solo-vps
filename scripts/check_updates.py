#!/usr/bin/env python3
"""Read-only release discovery; availability never authorizes installation."""
from __future__ import annotations

try:
    from scripts.coolify_release import load_release, load_defaults, variables
except ModuleNotFoundError:
    from coolify_release import load_release, load_defaults, variables
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import Request, urlopen
import yaml

REPOSITORIES = {"solo-vps": "paracosm17/solo-vps", "coolify": "coollabsio/coolify"}
VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")

def version(value: str) -> tuple[int, ...]:
    match = VERSION.fullmatch(value)
    if not match:
        raise ValueError("expected an exact semantic release version")
    return tuple(map(int, match.groups()))

def select_release(items: object) -> dict:
    if not isinstance(items, list):
        raise ValueError("GitHub releases response must be a list")
    releases = [r for r in items if isinstance(r, dict) and not r.get("draft") and isinstance(r.get("tag_name"), str) and VERSION.fullmatch(r["tag_name"])]
    stable = [r for r in releases if not r.get("prerelease")]
    if not releases:
        raise ValueError("no published exact-version releases found")
    item = max(stable or releases, key=lambda r: version(r["tag_name"]))
    return {"version": item["tag_name"], "prerelease": bool(item.get("prerelease"))}

def fetch_release(repository: str) -> dict:
    request = Request(f"https://api.github.com/repos/{repository}/releases?per_page=100", headers={"Accept": "application/vnd.github+json", "User-Agent": "solo-vps-update-check"})
    with urlopen(request, timeout=15) as response:
        body = response.read(2_000_001)
    if len(body) > 2_000_000:
        raise ValueError("GitHub releases response exceeds the size limit")
    return select_release(json.loads(body))

def source_identity(root: Path) -> dict:
    def git(*args: str) -> str:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else ""
    revision = git("rev-parse", "HEAD")
    if not revision:
        return {"revision": None, "exact_release": None, "dirty": None,
                "error": "Git cannot inspect this checkout; source identity and cleanliness are unknown"}
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False)
    return {"revision": revision, "exact_release": git("describe", "--tags", "--exact-match"),
            "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None}

def report(root: Path, online: bool = False, component: str = "all", fetch=fetch_release) -> dict:
    release_manifest = load_release(root / "config/coolify-release.yml")
    manifest = variables(release_manifest)
    target = manifest["solo_vps_coolify_version"]
    version(target)
    result = {"network_request": online, "mutation": False, "source": source_identity(root), "coolify": {"reviewed_target": target, "reviewed_origin": manifest["solo_vps_coolify_previous_supported_version"], "evidence": manifest["solo_vps_coolify_release_evidence"], "installed_version": "not observed; run make coolify-upgrade-preflight"}, "upstream": {}}
    result['coolify'].update(evidence_record=release_manifest['qualification']['evidence'],
                             release_fingerprint=release_manifest['qualification']['release_sha256'])
    if online:
        for name, repo in REPOSITORIES.items():
            if component != "all" and component != name:
                continue
            release = fetch(repo)
            release["release_notes"] = f"https://github.com/{repo}/releases/tag/{release['version']}"
            if name == "coolify":
                release["newer_than_reviewed_target"] = version(release["version"]) > version(target)
                release["matches_reviewed_target"] = version(release["version"]) == version(target)
            else:
                current = result["source"]["exact_release"] or ""
                release["newer_than_exact_source_release"] = version(release["version"]) > version(current) if VERSION.fullmatch(current) else None
            result["upstream"][name] = release
    result["next_steps"] = ["Read release notes and evidence before changing source or runtime.", "make source-update-prepare RELEASE_VERSION=<published exact tag>", "make coolify-upgrade-preflight; then the explicit upgrade/resume command."]
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--component", choices=("all", *REPOSITORIES), default="all")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        value = report(args.root, args.online, args.component)
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        print(f"ERROR update discovery: {exc}; no source/runtime changes performed", file=sys.stderr)
        return 2
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
