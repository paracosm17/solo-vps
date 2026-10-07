#!/usr/bin/env python3
"""Block two forbidden proxy publications before Docker starts containers.

Preserve all shared firewall rules. The guard does not block outbound replies,
application HTTP/HTTPS DNAT, localhost administration, or TCP SSH.
"""
from __future__ import annotations
import argparse
import json
import re
import shlex
import subprocess
import sys

CHAIN = 'SOLO-VPS-PROXY-EDGE'


class GuardError(ValueError):
    pass


def rules(interfaces: list[str]) -> list[list[str]]:
    if not interfaces or any(not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,15}', name) for name in interfaces):
        raise GuardError('Guard requires explicit external interfaces')
    return [['-i', name, '-p', protocol, '-m', 'conntrack', '--ctdir', 'ORIGINAL',
             '--ctorigdstport', port, '-m', 'comment', '--comment', 'Solo VPS proxy ingress', '-j', 'DROP']
            for name in sorted(set(interfaces)) for protocol, port in [('tcp', '8080'), ('udp', '443')]]


def invoke(binary: str, args: list[str], required: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run([binary, '-w', '5', *args], capture_output=True, text=True, timeout=15)
    if required and result.returncode:
        raise GuardError('Cannot establish or verify proxy ingress guard')
    return result


def reconcile(binary: str, interfaces: list[str], check: bool) -> bool:
    wanted = rules(interfaces)
    changed = False
    own = invoke(binary, ['-S', CHAIN], required=False)
    if own.returncode:
        if check:
            raise GuardError('Proxy ingress guard is missing')
        invoke(binary, ['-N', CHAIN]); changed = True
    else:
        existing = [shlex.split(line)[2:] for line in own.stdout.splitlines() if line.startswith('-A ')]
        # iptables may add the implied tcp/udp module to its normalized output.
        for entry in existing:
            for protocol in ('tcp', 'udp'):
                for index in range(len(entry) - 1):
                    if entry[index:index + 2] == ['-m', protocol]:
                        del entry[index:index + 2]
                        break
        def canonical(entry):
            return sorted(zip(entry[::2], entry[1::2]))
        if any(canonical(entry) not in [canonical(rule) for rule in wanted] for entry in existing):
            raise GuardError('Reserved guard chain contains unrecognized rules; preserve and review it')
    for rule in wanted:
        if invoke(binary, ['-C', CHAIN, *rule], required=False).returncode:
            if check:
                raise GuardError('Proxy ingress guard rule is missing')
            invoke(binary, ['-A', CHAIN, *rule]); changed = True
    # Prepare Docker's documented user chain before dockerd can start workloads.
    # No flush or replacement of Docker/UFW/operator rules is allowed.
    if invoke(binary, ['-S', 'DOCKER-USER'], required=False).returncode:
        if check:
            raise GuardError('Docker user chain is missing')
        invoke(binary, ['-N', 'DOCKER-USER']); changed = True
    for parent, child in [('DOCKER-USER', CHAIN), ('INPUT', CHAIN), ('FORWARD', 'DOCKER-USER')]:
        output = invoke(binary, ['-S', parent]).stdout
        entries = [shlex.split(line)[2:] for line in output.splitlines() if line.startswith('-A ')]
        jump = ['-j', child]
        if not entries or entries[0] != jump:
            if check:
                raise GuardError('Proxy guard must precede shared accept rules')
            while invoke(binary, ['-C', parent, *jump], required=False).returncode == 0:
                invoke(binary, ['-D', parent, *jump])
            invoke(binary, ['-I', parent, '1', *jump]); changed = True
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interface', action='append', required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        changed = False
        for binary in ('/usr/sbin/iptables', '/usr/sbin/ip6tables'):
            changed = reconcile(binary, args.interface, args.check) or changed
        print(json.dumps({'changed': changed, 'ipv4_guard': True, 'ipv6_guard': True}))
    except (GuardError, OSError, ValueError, subprocess.TimeoutExpired):
        print('ERROR: proxy ingress guard failed; Docker startup must remain blocked', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
