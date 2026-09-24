#!/usr/bin/env python3
"""Restore a Coolify instance database onto an explicitly marked replacement VPS.

This helper follows the project recovery boundary: install a fresh pinned Coolify
first, restore its logical instance database, add the previous APP_KEY only as a
previous decryption key, restore the backed-up Coolify SSH identities, and then
restart the current pinned Compose model. It never copies the old .env wholesale.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
from typing import Callable, Sequence


class CoolifyInstanceRestoreError(RuntimeError):
    pass


CONFIRMATION = "I_HAVE_VERIFIED_THE_REPLACEMENT_VPS_FOR_COOLIFY_RESTORE"
DEFAULT_LIVE_ENV = Path("/data/coolify/source/.env")
DEFAULT_LIVE_KEYS = Path("/data/coolify/ssh/keys")
DEFAULT_MARKER = Path("/data/coolify/.solo-vps-managed")
DEFAULT_TARGET_MARKER = Path("/root/.solo-vps-disaster-recovery-target")
COMPOSE_FILES = (
    Path("/data/coolify/source/docker-compose.yml"),
    Path("/data/coolify/source/docker-compose.prod.yml"),
    Path("/data/coolify/source/docker-compose.solo-vps.yml"),
)
ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
TARGET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
PRIVATE_KEY_UUID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{7,127}$")
COOLIFY_KEY_FILE_RE = re.compile(
    r"^(?:ssh_key@[A-Za-z0-9][A-Za-z0-9_-]{7,127}|id\.[A-Za-z0-9._-]+@host\.docker\.internal)$"
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class RestorePlan:
    admin_user: str
    db_user: str
    db_name: str
    previous_app_key_present: bool
    recovered_ssh_keys: int
    localhost_key_authorized: bool = False


def _bounded(text: str, *, lines: int = 8) -> str:
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    return " | ".join(rows[-lines:])[:2000] if rows else "no diagnostic output"


def require_regular(path: Path, name: str, *, private: bool = False) -> Path:
    try:
        meta = path.lstat()
    except FileNotFoundError as exc:
        raise CoolifyInstanceRestoreError(f"required {name} is missing: {path}") from exc
    if stat.S_ISLNK(meta.st_mode) or not stat.S_ISREG(meta.st_mode):
        raise CoolifyInstanceRestoreError(f"{name} must be a regular non-symlink file: {path}")
    if private and stat.S_IMODE(meta.st_mode) & 0o077:
        raise CoolifyInstanceRestoreError(f"{name} must not be group/world accessible: {path}")
    return path


def parse_env(path: Path) -> dict[str, str]:
    require_regular(path, "Coolify environment", private=True)
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not ENV_KEY_RE.fullmatch(key):
            continue
        if key in result:
            raise CoolifyInstanceRestoreError(f"duplicate key in Coolify environment: {key}")
        result[key] = value
    return result


def update_previous_keys(path: Path, previous_key: str) -> None:
    if not previous_key or "\n" in previous_key or "\r" in previous_key:
        raise CoolifyInstanceRestoreError("previous APP_KEY is empty or multiline")
    lines = path.read_text(encoding="utf-8").splitlines()
    current = parse_env(path)
    current_key = current.get("APP_KEY", "")
    if not current_key:
        raise CoolifyInstanceRestoreError("fresh Coolify environment is missing APP_KEY")
    existing = [item for item in current.get("APP_PREVIOUS_KEYS", "").split(",") if item]
    desired = [item for item in existing if item != current_key]
    if previous_key != current_key and previous_key not in desired:
        desired.append(previous_key)
    replacement = "APP_PREVIOUS_KEYS=" + ",".join(desired)
    output: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith("APP_PREVIOUS_KEYS="):
            if not replaced:
                output.append(replacement)
                replaced = True
            continue
        output.append(line)
    if not replaced:
        output.append(replacement)
    temp = path.with_name(path.name + ".solo-vps-recovery.tmp")
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(output) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(temp, path.stat().st_uid, path.stat().st_gid)
        os.chmod(temp, stat.S_IMODE(path.stat().st_mode))
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _read_managed_marker(path: Path, expected_version: str) -> str:
    require_regular(path, "Solo VPS Coolify managed marker", private=True)
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    if values.get("managed_by") != "solo-vps" or values.get("coolify_version") != expected_version:
        raise CoolifyInstanceRestoreError("fresh Coolify marker does not match this Solo VPS pin")
    admin = values.get("localhost_user", "")
    if not admin:
        raise CoolifyInstanceRestoreError("managed marker has no localhost_user")
    return admin


def _require_target_marker(path: Path, target_id: str) -> None:
    if not TARGET_ID_RE.fullmatch(target_id):
        raise CoolifyInstanceRestoreError("recovery target id must be 8-128 safe characters")
    require_regular(path, "disaster-recovery target marker", private=True)
    meta = path.stat()
    if meta.st_uid != 0 or meta.st_gid != 0 or stat.S_IMODE(meta.st_mode) != 0o600:
        raise CoolifyInstanceRestoreError("disaster-recovery target marker must be root:root mode 0600")
    if path.read_text(encoding="utf-8").strip() != target_id:
        raise CoolifyInstanceRestoreError("disaster-recovery target marker does not match --target-id")


def _recovered_env(recovery_root: Path) -> Path:
    return recovery_root / "data/coolify/source/.env"


def _recovered_keys(recovery_root: Path) -> Path:
    return recovery_root / "data/coolify/ssh/keys"


def _key_files(root: Path) -> list[Path]:
    try:
        meta = root.lstat()
    except FileNotFoundError as exc:
        raise CoolifyInstanceRestoreError(f"recovered Coolify SSH key directory is missing: {root}") from exc
    if stat.S_ISLNK(meta.st_mode) or not stat.S_ISDIR(meta.st_mode):
        raise CoolifyInstanceRestoreError("recovered Coolify SSH key path must be a real directory")
    keys: list[Path] = []
    for path in sorted(root.iterdir()):
        if path.name.endswith((".pub", ".lock")):
            continue
        if not COOLIFY_KEY_FILE_RE.fullmatch(path.name):
            raise CoolifyInstanceRestoreError(f"unexpected file in recovered Coolify key directory: {path.name}")
        meta = path.lstat()
        if stat.S_ISLNK(meta.st_mode) or not stat.S_ISREG(meta.st_mode):
            raise CoolifyInstanceRestoreError(f"unexpected non-file in recovered key directory: {path.name}")
        if stat.S_IMODE(meta.st_mode) & 0o077:
            raise CoolifyInstanceRestoreError(f"recovered Coolify private key is too permissive: {path.name}")
        keys.append(path)
    if not keys:
        raise CoolifyInstanceRestoreError("no recovered Coolify SSH private keys were found")
    return keys


def inspect_archive(archive: Path, *, pg_restore: str = "pg_restore", runner: Runner = subprocess.run) -> int:
    require_regular(archive, "Coolify instance database archive", private=True)
    binary = shutil.which(pg_restore) if "/" not in pg_restore else pg_restore
    if not binary:
        raise CoolifyInstanceRestoreError("pg_restore is required to inspect the Coolify instance archive")
    result = runner([binary, "--list", str(archive)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise CoolifyInstanceRestoreError(f"Coolify instance archive inspection failed: {_bounded(result.stderr or '')}")
    objects = len([row for row in (result.stdout or "").splitlines() if row.strip() and not row.startswith(";")])
    if objects < 1:
        raise CoolifyInstanceRestoreError("Coolify instance archive contains no restorable objects")
    return objects


def build_plan(
    *,
    archive: Path,
    recovery_root: Path,
    expected_version: str,
    live_env: Path = DEFAULT_LIVE_ENV,
    live_marker: Path = DEFAULT_MARKER,
    pg_restore: str = "pg_restore",
    runner: Runner = subprocess.run,
) -> RestorePlan:
    inspect_archive(archive, pg_restore=pg_restore, runner=runner)
    old_env = parse_env(_recovered_env(recovery_root))
    old_key = old_env.get("APP_KEY", "")
    if not old_key:
        raise CoolifyInstanceRestoreError("recovered Coolify environment is missing APP_KEY")
    keys = _key_files(_recovered_keys(recovery_root))
    current = parse_env(live_env)
    db_user = current.get("DB_USERNAME", "")
    db_name = current.get("DB_DATABASE", "coolify")
    if not db_user or not db_name:
        raise CoolifyInstanceRestoreError("fresh Coolify environment is missing DB_USERNAME/DB_DATABASE")
    admin = _read_managed_marker(live_marker, expected_version)
    return RestorePlan(
        admin_user=admin,
        db_user=db_user,
        db_name=db_name,
        previous_app_key_present=True,
        recovered_ssh_keys=len(keys),
    )


def _run(command: Sequence[str], *, runner: Runner, input_file=None, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    result = runner(
        list(command),
        stdin=input_file,
        text=False if input_file is not None else True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace") if isinstance(result.stderr, bytes) else (result.stderr or "")
        raise CoolifyInstanceRestoreError(f"recovery command failed (exit {result.returncode}): {_bounded(stderr)}")
    return result


def resolve_localhost_private_key_uuid(
    db_user: str,
    db_name: str,
    *,
    runner: Runner = subprocess.run,
) -> str:
    """Resolve only the restored Coolify localhost server key from restored DB state.

    Coolify models the built-in host as Server id=0 and Server belongsTo PrivateKey.
    Querying that exact relation prevents unrelated recovered server/Git keys from
    being granted login access to the replacement host.
    """
    sql = (
        "SELECT pk.uuid FROM servers AS s "
        "JOIN private_keys AS pk ON pk.id = s.private_key_id "
        "WHERE s.id = 0;"
    )
    result = runner(
        [
            "/usr/bin/docker",
            "exec",
            "coolify-db",
            "psql",
            "-X",
            "-A",
            "-t",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            db_user,
            "-d",
            db_name,
            "-c",
            sql,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        raise CoolifyInstanceRestoreError(
            "could not resolve the restored Coolify localhost SSH identity: "
            + _bounded(result.stderr or "")
        )
    rows = [row.strip() for row in (result.stdout or "").splitlines() if row.strip()]
    if len(rows) != 1 or not PRIVATE_KEY_UUID_RE.fullmatch(rows[0]):
        raise CoolifyInstanceRestoreError(
            "restored Coolify database must resolve exactly one safe private-key UUID for server id=0"
        )
    return rows[0]


def restore_keys(
    recovery_root: Path,
    live_keys: Path,
    admin_user: str,
    localhost_private_key_uuid: str,
    *,
    runner: Runner = subprocess.run,
) -> int:
    old_keys = _key_files(_recovered_keys(recovery_root))
    if not PRIVATE_KEY_UUID_RE.fullmatch(localhost_private_key_uuid):
        raise CoolifyInstanceRestoreError("invalid restored localhost private-key UUID")
    expected_local_key_name = f"ssh_key@{localhost_private_key_uuid}"
    old_by_name = {path.name: path for path in old_keys}
    if expected_local_key_name not in old_by_name:
        raise CoolifyInstanceRestoreError(
            "recovered Coolify SSH material is missing the database-associated localhost key"
        )

    user = pwd.getpwnam(admin_user)
    ssh_dir = Path(user.pw_dir) / ".ssh"
    auth = ssh_dir / "authorized_keys"
    ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chown(ssh_dir, user.pw_uid, user.pw_gid)
    os.chmod(ssh_dir, 0o700)
    live_keys.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chown(live_keys, 9999, 0)
    os.chmod(live_keys, 0o700)
    for existing in live_keys.iterdir():
        if existing.is_file() or existing.is_symlink():
            existing.unlink()
        else:
            raise CoolifyInstanceRestoreError("refusing unexpected directory inside live Coolify SSH keys")

    for old in old_keys:
        dest = live_keys / old.name
        shutil.copyfile(old, dest)
        os.chown(dest, 9999, 0)
        os.chmod(dest, 0o600)

    local_key = live_keys / expected_local_key_name
    result = runner(
        ["/usr/bin/ssh-keygen", "-y", "-f", str(local_key)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0 or not (result.stdout or "").strip().startswith("ssh-"):
        raise CoolifyInstanceRestoreError("could not derive public key from the restored Coolify localhost key")
    public = (result.stdout or "").strip()
    authorized = auth.read_text(encoding="utf-8").splitlines() if auth.exists() else []
    if public not in authorized:
        authorized.append(public)
    auth.write_text("\n".join(authorized) + "\n", encoding="utf-8")
    os.chown(auth, user.pw_uid, user.pw_gid)
    os.chmod(auth, 0o600)
    return len(old_keys)


def apply_restore(
    *,
    archive: Path,
    recovery_root: Path,
    expected_version: str,
    target_id: str,
    live_env: Path = DEFAULT_LIVE_ENV,
    live_keys: Path = DEFAULT_LIVE_KEYS,
    live_marker: Path = DEFAULT_MARKER,
    target_marker: Path = DEFAULT_TARGET_MARKER,
    runner: Runner = subprocess.run,
) -> RestorePlan:
    if os.geteuid() != 0:
        raise CoolifyInstanceRestoreError("Coolify instance restore must run as root")
    if os.environ.get("SOLO_VPS_DISASTER_RECOVERY_CONFIRM", "") != CONFIRMATION:
        raise CoolifyInstanceRestoreError("restore requires SOLO_VPS_DISASTER_RECOVERY_CONFIRM=" + CONFIRMATION)
    _require_target_marker(target_marker, target_id)
    plan = build_plan(
        archive=archive,
        recovery_root=recovery_root,
        expected_version=expected_version,
        live_env=live_env,
        live_marker=live_marker,
        runner=runner,
    )
    old_key = parse_env(_recovered_env(recovery_root))["APP_KEY"]
    for compose in COMPOSE_FILES:
        require_regular(compose, "fresh pinned Coolify Compose file")
    docker = "/usr/bin/docker"
    _run([docker, "inspect", "coolify-db"], runner=runner, timeout=60)
    # Stop only front/control containers; the database must stay available for pg_restore.
    for container in ("coolify", "coolify-redis", "coolify-realtime", "coolify-proxy"):
        result = runner([docker, "stop", container], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=120)
        if result.returncode not in (0, 1):
            raise CoolifyInstanceRestoreError(f"could not stop {container}: {_bounded(result.stderr or '')}")
    with archive.open("rb") as handle:
        _run(
            [
                docker,
                "exec",
                "-i",
                "coolify-db",
                "pg_restore",
                "--exit-on-error",
                "--clean",
                "--if-exists",
                "--no-acl",
                "--no-owner",
                "-U",
                plan.db_user,
                "-d",
                plan.db_name,
            ],
            runner=runner,
            input_file=handle,
            timeout=3600,
        )
    update_previous_keys(live_env, old_key)
    localhost_key_uuid = resolve_localhost_private_key_uuid(
        plan.db_user,
        plan.db_name,
        runner=runner,
    )
    restored = restore_keys(
        recovery_root,
        live_keys,
        plan.admin_user,
        localhost_key_uuid,
        runner=runner,
    )
    compose_command = [docker, "compose", "--env-file", str(live_env)]
    for compose in COMPOSE_FILES:
        compose_command.extend(["-f", str(compose)])
    _run([*compose_command, "config", "--quiet"], runner=runner, timeout=120)
    _run([*compose_command, "up", "-d", "--pull", "always", "--remove-orphans", "--force-recreate"], runner=runner, timeout=1800)
    return RestorePlan(
        admin_user=plan.admin_user,
        db_user=plan.db_user,
        db_name=plan.db_name,
        previous_app_key_present=True,
        recovered_ssh_keys=restored,
        localhost_key_authorized=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inspect", "plan", "restore"))
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--recovery-root", type=Path)
    parser.add_argument("--expected-version", default="4.1.2")
    parser.add_argument("--target-id", default="")
    args = parser.parse_args()
    try:
        if args.operation == "inspect":
            objects = inspect_archive(args.archive)
            print("PASS Coolify instance backup archive inspection")
            print(f"  archive_objects: {objects}")
            print("  restore_exercised: false")
            return 0
        if args.recovery_root is None:
            raise CoolifyInstanceRestoreError("plan/restore requires --recovery-root")
        if args.operation == "plan":
            plan = build_plan(
                archive=args.archive,
                recovery_root=args.recovery_root,
                expected_version=args.expected_version,
            )
            print("PASS Coolify instance restore plan")
            print(f"  admin_user: {plan.admin_user}")
            print(f"  recovered_ssh_keys: {plan.recovered_ssh_keys}")
            print("  previous_app_key_present: true")
            print("  old_env_will_replace_fresh_env: false")
            print("  mutation: false")
            return 0
        plan = apply_restore(
            archive=args.archive,
            recovery_root=args.recovery_root,
            expected_version=args.expected_version,
            target_id=args.target_id,
        )
        print("PASS Coolify instance database + identity restore")
        print(f"  admin_user: {plan.admin_user}")
        print(f"  recovered_ssh_keys: {plan.recovered_ssh_keys}")
        print("  localhost_database_associated_key_authorized: true")
        print("  unrelated_recovered_keys_authorized_locally: false")
        print("  previous_app_key_installed_as_previous_only: true")
        print("  fresh_runtime_database_credentials_preserved: true")
        print("  follow_up: make verify-coolify && make verify && make audit")
        return 0
    except (KeyError, OSError, pwd.KeyError, subprocess.TimeoutExpired, CoolifyInstanceRestoreError) as exc:
        print(f"ERROR Coolify instance restore: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
