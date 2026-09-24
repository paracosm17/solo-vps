#!/usr/bin/env python3
"""Validate the static Solo VPS hello-app container contract."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys


def fail(message: str) -> None:
    raise SystemExit(f"ERROR example app contract: {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("example_dir", type=pathlib.Path)
    args = parser.parse_args()

    root = args.example_dir
    dockerfile = root / "Dockerfile"
    app = root / "app.py"
    tests = root / "test_app.py"

    for path in (dockerfile, app, tests):
        if not path.is_file():
            fail(f"missing required file: {path}")

    text = dockerfile.read_text(encoding="utf-8")
    from_lines = [line.strip() for line in text.splitlines() if line.strip().upper().startswith("FROM ")]
    if len(from_lines) != 1:
        fail("Dockerfile must contain exactly one FROM instruction")

    base_image = from_lines[0].split(maxsplit=1)[1].strip()
    if ":latest" in base_image or ":" not in base_image:
        fail("Dockerfile base image must use an explicit non-latest tag")

    required_snippets = (
        "USER 65532:65532",
        "EXPOSE 8080",
        "HEALTHCHECK ",
        "http://127.0.0.1:8080/healthz",
        'CMD ["python", "/app/app.py"]',
    )
    for snippet in required_snippets:
        if snippet not in text:
            fail(f"Dockerfile is missing required contract: {snippet}")

    if re.search(r"(?im)^\s*(ADD|COPY)\s+.*test_app\.py", text):
        fail("Dockerfile must not copy test_app.py into the runtime image")

    compose_files = list(root.glob("*compose*.yml")) + list(root.glob("*compose*.yaml"))
    if compose_files:
        fail("hello-app must not add a Compose/host-port deployment layer")

    app_text = app.read_text(encoding="utf-8")
    if "APP_PORT: Final = 8080" not in app_text:
        fail("application port contract must remain fixed at 8080")
    if 'self.path == "/healthz"' not in app_text:
        fail("application must implement /healthz")

    print("PASS example app static contract")


if __name__ == "__main__":
    main()
