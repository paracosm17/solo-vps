#!/usr/bin/env python3
"""Receive a private Coolify control-plane backup over SSH and encrypt locally."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import tarfile
import tempfile
import zipfile

import yaml
if __package__:
    from .ci_deploy_transport import validate_server_host
    from .secrets_toolchain import (DEFAULT_MANIFEST, ToolchainError, check_installation,
                                   controller_platform, default_cache_root, install_dir, load_manifest)
else:
    from ci_deploy_transport import validate_server_host
    from secrets_toolchain import (DEFAULT_MANIFEST, ToolchainError, check_installation,
                                   controller_platform, default_cache_root, install_dir, load_manifest)

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = """import pathlib,subprocess,sys,tempfile
with tempfile.TemporaryDirectory(prefix='solo-vps-backup-code-') as tmp:
    p=pathlib.Path(tmp)/'collector.pyz'
    p.write_bytes(sys.stdin.buffer.read())
    sys.exit(subprocess.call([sys.executable,str(p),*sys.argv[1:]]))
"""


def payload() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zip:
        zip.writestr("__main__.py", (ROOT / "scripts/coolify_backup_collect.py").read_bytes())
        zip.writestr("coolify_upgrade_checkpoint.py", (ROOT / "scripts/coolify_upgrade_checkpoint.py").read_bytes())
    return output.getvalue()


def connection(args) -> tuple[list[str], str, str]:
    host, user, port, identity = args.host, args.user, 22, args.ssh_identity
    if not host and not user:
        inventory = yaml.safe_load(args.inventory.expanduser().read_text())
        hosts = inventory["all"]["hosts"]
        if len(hosts) != 1 or inventory["all"].get("vars") or inventory["all"].get("children"):
            raise ValueError("export requires one direct inventory host without inherited connection settings")
        variables = next(iter(hosts.values()))
        allowed = {"ansible_host", "ansible_user", "ansible_port", "ansible_ssh_private_key_file"}
        if set(variables) - allowed:
            raise ValueError("unsupported inventory connection settings; use explicit host/user")
        host, user = variables["ansible_host"], variables["ansible_user"]
        port = variables.get("ansible_port", 22)
        identity = identity or variables.get("ansible_ssh_private_key_file")
    validate_server_host(host)
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user or "") or user == "root":
        raise ValueError("use the existing non-root administrator")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("invalid SSH port")
    command = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "ConnectTimeout=20", "-p", str(port)]
    if identity:
        command += ["-i", str(Path(identity).expanduser())]
    return command + [user + "@" + host], host, user


def verify_members(stream) -> None:
    hashes = {}
    manifest = None
    with tarfile.open(fileobj=stream, mode="r|gz") as tar:
        for member in tar:
            name = PurePosixPath(member.name)
            if not member.isfile() or name.is_absolute() or ".." in name.parts or member.name in hashes:
                raise ValueError("unsafe or duplicate backup member")
            if member.name not in {"runtime.json", "manifest.json"} and not member.name.startswith(
                    ("control-plane/", "proxy/", "operator-config/")):
                raise ValueError("unexpected backup scope")
            file = tar.extractfile(member)
            if member.name == "manifest.json":
                if manifest is not None or member.size > 1024 * 1024:
                    raise ValueError("invalid backup manifest")
                manifest = json.load(file)
            else:
                hashes[member.name] = hashlib.file_digest(file, "sha256").hexdigest()
    if not isinstance(manifest, dict) or manifest.get("schema") != 1 or manifest.get("files") != hashes:
        raise ValueError("backup manifest checksum mismatch")
    if not {"control-plane/coolify-db.dump", "control-plane/control-plane.tar.gz",
            "control-plane/checkpoint.json", "runtime.json", "operator-config/config.yml",
            "operator-config/hosts.yml", "proxy/docker-compose.yml"} <= hashes.keys():
        raise ValueError("incomplete control-plane backup")


def verify_ciphertext(age: Path, key: Path, path: Path, expected: str) -> None:
    with tempfile.TemporaryFile() as error:
        proc = subprocess.Popen([str(age), "--decrypt", "-i", str(key), str(path)],
                                stdout=subprocess.PIPE, stderr=error)
        try:
            digest = hashlib.file_digest(proc.stdout, "sha256").hexdigest()
            if proc.wait() or digest != expected:
                raise ValueError("decryption or received backup checksum failed")
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
        # A second streaming pass checks every member, without plaintext on disk.
        proc = subprocess.Popen([str(age), "--decrypt", "-i", str(key), str(path)],
                                stdout=subprocess.PIPE, stderr=error)
        try:
            verify_members(proc.stdout)
            # Drain the authenticated age stream even if gzip ends before age EOF.
            while proc.stdout.read(1024 * 1024):
                pass
            if proc.wait():
                raise ValueError("age authentication failed")
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()


def export(command: list[str], age: Path, key: Path, output: Path, program: bytes) -> None:
    output = output.expanduser().absolute()
    if output.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("backup output must stay outside the source checkout")
    if output.exists() or output.is_symlink() or output.suffix != ".age":
        raise ValueError("output must be a new .age file")
    output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if output.parent.is_symlink():
        raise ValueError("unsafe output directory")
    descriptor, name = tempfile.mkstemp(prefix="." + output.name + ".", suffix=".partial", dir=output.parent)
    partial = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as ciphertext, tempfile.TemporaryFile() as remote_error, tempfile.TemporaryFile() as age_error:
            # Only source code travels to the VPS; age identity is never in this payload.
            with tempfile.TemporaryFile() as code:
                code.write(program)
                code.seek(0)
                remote = subprocess.Popen(command, stdin=code, stdout=subprocess.PIPE, stderr=remote_error)
                encrypt = None
                try:
                    encrypt = subprocess.Popen([str(age), "--encrypt", "-i", str(key)],
                                               stdin=remote.stdout, stdout=ciphertext, stderr=age_error)
                    remote.stdout.close()
                    encrypt_status = encrypt.wait()
                    remote_status = remote.wait()
                    if remote_status or encrypt_status:
                        raise ValueError("SSH collection or encryption failed; no final backup created")
                finally:
                    for proc in (encrypt, remote):
                        if proc and proc.poll() is None:
                            proc.kill()
                        if proc:
                            proc.wait()
                ciphertext.flush()
                os.fsync(ciphertext.fileno())
            remote_error.seek(0)
            lines = re.findall(rb"^SOLO_BACKUP_SHA256=([a-f0-9]{64})$", remote_error.read(), re.M)
            if len(lines) != 1:
                raise ValueError("missing remote checksum")
        verify_ciphertext(age, key, partial, lines[0].decode())
        # Link provides atomic no-clobber publication, including concurrent invocations.
        os.link(partial, output)
    finally:
        partial.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--host", default="")
    parser.add_argument("--user", default="")
    parser.add_argument("--ssh-identity", default="")
    parser.add_argument("--remote-data", default="")
    parser.add_argument("--remote-source", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    try:
        key = args.key_file.expanduser()
        if not key.is_file() or key.is_symlink():
            raise ValueError("local age identity is missing or unsafe")
        manifest = load_manifest(DEFAULT_MANIFEST)
        platform = controller_platform()
        tools = check_installation(install_dir(default_cache_root(), manifest, platform),
                                   DEFAULT_MANIFEST, manifest, platform)
        subprocess.run([str(tools["age-keygen"]), "-y", str(key)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        command, _, user = connection(args)
        home = "/home/" + user
        remote_args = ["--operator-data", args.remote_data or home + "/.local/share/solo-vps",
                       "--source", args.remote_source or home + "/solo-vps"]
        remote = shlex.join(["sudo", "-n", "python3", "-c", LAUNCHER, *remote_args])
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = Path(args.output) if args.output else args.data_dir / "backups" / ("coolify-" + stamp + ".tar.gz.age")
        export(command + [remote], tools["age"], key, output, payload())
    except (OSError, ValueError, KeyError, TypeError, EOFError, ToolchainError, yaml.YAMLError,
            subprocess.SubprocessError, tarfile.TarError):
        # Never echo SSH/age/pg_dump stderr or file contents.
        parser.exit(2, "ERROR: Coolify backup export failed; check paths, pinned tools, SSH and sudo access\n")
    print("PASS verified encrypted Coolify control-plane backup")
    print("  output: " + str(output.expanduser().absolute()))
    with output.expanduser().open("rb") as stream:
        print("  encrypted SHA256: " + hashlib.file_digest(stream, "sha256").hexdigest())
    print("  application data: excluded; keep separate database/volume backups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
