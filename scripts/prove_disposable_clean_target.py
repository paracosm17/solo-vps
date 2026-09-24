#!/usr/bin/env python3
"""Run the provider-neutral CRIT-004 clean Ubuntu target proof.

This maintainer-only harness never creates or destroys provider resources. It
requires an explicitly marked fresh Ubuntu 24.04 target, keeps all generated
keys/config in a temporary controller directory, runs the critical host flow,
and writes only a sanitized machine-readable evidence summary outside the
source checkout.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from typing import Iterable

import yaml


CONFIRMATION = "I_HAVE_REVIEWED_THE_DISPOSABLE_CLEAN_TARGET"
PROVIDER_RECOVERY_CONFIRMATION = "I_HAVE_VERIFIED_DISPOSABLE_PROVIDER_RECOVERY"
MARKER_PATH = "/root/.solo-vps-disposable-clean-target"
ID_RE = re.compile(r"^[A-Za-z0-9._-]{12,128}$")
FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{20,}={0,2}$")
RECAP_RE = re.compile(
    r"(?m)^\S+\s*:\s+ok=(?P<ok>\d+)\s+changed=(?P<changed>\d+)\s+"
    r"unreachable=(?P<unreachable>\d+)\s+failed=(?P<failed>\d+)"
)
SSH_KEY_PREFIXES = (
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
)


class ProofError(RuntimeError):
    pass


class CommandError(ProofError):
    def __init__(self, label: str, returncode: int, output: str):
        super().__init__(f"{label} failed with exit code {returncode}")
        self.label = label
        self.returncode = returncode
        self.output = output


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_inputs(args: argparse.Namespace) -> None:
    if args.confirm != CONFIRMATION:
        raise ProofError("explicit disposable-target confirmation is required")
    if args.provider_recovery_confirm != PROVIDER_RECOVERY_CONFIRMATION:
        raise ProofError("provider console/recovery confirmation is required before automated SSH hardening")
    if not ID_RE.fullmatch(args.target_id):
        raise ProofError("target id must be 12-128 characters containing only letters, digits, '.', '_', or '-'")
    if not FINGERPRINT_RE.fullmatch(args.host_key_sha256):
        raise ProofError("host key fingerprint must use the OpenSSH SHA256:<base64> form")
    identity = args.bootstrap_identity.expanduser().resolve()
    if not identity.is_file() or identity.is_symlink():
        raise ProofError("bootstrap identity must be an existing regular private-key file")
    if args.bootstrap_user.strip() != args.bootstrap_user or not args.bootstrap_user:
        raise ProofError("bootstrap user must be a non-empty SSH account name")
    if args.admin_user.strip() != args.admin_user or not args.admin_user:
        raise ProofError("admin user must be a non-empty SSH account name")


def resolve_ips(host: str) -> set[ipaddress._BaseAddress]:
    resolved: set[ipaddress._BaseAddress] = set()
    try:
        resolved.add(ipaddress.ip_address(host))
        return resolved
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ProofError(f"cannot resolve disposable target host: {exc}") from exc
    for info in infos:
        try:
            resolved.add(ipaddress.ip_address(info[4][0]))
        except ValueError:
            pass
    if not resolved:
        raise ProofError("disposable target host resolved to no IP addresses")
    return resolved


def local_ips() -> set[ipaddress._BaseAddress]:
    result: set[ipaddress._BaseAddress] = {
        ipaddress.ip_address("127.0.0.1"),
        ipaddress.ip_address("::1"),
    }
    try:
        proc = subprocess.run(
            ["ip", "-o", "addr", "show"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return result
    for line in proc.stdout.splitlines():
        parts = line.split()
        for index, token in enumerate(parts[:-1]):
            if token not in {"inet", "inet6"}:
                continue
            try:
                result.add(ipaddress.ip_address(parts[index + 1].split("/", 1)[0]))
            except ValueError:
                pass
    return result


def configured_production_host() -> str | None:
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    data_dir = Path(os.environ.get("SOLO_VPS_DATA_DIR", str(base / "solo-vps")))
    config_override = os.environ.get("SOLO_VPS_CONFIG") or os.environ.get("CONFIG")
    config = Path(config_override or str(data_dir / "config/config.yml")).expanduser()
    if not config.is_file() or config.is_symlink():
        return None
    try:
        data = yaml.safe_load(config.read_text(encoding="utf-8"))
        host = str(data["server"]["host"]).strip()
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return None
    return host or None


def refuse_production_or_local_target(target: str) -> None:
    target_ips = resolve_ips(target)
    if target_ips & local_ips():
        raise ProofError("refusing a disposable proof against the current controller host")
    production = configured_production_host()
    if not production:
        return
    if production == target:
        raise ProofError("refusing a disposable proof against the configured Solo VPS production host")
    try:
        production_ips = resolve_ips(production)
    except ProofError:
        production_ips = set()
    if target_ips & production_ips:
        raise ProofError("refusing a disposable proof against an IP used by the configured production host")


def run_capture(
    label: str,
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 1800,
    expected_rc: int = 0,
) -> str:
    print(f"RUN {label} ...", flush=True)
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProofError(f"{label} could not complete: {exc}") from exc
    if proc.returncode != expected_rc:
        raise CommandError(label, proc.returncode, proc.stdout)
    print(f"PASS {label}", flush=True)
    return proc.stdout


def sanitize_failure(text: str, target: str, private_paths: Iterable[Path]) -> str:
    value = text.replace(target, "<disposable-target>")
    for path in private_paths:
        value = value.replace(str(path), "<private-key-path>")
    value = re.sub(
        r"(?m)^(\s*(?:changed|ok):\s*\[[^\]]+\].*item=)(ssh-(?:ed25519|rsa)\s+)[A-Za-z0-9+/=]+.*$",
        r"\1\2<redacted-public-key>",
        value,
    )
    value = re.sub(r"(?m)(ssh-(?:ed25519|rsa)\s+)[A-Za-z0-9+/=]{20,}(?:\s+[^\r\n]+)?", r"\1<redacted-public-key>", value)
    lines = value.splitlines()
    return "\n".join(lines[-120:])


def ssh_keyscan(target: str, expected_fingerprint: str, known_hosts: Path) -> None:
    scan = run_capture(
        "read disposable target Ed25519 host key",
        ["ssh-keyscan", "-T", "10", "-t", "ed25519", target],
        timeout=30,
    )
    lines = [line for line in scan.splitlines() if line and not line.startswith("#")]
    if not lines:
        raise ProofError("ssh-keyscan returned no Ed25519 host key")
    known_hosts.write_text("\n".join(lines) + "\n", encoding="utf-8")
    known_hosts.chmod(0o600)
    fingerprint_output = run_capture(
        "verify disposable target host-key fingerprint",
        ["ssh-keygen", "-lf", str(known_hosts), "-E", "sha256"],
        timeout=30,
    )
    observed = {
        fields[1]
        for fields in (line.split() for line in fingerprint_output.splitlines())
        if len(fields) >= 2
    }
    if observed != {expected_fingerprint}:
        raise ProofError("disposable target Ed25519 host-key fingerprint does not match the provider-console value")


def ssh_command(identity: Path, known_hosts: Path, user: str, target: str, remote: str) -> list[str]:
    return [
        "ssh",
        "-i",
        str(identity),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        "ConnectTimeout=15",
        f"{user}@{target}",
        remote,
    ]


def remote_clean_preflight(args: argparse.Namespace, known_hosts: Path) -> dict[str, str]:
    marker = MARKER_PATH
    admin = args.admin_user
    script = f"""
set -eu
if [ "$(id -u)" -eq 0 ]; then
  ROOT=''
else
  sudo -n true
  ROOT='sudo -n'
fi
. /etc/os-release
printf 'OS_ID=%s\\nOS_VERSION=%s\\nOS_CODENAME=%s\\n' "$ID" "$VERSION_ID" "${{VERSION_CODENAME:-}}"
printf 'ARCH=%s\\n' "$(uname -m)"
marker_value=$($ROOT cat {marker})
marker_mode=$($ROOT stat -c '%U:%G:%a' {marker})
printf 'MARKER_VALUE=%s\\nMARKER_MODE=%s\\n' "$marker_value" "$marker_mode"
command -v docker >/dev/null 2>&1 && {{ echo 'DIRTY=docker-command'; exit 42; }} || true
$ROOT test ! -e /etc/docker/daemon.json || {{ echo 'DIRTY=docker-config'; exit 42; }}
$ROOT test ! -e /data/coolify/.solo-vps-managed || {{ echo 'DIRTY=coolify-marker'; exit 42; }}
$ROOT test ! -e /etc/solo-vps || {{ echo 'DIRTY=solo-vps-etc'; exit 42; }}
$ROOT test ! -e /etc/ssh/sshd_config.d/99-solo-vps.conf || {{ echo 'DIRTY=solo-vps-ssh'; exit 42; }}
getent passwd {admin} >/dev/null 2>&1 && {{ echo 'DIRTY=managed-admin-exists'; exit 42; }} || true
if command -v ufw >/dev/null 2>&1; then
  status=$($ROOT ufw status | head -n 1 || true)
  [ "$status" != 'Status: active' ] || {{ echo 'DIRTY=ufw-active'; exit 42; }}
fi
printf 'CLEAN=YES\\n'
""".strip()
    output = run_capture(
        "clean Ubuntu target preflight",
        ssh_command(args.bootstrap_identity, known_hosts, args.bootstrap_user, args.target, script),
        timeout=60,
    )
    facts: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            facts[key] = value
    if facts.get("OS_ID") != "ubuntu" or facts.get("OS_VERSION") != "24.04" or facts.get("OS_CODENAME") != "noble":
        raise ProofError("disposable target must be a clean Ubuntu 24.04 LTS (noble) host")
    if facts.get("MARKER_VALUE") != args.target_id:
        raise ProofError("disposable target marker value does not match the requested target id")
    if facts.get("MARKER_MODE") != "root:root:600":
        raise ProofError("disposable target marker must be root:root mode 0600")
    if facts.get("CLEAN") != "YES":
        raise ProofError("disposable target clean-state preflight did not complete")
    return facts


def generate_key(path: Path, comment: str) -> tuple[Path, Path, str]:
    run_capture(
        f"generate ephemeral {comment} key",
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", comment, "-f", str(path)],
        timeout=30,
    )
    private = path
    public = Path(str(path) + ".pub")
    line = public.read_text(encoding="utf-8").strip()
    if not line.startswith("ssh-ed25519 "):
        raise ProofError("ephemeral public key generation returned an unexpected key type")
    return private, public, line


def write_test_config(root: Path, config: Path, inventory: Path, args: argparse.Namespace, automation_pub: Path, human_key: str) -> None:
    data = yaml.safe_load((root / "config/config.example.yml").read_text(encoding="utf-8"))
    data["server"]["host"] = args.target
    data["server"]["hostname"] = f"solo-vps-clean-{args.target_id[:8].lower()}"
    data["server"]["timezone"] = "UTC"
    data["admin"]["user"] = args.admin_user
    data["admin"]["ssh_public_key_file"] = str(automation_pub)
    data["admin"]["human_ssh_public_key"] = human_key
    config.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    config.chmod(0o600)
    shutil.copy2(root / "ansible/inventories/example/hosts.yml", inventory)
    inventory.chmod(0o600)


def make_env(config: Path, inventory: Path, identity: Path, known_hosts: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "CONFIG": str(config),
            "INVENTORY": str(inventory),
            "ANSIBLE_PRIVATE_KEY_FILE": str(identity),
            "ANSIBLE_SSH_COMMON_ARGS": (
                f"-o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes "
                f"-o UserKnownHostsFile={known_hosts} -o ConnectTimeout=15"
            ),
        }
    )
    return env


def parse_recap(output: str, label: str) -> dict[str, int]:
    matches = list(RECAP_RE.finditer(output))
    if not matches:
        raise ProofError(f"{label} produced no parseable Ansible PLAY RECAP")
    match = matches[-1]
    return {key: int(match.group(key)) for key in ("ok", "changed", "unreachable", "failed")}


def require_recap_clean(recap: dict[str, int], label: str) -> None:
    if recap["unreachable"] != 0 or recap["failed"] != 0:
        raise ProofError(f"{label} recap is not clean: {recap}")


def exact_admin_login(identity: Path, known_hosts: Path, user: str, target: str, label: str) -> None:
    output = run_capture(
        label,
        ssh_command(identity, known_hosts, user, target, "id -un && sudo -n id -u"),
        timeout=45,
    )
    if output.strip().splitlines() != [user, "0"]:
        raise ProofError(f"{label} did not prove the expected admin identity plus passwordless sudo")


def require_root_login_denied(identity: Path, known_hosts: Path, target: str) -> None:
    print("RUN prove direct root SSH is denied after hardening ...", flush=True)
    proc = subprocess.run(
        ssh_command(identity, known_hosts, "root", target, "true"),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=45,
        check=False,
    )
    if proc.returncode == 0:
        raise ProofError("direct root SSH unexpectedly succeeded after hardening")
    print("PASS prove direct root SSH is denied after hardening", flush=True)


def tree_fingerprint(root: Path) -> str:
    git = shutil.which("git")
    if git and (root / ".git").exists():
        proc = subprocess.run([git, "rev-parse", "HEAD"], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
        if proc.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}\n?", proc.stdout):
            return f"git:{proc.stdout.strip()}"
    digest = hashlib.sha256()
    excluded_parts = {".git", ".venv", "__pycache__", ".pytest_cache"}
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not (set(p.relative_to(root).parts) & excluded_parts)):
        rel = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        digest.update(path.read_bytes())
    return f"tree-sha256:{digest.hexdigest()}"


def write_evidence(evidence_dir: Path, data: dict[str, object]) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        evidence_dir.chmod(0o700)
    except OSError:
        pass
    destination = evidence_dir / "clean-target-evidence.json"
    destination.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    destination.chmod(0o600)
    return destination


def run_proof(args: argparse.Namespace) -> Path:
    root = args.root.resolve()
    validate_inputs(args)
    refuse_production_or_local_target(args.target)
    for command in ("make", "ssh", "ssh-keygen", "ssh-keyscan"):
        if shutil.which(command) is None:
            raise ProofError(f"required controller command is unavailable: {command}")

    source_ref = tree_fingerprint(root)
    default_evidence = Path.home() / ".local/share/solo-vps/evidence/disposable-clean-target" / args.target_id
    evidence_dir = (args.evidence_dir or default_evidence).expanduser().resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError:
        pass
    else:
        raise ProofError("evidence directory must stay outside the Solo VPS source checkout")

    started = now_utc()
    with tempfile.TemporaryDirectory(prefix="solo-vps-clean-target-") as tmp_name:
        tmp = Path(tmp_name)
        known_hosts = tmp / "known_hosts"
        config = tmp / "config.yml"
        inventory = tmp / "hosts.yml"
        automation_private, automation_public, _ = generate_key(tmp / "automation", "solo-vps-disposable-automation")
        human_private, _, human_public_line = generate_key(tmp / "human", "solo-vps-disposable-human")
        private_paths = (args.bootstrap_identity, automation_private, human_private)
        try:
            ssh_keyscan(args.target, args.host_key_sha256, known_hosts)
            facts = remote_clean_preflight(args, known_hosts)
            write_test_config(root, config, inventory, args, automation_public, human_public_line)

            bootstrap_env = make_env(config, inventory, args.bootstrap_identity, known_hosts)
            admin_env = make_env(config, inventory, automation_private, known_hosts)

            run_capture("pinned controller QA check", ["make", "--no-print-directory", "qa-check"], cwd=root, env=bootstrap_env, timeout=180)
            run_capture(
                "configure disposable bootstrap inventory",
                ["make", "--no-print-directory", f"SSH_USER={args.bootstrap_user}", "use-bootstrap"],
                cwd=root,
                env=bootstrap_env,
                timeout=60,
            )
            run_capture("separate-controller access preflight", ["make", "--no-print-directory", "prepare-access"], cwd=root, env=bootstrap_env, timeout=60)
            run_capture("disposable target doctor", ["make", "--no-print-directory", "doctor"], cwd=root, env=bootstrap_env, timeout=180)
            first_bootstrap_output = run_capture("first clean-target bootstrap", ["make", "--no-print-directory", "bootstrap"], cwd=root, env=bootstrap_env, timeout=1800)
            first_recap = parse_recap(first_bootstrap_output, "first bootstrap")
            require_recap_clean(first_recap, "first bootstrap")
            if first_recap["changed"] <= 0:
                raise ProofError("clean target bootstrap unexpectedly reported changed=0")

            run_capture("switch disposable inventory to managed admin", ["make", "--no-print-directory", "use-admin"], cwd=root, env=admin_env, timeout=60)
            run_capture("read-only verify after first bootstrap", ["make", "--no-print-directory", "verify"], cwd=root, env=admin_env, timeout=600)
            exact_admin_login(human_private, known_hosts, args.admin_user, args.target, "fresh exact human-key admin login before hardening")

            hardened_env = admin_env.copy()
            hardened_env["SSH_HARDENING_CONFIRM"] = "I_HAVE_VERIFIED_PROVIDER_RECOVERY"
            hardened_env["SSH_HARDENING_ADMIN_LOGIN_CONFIRM"] = "I_HAVE_VERIFIED_WORKSTATION_ADMIN_LOGIN"
            run_capture("proof-gated SSH hardening", ["make", "--no-print-directory", "ssh-harden"], cwd=root, env=hardened_env, timeout=600)
            run_capture("verify hardened SSH", ["make", "--no-print-directory", "verify-ssh"], cwd=root, env=admin_env, timeout=300)
            exact_admin_login(human_private, known_hosts, args.admin_user, args.target, "fresh exact human-key admin login after hardening")
            require_root_login_denied(args.bootstrap_identity, known_hosts, args.target)
            run_capture("security audit after hardening", ["make", "--no-print-directory", "audit"], cwd=root, env=admin_env, timeout=600)

            second_bootstrap_output = run_capture("idempotency bootstrap rerun", ["make", "--no-print-directory", "bootstrap"], cwd=root, env=admin_env, timeout=1800)
            second_recap = parse_recap(second_bootstrap_output, "second bootstrap")
            require_recap_clean(second_recap, "second bootstrap")
            if second_recap["changed"] != 0:
                raise ProofError(f"idempotency bootstrap rerun must report changed=0; got {second_recap['changed']}")
            run_capture("final read-only verify", ["make", "--no-print-directory", "verify"], cwd=root, env=admin_env, timeout=600)
            run_capture("final security audit", ["make", "--no-print-directory", "audit"], cwd=root, env=admin_env, timeout=600)
        except CommandError as exc:
            print(
                "ERROR disposable clean-target command failed; sanitized tail follows. "
                "The target is intentionally left intact for provider-console/SSH diagnosis.",
                file=sys.stderr,
            )
            print(sanitize_failure(exc.output, args.target, private_paths), file=sys.stderr)
            raise

        evidence = {
            "schema_version": 1,
            "proof": "crit-004-disposable-clean-target-core",
            "started_at_utc": started,
            "finished_at_utc": now_utc(),
            "source": source_ref,
            "target": {
                "address_retained": False,
                "marker_value_retained": False,
                "host_key_fingerprint_retained": False,
                "os": "Ubuntu 24.04 LTS",
                "codename": "noble",
                "architecture": facts.get("ARCH", "unknown"),
                "clean_preflight": "PASS",
            },
            "controller": {
                "generated_private_keys_retained": False,
                "raw_command_logs_retained": False,
                "production_config_reused": False,
            },
            "steps": {
                "qa_check": "PASS",
                "doctor_bootstrap_identity": "PASS",
                "first_bootstrap": {**first_recap, "status": "PASS"},
                "verify_after_bootstrap": "PASS",
                "human_admin_login_before_hardening": "PASS",
                "ssh_hardening": "PASS",
                "verify_ssh": "PASS",
                "human_admin_login_after_hardening": "PASS",
                "direct_root_ssh_after_hardening": "DENIED",
                "audit_after_hardening": "PASS",
                "second_bootstrap": {**second_recap, "status": "PASS"},
                "final_verify": "PASS",
                "final_audit": "PASS",
            },
            "idempotency": {
                "second_bootstrap_changed": second_recap["changed"],
                "second_bootstrap_failed": second_recap["failed"],
                "status": "PASS",
            },
            "scope": {
                "host_baseline": "PROVEN",
                "ssh_hardening": "PROVEN",
                "coolify_installation": "NOT_RUN",
                "backup_restore": "NOT_RUN",
                "observability_credentials": "NOT_RUN",
            },
            "disposal": {
                "provider_resource_destroyed_by_harness": False,
                "operator_must_destroy_target_after_evidence": True,
            },
            "public_safe": True,
        }
        return write_evidence(evidence_dir, evidence)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--target", required=True)
    parser.add_argument("--bootstrap-user", default="root")
    parser.add_argument("--bootstrap-identity", type=Path, required=True)
    parser.add_argument("--admin-user", default="ops")
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--host-key-sha256", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--provider-recovery-confirm", required=True)
    parser.add_argument("--evidence-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.bootstrap_identity = args.bootstrap_identity.expanduser().resolve()
    try:
        evidence = run_proof(args)
    except ProofError as exc:
        print(f"ERROR disposable clean-target proof: {exc}", file=sys.stderr)
        return 2
    print("PASS CRIT-004 disposable clean-target core proof")
    print("  target_address_retained: false")
    print("  generated_private_keys_retained: false")
    print("  raw_command_logs_retained: false")
    print("  second_bootstrap_changed: 0")
    print("  second_bootstrap_failed: 0")
    print(f"  sanitized_evidence: {evidence}")
    print("  next: destroy the disposable VPS in the provider control plane after reviewing the evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
