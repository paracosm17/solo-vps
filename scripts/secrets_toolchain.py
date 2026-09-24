#!/usr/bin/env python3
"""Install/check the pinned SOPS + age controller toolchain without root access."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import sys
import tarfile
import tempfile
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "tools" / "secrets-toolchain.json"
SCHEMA_VERSION = 1
SUPPORTED_PLATFORMS = {"linux-amd64", "linux-arm64"}
EXPECTED_TOOLS = {"sops", "age"}
EXPECTED_AGE_MEMBERS = {"age", "age-keygen"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class ToolchainError(RuntimeError):
    """Raised when the pinned toolchain contract is unsafe or unsatisfied."""


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolchainError(f"cannot read toolchain manifest {path}: {exc}") from exc
    validate_manifest(data)
    return data


def validate_manifest(data: dict[str, Any]) -> None:
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ToolchainError(f"toolchain manifest schema_version must be {SCHEMA_VERSION}")

    platforms = data.get("controller_platforms")
    if platforms != ["linux-amd64", "linux-arm64"]:
        raise ToolchainError("controller_platforms must be exactly linux-amd64 + linux-arm64")

    tools = data.get("tools")
    if not isinstance(tools, dict) or set(tools) != EXPECTED_TOOLS:
        raise ToolchainError("toolchain manifest must contain exactly sops and age")

    for tool_name in sorted(EXPECTED_TOOLS):
        tool = tools[tool_name]
        if not isinstance(tool, dict):
            raise ToolchainError(f"{tool_name} manifest entry must be a mapping")
        version = tool.get("version")
        if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
            raise ToolchainError(f"{tool_name} version must be an exact x.y.z release")
        artifacts = tool.get("artifacts")
        if not isinstance(artifacts, dict) or set(artifacts) != SUPPORTED_PLATFORMS:
            raise ToolchainError(f"{tool_name} must pin linux-amd64 and linux-arm64 artifacts")
        for platform_id, artifact in artifacts.items():
            _validate_artifact(tool_name, version, platform_id, artifact)


def _validate_artifact(
    tool_name: str, version: str, platform_id: str, artifact: dict[str, Any]
) -> None:
    if not isinstance(artifact, dict):
        raise ToolchainError(f"{tool_name}/{platform_id} artifact must be a mapping")
    url = artifact.get("url")
    digest = artifact.get("sha256")
    artifact_format = artifact.get("format")
    if not isinstance(url, str):
        raise ToolchainError(f"{tool_name}/{platform_id} URL is missing")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise ToolchainError(f"{tool_name}/{platform_id} must use an official GitHub HTTPS release URL")
    expected_repo = "/getsops/sops/releases/download/" if tool_name == "sops" else "/FiloSottile/age/releases/download/"
    if not parsed.path.startswith(expected_repo + f"v{version}/"):
        raise ToolchainError(f"{tool_name}/{platform_id} URL must point at pinned v{version} release")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise ToolchainError(f"{tool_name}/{platform_id} must pin a lowercase SHA-256")

    if tool_name == "sops":
        if artifact_format != "binary" or "members" in artifact:
            raise ToolchainError(f"sops/{platform_id} must be a direct binary artifact")
        expected_suffix = ".linux.amd64" if platform_id.endswith("amd64") else ".linux.arm64"
        if not parsed.path.endswith(f"sops-v{version}{expected_suffix}"):
            raise ToolchainError(f"sops/{platform_id} artifact filename does not match the platform")
    else:
        if artifact_format != "tar.gz":
            raise ToolchainError(f"age/{platform_id} must be a tar.gz artifact")
        expected_arch = "amd64" if platform_id.endswith("amd64") else "arm64"
        if not parsed.path.endswith(f"age-v{version}-linux-{expected_arch}.tar.gz"):
            raise ToolchainError(f"age/{platform_id} artifact filename does not match the platform")
        members = artifact.get("members")
        if not isinstance(members, dict) or set(members) != EXPECTED_AGE_MEMBERS:
            raise ToolchainError(f"age/{platform_id} must define exact age + age-keygen archive members")
        if members != {"age": "age/age", "age-keygen": "age/age-keygen"}:
            raise ToolchainError(f"age/{platform_id} archive members must remain pinned to age/* paths")


def controller_platform(system: str | None = None, machine: str | None = None) -> str:
    system_name = (system or platform.system()).lower()
    machine_name = (machine or platform.machine()).lower()
    if system_name != "linux":
        raise ToolchainError(
            f"controller tool bootstrap currently supports Linux only; got {system_name or 'unknown'}"
        )
    if machine_name in {"x86_64", "amd64"}:
        return "linux-amd64"
    if machine_name in {"aarch64", "arm64"}:
        return "linux-arm64"
    raise ToolchainError(f"unsupported Linux controller architecture: {machine_name or 'unknown'}")


def default_cache_root() -> Path:
    explicit = os.environ.get("SOLO_VPS_TOOL_CACHE")
    if explicit:
        return Path(explicit).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "solo-vps" / "toolchains"


def manifest_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install_dir(cache_root: Path, manifest: dict[str, Any], platform_id: str) -> Path:
    sops_version = manifest["tools"]["sops"]["version"]
    age_version = manifest["tools"]["age"]["version"]
    return cache_root / f"sops-{sops_version}_age-{age_version}" / platform_id


def binary_paths(root: Path) -> dict[str, Path]:
    bin_dir = root / "bin"
    return {
        "sops": bin_dir / "sops",
        "age": bin_dir / "age",
        "age-keygen": bin_dir / "age-keygen",
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise ToolchainError(
            f"SHA-256 mismatch for {path.name}: expected {expected}, got {actual}"
        )


def _artifact_filename(artifact: dict[str, Any]) -> str:
    return Path(urlparse(artifact["url"]).path).name


def _copy_local_artifact(source_dir: Path, artifact: dict[str, Any], destination: Path) -> None:
    source = source_dir / _artifact_filename(artifact)
    try:
        metadata = source.lstat()
    except OSError as exc:
        raise ToolchainError(f"local artifact is missing: {source}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ToolchainError(f"local artifact must be a regular non-symlink file: {source}")
    if metadata.st_size <= 0 or metadata.st_size > 128 * 1024 * 1024:
        raise ToolchainError(f"local artifact has an unreasonable size: {source}")
    shutil.copyfile(source, destination)


def _download(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "solo-vps-secrets-toolchain/1"})
    max_bytes = 128 * 1024 * 1024
    try:
        with urlopen(request, timeout=60) as response, destination.open("wb") as handle:
            if response.geturl().split("?", 1)[0].startswith("http://"):
                raise ToolchainError("refusing an HTTPS-to-HTTP download redirect")
            declared = response.headers.get("Content-Length")
            if declared is not None and int(declared) > max_bytes:
                raise ToolchainError("refusing release artifact larger than 128 MiB")
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ToolchainError("refusing release artifact larger than 128 MiB")
                handle.write(chunk)
    except (OSError, ValueError) as exc:
        raise ToolchainError(f"download failed for {url}: {exc}") from exc


def _write_executable_from_stream(source: Any, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        shutil.copyfileobj(source, handle)
    destination.chmod(0o755)


def extract_age_archive(archive_path: Path, members: dict[str, str], bin_dir: Path) -> None:
    """Extract only the two exact regular age binaries; never generic-extract the archive."""

    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            all_members = archive.getmembers()
            expected_paths = set(members.values())
            names = [member.name for member in all_members]
            missing = sorted(path for path in expected_paths if path not in names)
            if missing:
                raise ToolchainError(f"age archive is missing expected members: {', '.join(missing)}")
            duplicates = sorted(path for path in expected_paths if names.count(path) != 1)
            if duplicates:
                raise ToolchainError(
                    f"age archive contains duplicate expected members: {', '.join(duplicates)}"
                )
            archive_members = {member.name: member for member in all_members}

            for binary_name, member_name in members.items():
                member = archive_members[member_name]
                if not member.isfile() or member.issym() or member.islnk():
                    raise ToolchainError(f"age archive member is not a regular file: {member_name}")
                if member.size <= 0 or member.size > 128 * 1024 * 1024:
                    raise ToolchainError(f"age archive member has an unreasonable size: {member_name}")
                source = archive.extractfile(member)
                if source is None:
                    raise ToolchainError(f"cannot read age archive member: {member_name}")
                _write_executable_from_stream(source, bin_dir / binary_name)
    except (OSError, tarfile.TarError) as exc:
        raise ToolchainError(f"cannot read age archive {archive_path}: {exc}") from exc


def _receipt_path(root: Path) -> Path:
    return root / "receipt.json"


def check_installation(
    root: Path, manifest_path: Path, manifest: dict[str, Any], platform_id: str
) -> dict[str, Path]:
    receipt_path = _receipt_path(root)
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolchainError(f"toolchain receipt is missing or invalid: {receipt_path}: {exc}") from exc

    if receipt.get("schema_version") != 1:
        raise ToolchainError("toolchain receipt schema is unsupported")
    if receipt.get("manifest_sha256") != manifest_digest(manifest_path):
        raise ToolchainError("installed toolchain does not match the current pinned manifest")
    if receipt.get("platform") != platform_id:
        raise ToolchainError("installed toolchain platform does not match this controller")

    paths = binary_paths(root)
    for path in paths.values():
        if not path.is_file():
            raise ToolchainError(f"installed tool is missing: {path}")
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o111 == 0:
            raise ToolchainError(f"installed tool is not executable: {path}")

    artifacts_dir = root / "artifacts"
    sops_artifact = manifest["tools"]["sops"]["artifacts"][platform_id]
    sops_artifact_path = artifacts_dir / Path(urlparse(sops_artifact["url"]).path).name
    verify_sha256(sops_artifact_path, sops_artifact["sha256"])
    if sha256_file(paths["sops"]) != sops_artifact["sha256"]:
        raise ToolchainError("installed sops binary no longer matches the pinned release artifact")

    age_artifact = manifest["tools"]["age"]["artifacts"][platform_id]
    age_artifact_path = artifacts_dir / Path(urlparse(age_artifact["url"]).path).name
    verify_sha256(age_artifact_path, age_artifact["sha256"])
    with tempfile.TemporaryDirectory(prefix="solo-vps-age-check-") as temporary:
        expected_bin_dir = Path(temporary) / "bin"
        extract_age_archive(age_artifact_path, age_artifact["members"], expected_bin_dir)
        for name in EXPECTED_AGE_MEMBERS:
            if sha256_file(paths[name]) != sha256_file(expected_bin_dir / name):
                raise ToolchainError(f"installed {name} no longer matches the pinned age release archive")

    return paths


def install_toolchain(
    manifest_path: Path,
    manifest: dict[str, Any],
    cache_root: Path,
    platform_id: str,
    artifact_dir: Path | None = None,
) -> Path:
    target = install_dir(cache_root, manifest, platform_id)
    if target.exists():
        check_installation(target, manifest_path, manifest, platform_id)
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{platform_id}.", dir=target.parent))
    try:
        artifacts_dir = staging / "artifacts"
        bin_dir = staging / "bin"
        artifacts_dir.mkdir(mode=0o700)
        bin_dir.mkdir(mode=0o755)

        for tool_name in ("sops", "age"):
            artifact = manifest["tools"][tool_name]["artifacts"][platform_id]
            filename = _artifact_filename(artifact)
            artifact_path = artifacts_dir / filename
            if artifact_dir is None:
                _download(artifact["url"], artifact_path)
            else:
                _copy_local_artifact(artifact_dir, artifact, artifact_path)
            verify_sha256(artifact_path, artifact["sha256"])

            if tool_name == "sops":
                shutil.copyfile(artifact_path, bin_dir / "sops")
                (bin_dir / "sops").chmod(0o755)
            else:
                extract_age_archive(artifact_path, artifact["members"], bin_dir)

        paths = binary_paths(staging)
        binary_hashes = {name: sha256_file(path) for name, path in paths.items()}
        receipt = {
            "schema_version": 1,
            "manifest_sha256": manifest_digest(manifest_path),
            "platform": platform_id,
            "versions": {
                "sops": manifest["tools"]["sops"]["version"],
                "age": manifest["tools"]["age"]["version"],
            },
            "artifact_sha256": {
                tool_name: manifest["tools"][tool_name]["artifacts"][platform_id]["sha256"]
                for tool_name in ("sops", "age")
            },
            "binary_sha256": binary_hashes,
        }
        _receipt_path(staging).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, target)
        check_installation(target, manifest_path, manifest, platform_id)
        return target
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "install", "check", "paths"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="install from exact pinned artifact filenames in this local directory instead of downloading",
    )
    args = parser.parse_args()

    try:
        manifest_path = args.manifest.expanduser().resolve()
        manifest = load_manifest(manifest_path)
        if args.artifact_dir is not None and args.command != "install":
            raise ToolchainError("--artifact-dir is valid only with the install command")
        if args.command == "validate":
            print("PASS secrets toolchain manifest: pinned Linux amd64/arm64 SOPS + age artifacts")
            return 0

        platform_id = controller_platform()
        cache_root = (args.cache_dir or default_cache_root()).expanduser().resolve()
        root = install_dir(cache_root, manifest, platform_id)

        if args.command == "install":
            artifact_dir = args.artifact_dir.expanduser().resolve() if args.artifact_dir else None
            root = install_toolchain(
                manifest_path, manifest, cache_root, platform_id, artifact_dir=artifact_dir
            )
            source = "local verified artifacts" if artifact_dir is not None else "official downloads"
            print(f"PASS secrets toolchain installed/verified from {source}: {root}")
            return 0

        paths = check_installation(root, manifest_path, manifest, platform_id)
        if args.command == "check":
            print(
                "PASS secrets toolchain: "
                f"sops {manifest['tools']['sops']['version']} + age {manifest['tools']['age']['version']} "
                f"({platform_id})"
            )
        else:
            for name in ("sops", "age", "age-keygen"):
                print(f"{name}={paths[name]}")
        return 0
    except (OSError, ToolchainError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
