"""Offline contract checks for the v4.5.3 upstream-artifact checksum helper."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy
import sys

import yaml


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/check-coolify-453-artifacts.py"
MANIFEST = REPO / "config/coolify-release.yml"


def _invoke(monkeypatch, tmp_path, args, *, match: bool):
    namespace = runpy.run_path(str(SCRIPT))
    main = namespace["main"]
    staging = tmp_path / "coolify-release.yml"
    staging.write_bytes(MANIFEST.read_bytes())
    raw_by_name = {name: f"test-content-for-{name}\n".encode() for name in namespace["NAMES"]}
    if match:
        text = staging.read_text()
        data = yaml.safe_load(text)
        for name, raw in raw_by_name.items():
            old = data["artifacts"][name]
            new = "sha256:" + hashlib.sha256(raw).hexdigest()
            text = text.replace(name + ": " + old, name + ": " + new)
            data["artifacts"][name] = new
        integration = {key: value for key, value in data.items() if key != "qualification"}
        digest = "sha256:" + hashlib.sha256(json.dumps(integration, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        text = text.replace(data["qualification"]["release_sha256"], digest)
        staging.write_text(text)
    original = staging.read_bytes()

    class FakeResponse:
        def __init__(self, content):
            self.content = content

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self.content

    def fake_urlopen(url, timeout):
        assert url.startswith("https://raw.githubusercontent.com/coollabsio/coolify/v4.5.3/")
        assert timeout == 30
        return FakeResponse(raw_by_name[url.rsplit("/", 1)[-1]])

    monkeypatch.setitem(main.__globals__, "MANIFEST", staging)
    monkeypatch.setitem(main.__globals__, "urlopen", fake_urlopen)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), *args])
    return main(), staging, original, raw_by_name


def test_discrepancy_fails_closed(monkeypatch, tmp_path):
    code, manifest, before, _ = _invoke(monkeypatch, tmp_path, [], match=False)
    assert code == 1
    assert manifest.read_bytes() == before


def test_sync_changes_all_checksums_and_refreshes_fingerprint(monkeypatch, tmp_path):
    code, manifest, before, payloads = _invoke(monkeypatch, tmp_path, ["--sync"], match=False)
    assert code == 0
    assert manifest.read_bytes() != before
    data = yaml.safe_load(manifest.read_text())
    for name, raw in payloads.items():
        assert data["artifacts"][name] == "sha256:" + hashlib.sha256(raw).hexdigest()
    integration = {key: value for key, value in data.items() if key != "qualification"}
    expected = "sha256:" + hashlib.sha256(json.dumps(integration, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert data["qualification"]["release_sha256"] == expected


def test_matching_sources_do_not_modify_manifest(monkeypatch, tmp_path):
    code, manifest, before, _ = _invoke(monkeypatch, tmp_path, [], match=True)
    assert code == 0
    assert manifest.read_bytes() == before
