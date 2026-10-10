"""Shared archive checks and fail-closed age publication for Coolify backups."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile
ROOT = Path(__file__).resolve().parents[1]

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


def receive_encrypted(command: list[str], age: Path, encryption_args: list[str], output: Path, program: bytes = b"", verifier=None) -> None:
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
                    encrypt = subprocess.Popen([str(age), "--encrypt", *encryption_args],
                                               stdin=subprocess.PIPE, stdout=ciphertext, stderr=age_error)
                    digest = hashlib.sha256()
                    try:
                        while block := remote.stdout.read(1024 * 1024):
                            digest.update(block)
                            encrypt.stdin.write(block)
                    finally:
                        remote.stdout.close()
                        encrypt.stdin.close()
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
        expected = lines[0].decode()
        if digest.hexdigest() != expected:
            raise ValueError("received plaintext checksum mismatch")
        if verifier is not None:
            verifier(partial, expected)
        # Link provides atomic no-clobber publication, including concurrent invocations.
        os.link(partial, output)
    finally:
        partial.unlink(missing_ok=True)


