#!/usr/bin/env python3
"""Prepare the same-VPS admin source checkout and persistent controller state."""

from __future__ import annotations

import argparse
import os
import pathlib
import pwd
import shutil
import subprocess
import sys
from typing import Iterable

try:
    from scripts.prepare_access import AccessError, extract_inputs, load_yaml, local_addresses, resolve_host
except ModuleNotFoundError:  # direct script execution from scripts/
    from prepare_access import AccessError, extract_inputs, load_yaml, local_addresses, resolve_host


class HandoffError(RuntimeError):
    pass


IGNORED_NAMES = {
    ".venv",
    ".venv-docs",
    "site",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "tmp",
}
INCOMPLETE_MARKER = ".admin-workspace.incomplete"
COMPLETE_MARKER = ".admin-workspace"


def ignore_workspace(path: str, names: list[str]) -> set[str]:
    """Ignore generated source-local caches retained only for legacy compatibility."""
    return {name for name in names if name in IGNORED_NAMES or name.endswith(".pyc")}


def workspace_ignore(source: pathlib.Path):
    source = source.resolve()

    def _ignore(path: str, names: list[str]) -> set[str]:
        ignored = ignore_workspace(path, names)
        current = pathlib.Path(path).resolve()
        if current == source / "config" and "config.yml" in names:
            ignored.add("config.yml")
        if current == source / "ansible" / "inventories" and "local" in names:
            ignored.add("local")
        if current == source and ".sops.yaml" in names:
            ignored.add(".sops.yaml")
        if current == source / "secrets" / "recipients" and "production.txt" in names:
            ignored.add("production.txt")
        return ignored

    return _ignore


def chown_tree(root: pathlib.Path, uid: int, gid: int) -> None:
    for current, dirs, files in os.walk(root):
        current_path = pathlib.Path(current)
        os.chown(current_path, uid, gid)
        for name in dirs:
            path = current_path / name
            if path.is_symlink():
                os.lchown(path, uid, gid)
        for name in files:
            path = current_path / name
            if path.is_symlink():
                os.lchown(path, uid, gid)
            else:
                os.chown(path, uid, gid)


def run_as_admin(admin_user: str, workspace: pathlib.Path, argv: Iterable[str]) -> None:
    command = ["sudo", "-H", "-u", admin_user, "--", *argv]
    try:
        subprocess.run(command, cwd=workspace, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise HandoffError(f"admin workspace command failed: {' '.join(argv)}: {exc}") from exc


def ensure_admin_data_parents(admin_home: pathlib.Path, uid: int, gid: int) -> None:
    """Keep default XDG data parents usable by the managed admin account.

    The root-driven handoff may be the first process that creates ~/.local/share.
    Creating the full state path as root and chowning only the final solo-vps
    directory leaves ~/.local/share root-owned, which later breaks ordinary
    user tools such as nano. Reconcile only these standard user-owned parents.
    """

    for path in (admin_home / ".local", admin_home / ".local/share"):
        if path.is_symlink():
            raise HandoffError(f"refusing symlink admin data directory: {path}")
        if path.exists() and not path.is_dir():
            raise HandoffError(f"admin data path is not a directory: {path}")
        path.mkdir(exist_ok=True, mode=0o700)
        stat = path.stat()
        if stat.st_uid not in (0, uid):
            raise HandoffError(
                f"refusing to take ownership of admin data directory owned by uid {stat.st_uid}: {path}"
            )
        if stat.st_uid != uid or stat.st_gid != gid:
            os.chown(path, uid, gid)


def admin_data_parents_need_repair(admin_home: pathlib.Path, uid: int, gid: int) -> bool:
    for path in (admin_home / ".local", admin_home / ".local/share"):
        if path.is_symlink():
            raise HandoffError(f"refusing symlink admin data directory: {path}")
        if not path.exists():
            return True
        if not path.is_dir():
            raise HandoffError(f"admin data path is not a directory: {path}")
        stat = path.stat()
        if stat.st_uid not in (0, uid):
            raise HandoffError(
                f"refusing to take ownership of admin data directory owned by uid {stat.st_uid}: {path}"
            )
        if stat.st_uid != uid or stat.st_gid != gid:
            return True
    return False


def _marker_path(state_dir: pathlib.Path, complete: bool) -> pathlib.Path:
    return state_dir / (COMPLETE_MARKER if complete else INCOMPLETE_MARKER)


def _write_marker(path: pathlib.Path, workspace: pathlib.Path, uid: int, gid: int, state: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(f"managed_by=solo-vps\nstate={state}\nworkspace={workspace}\n", encoding="utf-8")
    os.chown(path.parent, uid, gid)
    os.chmod(path.parent, 0o700)
    os.chown(path, uid, gid)
    os.chmod(path, 0o600)


def _marker_matches(path: pathlib.Path, workspace: pathlib.Path) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "managed_by=solo-vps\n" in text and f"workspace={workspace}\n" in text


def copy_workspace(
    source: pathlib.Path,
    destination: pathlib.Path,
    uid: int,
    gid: int,
    state_dir: pathlib.Path | None = None,
) -> None:
    temporary = destination.parent / f".{destination.name}.handoff-copy-{os.getpid()}"
    if temporary.exists():
        shutil.rmtree(temporary)
    try:
        shutil.copytree(source, temporary, symlinks=True, ignore=workspace_ignore(source))
        chown_tree(temporary, uid, gid)
        if state_dir is not None:
            _write_marker(_marker_path(state_dir, complete=False), destination, uid, gid, "incomplete")
        temporary.rename(destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        raise


def ensure_workspace(
    source: pathlib.Path,
    admin_user: str,
    admin_home: pathlib.Path,
    uid: int,
    gid: int,
    state_dir: pathlib.Path,
) -> pathlib.Path:
    destination = admin_home / "solo-vps"
    if source.resolve() == destination.resolve():
        return destination

    if destination.exists():
        if _marker_matches(_marker_path(state_dir, complete=True), destination) or _marker_matches(
            _marker_path(state_dir, complete=False), destination
        ):
            return destination
        raise HandoffError(
            f"refusing to overwrite existing unmanaged workspace {destination}; "
            "move it aside manually after reviewing its contents"
        )

    copy_workspace(source, destination, uid, gid, state_dir)
    return destination


def _copy_state_file(source: pathlib.Path, destination: pathlib.Path, uid: int, gid: int) -> str:
    if not source.is_file() or source.is_symlink():
        raise HandoffError(f"required controller state is not a regular file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.exists():
        if not destination.is_file() or destination.is_symlink():
            raise HandoffError(f"refusing non-regular admin state path: {destination}")
        if source.read_bytes() != destination.read_bytes():
            raise HandoffError(f"refusing to overwrite different existing admin state: {destination}")
        action = "kept"
    else:
        shutil.copyfile(source, destination)
        action = "copied"
    os.chown(destination.parent, uid, gid)
    os.chmod(destination.parent, 0o700)
    os.chown(destination, uid, gid)
    os.chmod(destination, 0o600)
    return action


def copy_operator_state(
    config: pathlib.Path,
    inventory: pathlib.Path,
    admin_state_dir: pathlib.Path,
    uid: int,
    gid: int,
) -> tuple[str, str]:
    config_action = _copy_state_file(config, admin_state_dir / "config/config.yml", uid, gid)
    inventory_action = _copy_state_file(inventory, admin_state_dir / "config/hosts.yml", uid, gid)
    return config_action, inventory_action


def finalize_workspace(state_dir: pathlib.Path, workspace: pathlib.Path, uid: int, gid: int) -> None:
    incomplete = _marker_path(state_dir, complete=False)
    complete = _marker_path(state_dir, complete=True)
    _write_marker(complete, workspace, uid, gid, "ready")
    if incomplete.exists():
        incomplete.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--inventory", type=pathlib.Path, required=True)
    parser.add_argument("--state-dir", type=pathlib.Path, required=True)
    parser.add_argument("--admin-state-dir", type=pathlib.Path, default=None)
    args = parser.parse_args()

    source = args.root.resolve()
    config_path = args.config.expanduser().resolve()
    inventory_path = args.inventory.expanduser().resolve()
    try:
        config = load_yaml(config_path, "config")
        inventory = load_yaml(inventory_path, "inventory")
        host, ansible_user, _, _ = extract_inputs(config, inventory)
        admin_user = str(config["admin"]["user"]).strip()
        if not admin_user:
            raise HandoffError("admin.user is empty")
        if ansible_user != admin_user:
            raise HandoffError(
                f"inventory must already use admin.user '{admin_user}' before workspace handoff; found '{ansible_user}'"
            )

        target_addresses = resolve_host(host)
        if not (target_addresses & local_addresses()):
            print("PASS admin workspace handoff: controller is separate from the target VPS")
            print("  no local project copy or controller state was changed")
            return 0

        if os.geteuid() != 0:
            current_user = pwd.getpwuid(os.geteuid()).pw_name
            account = pwd.getpwnam(admin_user)
            admin_home = pathlib.Path(account.pw_dir)
            if current_user == admin_user and source == admin_home / "solo-vps":
                if args.admin_state_dir is not None or not admin_data_parents_need_repair(
                    admin_home, account.pw_uid, account.pw_gid
                ):
                    print("PASS admin workspace handoff: already running from the managed admin workspace")
                    print(f"  workspace: {source}")
                    print(f"  state: {args.state_dir.expanduser().resolve()}")
                    return 0
                # Older handoffs could leave ~/.local or ~/.local/share root-owned.
                # Re-enter the same bounded root path to repair only those user data parents.
            # A provider account (for example ubuntu) already needs passwordless
            # sudo for bootstrap. Elevate this bounded handoff, with resolved
            # arguments; do not rely on sudo preserving HOME or environment.
            command = [
                "sudo", "-n", "--", sys.executable, str(pathlib.Path(__file__).resolve()),
                "--root", str(source), "--config", str(config_path),
                "--inventory", str(inventory_path),
                "--state-dir", str(args.state_dir.expanduser().resolve()),
            ]
            if args.admin_state_dir is not None:
                command.extend(["--admin-state-dir", str(args.admin_state_dir.expanduser().resolve())])
            return subprocess.run(command, check=False).returncode

        account = pwd.getpwnam(admin_user)
        admin_home = pathlib.Path(account.pw_dir)
        admin_state_dir = (
            args.admin_state_dir.expanduser().resolve()
            if args.admin_state_dir is not None
            else admin_home / ".local/share/solo-vps"
        )
        if args.admin_state_dir is None:
            ensure_admin_data_parents(admin_home, account.pw_uid, account.pw_gid)
        workspace = ensure_workspace(source, admin_user, admin_home, account.pw_uid, account.pw_gid, admin_state_dir)
        config_action, inventory_action = copy_operator_state(
            config_path, inventory_path, admin_state_dir, account.pw_uid, account.pw_gid
        )

        # Toolchains/collections are intentionally rebuilt under the admin's persistent data root;
        # non-relocatable root controller state is never copied into the source checkout.
        run_as_admin(admin_user, workspace, ["make", "setup"])
        run_as_admin(admin_user, workspace, ["make", "prepare-access"])
        run_as_admin(admin_user, workspace, ["make", "doctor"])
        finalize_workspace(admin_state_dir, workspace, account.pw_uid, account.pw_gid)
    except (AccessError, HandoffError, KeyError, OSError) as exc:
        print(f"ERROR admin workspace handoff: {exc}", file=sys.stderr)
        return 2

    print("PASS admin workspace handoff")
    print(f"  workspace: {workspace}")
    print(f"  state: {admin_state_dir}")
    print(f"  config: {config_action}")
    print(f"  inventory: {inventory_action}")
    print(f"  owner: {admin_user}")
    print("  controller_key: prepared under the admin account")
    print("  source checkout state: none generated; toolchain rebuilt outside the checkout")
    print(f"NEXT: open a fresh SSH session as {admin_user}, then: cd ~/solo-vps && make doctor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
