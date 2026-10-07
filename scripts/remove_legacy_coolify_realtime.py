#!/usr/bin/env python3
"""Retire only the owned standalone realtime container before embedded Reverb starts."""
import json
import re
import subprocess


def retire(run=subprocess.run):
    result = run(['/usr/bin/docker', 'inspect', 'coolify-realtime'], capture_output=True, text=True)
    if result.returncode:
        if 'No such object: coolify-realtime' in result.stderr or 'No such container: coolify-realtime' in result.stderr:
            return {'changed': False}
        raise ValueError('cannot inspect legacy realtime; refusing removal')
    container = json.loads(result.stdout)[0]
    config = container['Config']
    labels = config.get('Labels') or {}
    if container.get('Name') != '/coolify-realtime' or labels.get('coolify.managed') != 'true' or not re.fullmatch(
            r'(?:(?:docker\.io|ghcr\.io)/)?coollabsio/coolify-realtime:[0-9]+\.[0-9]+\.[0-9]+', config.get('Image', '')):
        raise ValueError('legacy realtime ownership is unknown; refusing removal')
    # Use the inspected ID, never remove a replacement that reused the name.
    run(['/usr/bin/docker', 'rm', '-f', container['Id']], capture_output=True, check=True)
    return {'changed': True}


if __name__ == '__main__':
    try:
        print(json.dumps(retire()))
    except (ValueError, KeyError, subprocess.SubprocessError):
        raise SystemExit('ERROR: legacy realtime retirement failed; transaction retained')
