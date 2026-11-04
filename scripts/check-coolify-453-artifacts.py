#!/usr/bin/env python3
"""Check/synchronize SHA-256 of the manifest-selected Coolify artifacts.

Historical filename retained for compatibility. This is source-integrity tooling,
not a substitute for controlled VPS or production evidence.
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
NAMES = ("docker-compose.yml", "docker-compose.prod.yml", ".env.production")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", action="store_true", help="synchronize upstream release checksums and fingerprint (review git diff afterwards)")
    args = parser.parse_args()

    text = MANIFEST.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    version = data.get("version")
    origin = data.get("upgrade_from", {}).get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        parser.error("expected an exact manifest-selected Coolify target version")
    if not isinstance(origin, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", origin) or tuple(map(int, version.split("."))) <= tuple(map(int, origin.split("."))):
        parser.error("expected a supported origin older than the reviewed target")
    base = f"https://raw.githubusercontent.com/coollabsio/coolify/v{version}"
    if set(data.get("artifacts", {})) != set(NAMES):
        parser.error("unexpected release artifacts")

    differences = []
    for name in NAMES:
        with urlopen(f"{base}/{name}", timeout=30) as response:
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
