#!/usr/bin/env python3
"""Validate the source-only M24 workstation-to-VPS Grafana Cloud Logs credential boundary."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


class ContractError(RuntimeError):
    pass


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        raise ContractError(f"{where} missing observability credential contract: {needle}")


def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        raise ContractError(f"{where} contains forbidden observability credential behavior: {needle}")


def validate(root: Path) -> None:
    root = root.resolve()
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    common = (root / "scripts/observability_credentials_common.py").read_text(encoding="utf-8")
    bundle = (root / "scripts/observability_secret_bundle.py").read_text(encoding="utf-8")
    installer = (root / "scripts/install_observability_credentials.py").read_text(encoding="utf-8")
    windows_init = (root / "scripts/windows/init-observability-secrets.ps1").read_text(encoding="utf-8")
    windows_check = (root / "scripts/windows/test-observability-secrets.ps1").read_text(encoding="utf-8")
    windows_push = (root / "scripts/windows/push-observability-secrets.ps1").read_text(encoding="utf-8")
    docs = (root / "docs/operations/observability.md").read_text(encoding="utf-8")
    docs_ru = (root / "docs/operations/observability.ru.md").read_text(encoding="utf-8")
    secrets_docs = (root / "docs/secrets-sops-age.md").read_text(encoding="utf-8")

    for needle in (
        "OBSERVABILITY_SECRET_FILE ?= $(SOLO_VPS_SECRET_DIR)/observability.enc.yaml",
        "observability-secrets-init:",
        "observability-secrets-check:",
        "observability-secrets-push:",
        "verify-observability-credentials:",
        "validate-observability-credentials:",
        "test-observability-credentials:",
    ):
        require(makefile, needle, "Makefile")

    for needle in (
        "LOKI_URL",
        "LOKI_USERNAME",
        "GRAFANA_CLOUD_API_KEY",
        "/loki/api/v1/push",
        "LOKI_URL must use HTTPS",
    ):
        require(common, needle, "scripts/observability_credentials_common.py")

    for needle in (
        'SOPS_FILENAME_OVERRIDE = "secrets/observability.enc.yaml"',
        "SOPS_AGE_KEY_FILE",
        "SSH stdin",
        "source checkout mutated: no",
        "secret-bearing stderr was suppressed",
        "refusing symlink observability ciphertext destination",
        "install_observability_credentials.py apply",
        "already exists; reusing it",
        "existing ciphertext replaced: no",
    ):
        require(bundle, needle, "scripts/observability_secret_bundle.py")

    for needle in (
        'DEFAULT_DIRECTORY = Path("/etc/solo-vps/observability")',
        '"grafana-cloud.json"',
        "os.chmod(directory, 0o700)",
        "os.chmod(destination, 0o600)",
        "refusing non-regular observability credential path",
        "plaintext printed: no",
        "Alloy service started: no",
        "Docker socket access granted: no",
        "telemetry sent: no",
        "_absolute_unresolved(args.path)",
    ):
        require(installer, needle, "scripts/install_observability_credentials.py")

    for text, where in (
        (windows_init, "scripts/windows/init-observability-secrets.ps1"),
        (windows_check, "scripts/windows/test-observability-secrets.ps1"),
        (windows_push, "scripts/windows/push-observability-secrets.ps1"),
    ):
        require(text, "LOCALAPPDATA", where)
        require(text, "observability.enc.yaml", where)
        require(text, "secret-bearing stderr was suppressed", where)
        forbid(text, "AGE-SECRET-KEY-", where)

    for needle in ("test-observability-secrets.ps1", "already exists; reusing it", "init-sops-policy.ps1 -StartFresh"):
        require(windows_init, needle, "scripts/windows/init-observability-secrets.ps1")

    for needle in (
        ".\\scripts\\windows\\init-observability-secrets.ps1",
        ".\\scripts\\windows\\test-observability-secrets.ps1",
        ".\\scripts\\windows\\push-observability-secrets.ps1",
        "make observability-secrets-init",
        "make observability-secrets-check",
        "make observability-secrets-push",
        "make verify-observability-credentials",
        "/etc/solo-vps/observability/grafana-cloud.json",
        "logs:write",
        "does not start Alloy",
        "does not grant Docker socket access",
        "-StartFresh",
        "archive\\workstation-secrets",
        "reuses it without overwriting it",
    ):
        require(docs, needle, "docs/operations/observability.md")

    for needle in ("-StartFresh", "archive\\workstation-secrets", "переиспользует без перезаписи"):
        require(docs_ru, needle, "docs/operations/observability.ru.md")

    require(secrets_docs, "observability.enc.yaml", "docs/secrets-sops-age.md")
    require(secrets_docs, "Grafana Cloud", "docs/secrets-sops-age.md")

    for forbidden in (
        "GRAFANA_CLOUD_API_KEY=example",
        "copy the age private key to the VPS",
        "chmod 666 /var/run/docker.sock",
    ):
        forbid(docs + secrets_docs, forbidden, "observability/secrets documentation")

    print("PASS observability credential contract: workstation SOPS ciphertext -> root-only VPS runtime file")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate(Path(args.root))
    except (OSError, ContractError) as exc:
        print(f"ERROR observability credential contract: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
