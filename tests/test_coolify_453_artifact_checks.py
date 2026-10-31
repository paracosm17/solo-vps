"""Offline contract checks for Coolify v4.5.3 upstream-artifact checks.

Use unittest: the repository's pinned QA toolchain does not include pytest.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/check-coolify-453-artifacts.py"
MANIFEST = REPO / "config/coolify-release.yml"


def _invoke(args: list[str], *, match: bool):
    namespace = runpy.run_path(str(SCRIPT))
    main = namespace["main"]
    raw_by_name = {name: f"test-content-for-{name}\n".encode() for name in namespace["NAMES"]}

    with tempfile.TemporaryDirectory(prefix="coolify-453-artifacts-") as directory:
        staging = Path(directory) / "coolify-release.yml"
        staging.write_bytes(MANIFEST.read_bytes())
        if match:
            text = staging.read_text(encoding="utf-8")
            data = yaml.safe_load(text)
            for name, raw in raw_by_name.items():
                old = data["artifacts"][name]
                updated = "sha256:" + hashlib.sha256(raw).hexdigest()
                text = text.replace(name + ": " + old, name + ": " + updated)
                data["artifacts"][name] = updated
            integration = {key: value for key, value in data.items() if key != "qualification"}
            fingerprint = "sha256:" + hashlib.sha256(
                json.dumps(integration, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            text = text.replace(data["qualification"]["release_sha256"], fingerprint)
            staging.write_text(text, encoding="utf-8")
        before = staging.read_bytes()

        class FakeResponse:
            def __init__(self, content: bytes):
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

        with patch.dict(main.__globals__, {"MANIFEST": staging, "urlopen": fake_urlopen}), \
                patch.object(sys, "argv", [str(SCRIPT), *args]):
            result = main()
        return result, before, staging.read_bytes(), raw_by_name


class TestCoolify453ArtifactChecks(unittest.TestCase):
    def test_discrepancy_fails_closed(self):
        result, before, after, _ = _invoke([], match=False)
        self.assertEqual(result, 1)
        self.assertEqual(after, before)

    def test_sync_refreshes_checksums_and_fingerprint(self):
        result, before, after, payloads = _invoke(["--sync"], match=False)
        self.assertEqual(result, 0)
        self.assertNotEqual(after, before)
        data = yaml.safe_load(after)
        for name, raw in payloads.items():
            self.assertEqual(data["artifacts"][name], "sha256:" + hashlib.sha256(raw).hexdigest())
        integration = {key: value for key, value in data.items() if key != "qualification"}
        expected = "sha256:" + hashlib.sha256(
            json.dumps(integration, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(data["qualification"]["release_sha256"], expected)

    def test_matching_sources_do_not_modify_manifest(self):
        result, before, after, _ = _invoke([], match=True)
        self.assertEqual(result, 0)
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
