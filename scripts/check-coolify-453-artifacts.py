#!/usr/bin/env python3
"""Check/synchronize SHA-256 of exact Coolify v4.5.3 upstream release artifacts.

This is source-integrity tooling, not a substitute for disposable-VPS V3 evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.request import urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/coolify-release.yml"
TAG = "v4.5.3"
NAMES = ("docker-compose.yml", "docker-compose.prod.yml", ".env.production")
BASE = f"https://raw.githubusercontent.com/coollabsio/coolify/{TAG}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", action="store_true", help="synchronize upstream release checksums and fingerprint (review git diff afterwards)")
    args = parser.parse_args()

    text = MANIFEST.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if data.get("version") != "4.5.3" or data.get("upgrade_from", {}).get("version") != "4.5.0":
        parser.error("expected 4.5.3 target with 4.5.0 upgrade origin")
    if set(data.get("artifacts", {})) != set(NAMES):
        parser.error("unexpected release artifacts")

    differences = []
    for name in NAMES:
        with urlopen(f"{BASE}/{name}", timeout=30) as response:
            raw = response.read()
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        recorded = data["artifacts"][name]
        print(f"{name}: downloaded {digest}; manifest {recorded}")
        if digest != recorded:
            differences.append((name, recorded, digest))
    if not differences:
        print("PASS: all three upstream SHA-256 values match")
        return 0
    if not args.sync:
        print("FAIL: at least one checksum differs; review upstream changes and rerun with --sync only if expected")
        return 1

    for name, old, new in differences:
        pattern = rf"(?m)^(  {re.escape(name)}: ){re.escape(old)}$"
        text, count = re.subn(pattern, lambda m: m.group(1) + new, text)
        if count != 1:
            raise SystemExit(f"cannot uniquely update checksum for {name}")
        data["artifacts"][name] = new
    integration = {key: value for key, value in data.items() if key != "qualification"}
    fingerprint = "sha256:" + hashlib.sha256(json.dumps(integration, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    text, count = re.subn(r"(?m)^(  release_sha256: )sha256:[0-9a-f]{64}$", lambda m: m.group(1) + fingerprint, text)
    if count != 1:
        raise SystemExit("cannot uniquely update release fingerprint")
    MANIFEST.write_text(text, encoding="utf-8")
    print("SYNCED: checksums and integration fingerprint; REVIEW `git diff` before commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
