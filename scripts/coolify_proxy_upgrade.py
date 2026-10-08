#!/usr/bin/env python3
"""Explicit, checkpointed native Traefik lifecycle; never changes application containers."""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import time
import yaml
try:
    from .coolify_proxy_policy import PolicyError, native, proxy_state, run, safe_publications, policy_configuration
    from .coolify_release import load_release, release_fingerprint
except ImportError:
    from coolify_proxy_policy import PolicyError, native, proxy_state, run, safe_publications, policy_configuration
    from coolify_release import load_release, release_fingerprint

CONFIRM = 'I_HAVE_REVIEWED_THE_PROXY_UPGRADE_PLAN'
STATE = Path('/var/lib/solo-vps/proxy-upgrade')
PROXY = Path('/data/coolify/proxy')
CHECKPOINTS = Path('/var/lib/solo-vps/checkpoints')


def target_ids(policy):
    return {policy['image_id_x86_64'], policy.get('image_config_id_x86_64', policy['image_id_x86_64'])}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def replace_image(configuration, image):
    """Replace exactly one scalar; reject aliases, duplicate keys and inline services."""
    def field(node, name):
        if not isinstance(node, yaml.MappingNode) or node.flow_style:
            raise PolicyError('Unsupported proxy YAML shape')
        values = [v for k, v in node.value if k.value == name]
        if len(values) != 1:
            raise PolicyError('Missing or ambiguous proxy image')
        return values[0]
    # Validate native ownership and require the already-safe edge policy.
    if policy_configuration(configuration)[1]:
        raise PolicyError('Apply the host edge policy before proxy upgrade')
    node = field(field(field(yaml.compose(configuration), 'services'), 'traefik'), 'image')
    if not isinstance(node, yaml.ScalarNode) or configuration[node.start_mark.index:node.end_mark.index].startswith(('&', '*')):
        raise PolicyError('Aliased proxy image requires operator review')
    return configuration[:node.start_mark.index] + json.dumps(image) + configuration[node.end_mark.index:]


def inspect_plan(configuration, before, model):
    if not before or not before['State'].get('Running') or before['State'].get('Health', {}).get('Status') != 'healthy':
        raise PolicyError('A healthy owned proxy is required')
    if not safe_publications(before) or policy_configuration(configuration)[1]:
        raise PolicyError('Unsafe proxy publications')
    if model['services']['traefik']['image'] != before['Config']['Image']:
        raise PolicyError('Saved and running proxy images disagree')
    networks = {v.get('name', k) for k, v in model.get('networks', {}).items()}
    attached = set(before.get('NetworkSettings', {}).get('Networks', {}))
    if not attached or not attached <= networks:
        raise PolicyError('Native restart cannot prove preservation of attached networks')
    return sorted(attached)


def private_json(path, data):
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def checkpoint(before, original, target, fingerprint, networks):
    image_details = json.loads(run(['/usr/bin/docker', 'image', 'inspect', before['Image']]))[0]
    digests = [value.split('@', 1)[1] for value in image_details.get('RepoDigests', [])
               if value.startswith(('traefik@sha256:', 'docker.io/library/traefik@sha256:'))]
    if not digests or image_details['Id'] != before['Image']:
        raise PolicyError('Previous image requires an immutable official repository digest')
    pinned_old = before['Config']['Image'].split('@', 1)[0] + '@' + sorted(digests)[0]
    if shutil.disk_usage(CHECKPOINTS).free < 1024**3:
        raise PolicyError('Insufficient checkpoint space')
    directory = Path(tempfile.mkdtemp(prefix='proxy-', dir=CHECKPOINTS))
    os.chmod(directory, 0o700)
    config = directory / 'native.yml'
    config.write_text(original)
    os.chmod(config, 0o600)
    archive = directory / 'proxy.tar.gz'
    with tarfile.open(archive, 'w:gz', dereference=False) as stream:
        stream.add(PROXY, arcname='proxy', filter=lambda member: None if Path(member.name).name.startswith('access.log') else member)
    os.chmod(archive, 0o600)
    with tarfile.open(archive) as stream:
        for member in stream:
            if member.isfile():
                with stream.extractfile(member) as value:
                    while value.read(1024**2):
                        pass
    image = directory / 'previous-image.tar'
    run(['/usr/bin/docker', 'image', 'save', '--output', str(image), before['Image']])
    os.chmod(image, 0o600)
    hashes = {}
    for path in (config, archive, image):
        with path.open('r+b') as stream:
            hashes[path.name] = hashlib.file_digest(stream, 'sha256').hexdigest()
            os.fsync(stream.fileno())
    record = {'schema': 1, 'state': 'prepared', 'checkpoint': str(directory), 'fingerprint': fingerprint,
              'original_sha256': digest(original), 'target_sha256': digest(target),
              'old_image': before['Config']['Image'], 'old_id': before['Image'],
              'old_image_pinned': pinned_old,
              'networks': networks, 'files': hashes}
    private_json(directory / 'transaction.json', record)
    return record


def read_checkpoint(path, fingerprint):
    if path.is_symlink() or path.resolve().parent != CHECKPOINTS.resolve() or not path.name.startswith('proxy-'):
        raise PolicyError('Unknown checkpoint location')
    if path.stat().st_uid != 0 or path.stat().st_mode & 0o077:
        raise PolicyError('Checkpoint must remain root-private')
    record = json.loads((path / 'transaction.json').read_text())
    if record.get('schema') != 1 or record.get('fingerprint') != fingerprint or record.get('checkpoint') != str(path):
        raise PolicyError('Checkpoint belongs to another integration')
    if set(record['files']) != {'native.yml', 'proxy.tar.gz', 'previous-image.tar'}:
        raise PolicyError('Incomplete checkpoint members')
    for name, expected in record['files'].items():
        if name not in ('native.yml', 'proxy.tar.gz', 'previous-image.tar'):
            raise PolicyError('Unknown checkpoint member')
        member = path / name
        if member.is_symlink() or not member.is_file():
            raise PolicyError('Unsafe checkpoint member')
        with member.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise PolicyError('Checkpoint checksum mismatch')
    return record


def wait_verified(expected_id, version, networks):
    for _ in range(90):
        value = proxy_state('/usr/bin/docker')
        if value and value['State'].get('Running') and value['State'].get('Health', {}).get('Status') == 'healthy':
            identities = {expected_id} if isinstance(expected_id, str) else expected_id
            if value['Image'] not in identities or not safe_publications(value) or not set(networks) <= set(value['NetworkSettings']['Networks']):
                raise PolicyError('Proxy identity, network or edge verification failed')
            actual = run(['/usr/bin/docker', 'exec', 'coolify-proxy', 'traefik', 'version'])
            if f'Version:      {version}\n' not in actual:
                raise PolicyError('Unexpected Traefik binary version')
            return
        time.sleep(2)
    raise PolicyError('Proxy health did not recover; checkpoint retained')


def execute(manifest, admin, mode, confirmation='', recovery=None, interrupt=False):
    release = load_release(manifest)
    policy = release['proxy']
    fingerprint = release_fingerprint(release)
    docker = '/usr/bin/docker'
    pending = STATE / 'pending.json'
    if any(p.is_symlink() for p in (STATE, PROXY, CHECKPOINTS, pending)):
        raise PolicyError('Unsafe lifecycle path')
    if (PROXY / 'docker-compose.override.yml').exists():
        raise PolicyError('Remove or review proxy overrides before explicit upgrade')
    original = native(docker, {'mode': 'check', 'admin_user': admin})['configuration']
    if (PROXY / 'docker-compose.yml').read_text() != original:
        raise PolicyError('Native saved and on-disk configuration drifted')
    before = proxy_state(docker)
    if mode in ('upgrade', 'resume', 'rollback') and confirmation != CONFIRM:
        raise PolicyError('Explicit proxy plan confirmation required')
    if pending.exists() and mode not in ('resume', 'rollback'):
        raise PolicyError('Interrupted proxy upgrade requires explicit resume')
    if mode == 'rollback':
        record = read_checkpoint(recovery, fingerprint)
        if pending.exists() and json.loads(pending.read_text()).get('checkpoint') != str(recovery):
            raise PolicyError('Different pending transaction; retain it')
        versions = {x['image_id_x86_64']: x['version'] for x in policy['upgrade_from']}
        versions.update({identity: policy['version'] for identity in target_ids(policy)})
        if record['old_id'] not in versions:
            raise PolicyError('Unreviewed recovery image identity')
        version = versions[record['old_id']]
        old = replace_image((recovery / 'native.yml').read_text(), record['old_image_pinned'])
        if digest(original) not in (record['original_sha256'], record['target_sha256'], digest(old)):
            raise PolicyError('Concurrent configuration changes require manual recovery review')
        if not before or before['Image'] not in {record['old_id']} | target_ids(policy):
            raise PolicyError('Unexpected proxy image during recovery')
        run([docker, 'image', 'load', '--input', str(recovery / 'previous-image.tar')])
        # Native StartProxy pulls before recreation. Pin the previous digest so a
        # mutable tag can never replace the checkpoint image during recovery.
        native(docker, {'mode': 'save', 'admin_user': admin, 'configuration': old, 'original_sha256': digest(original), 'restart': True})
        wait_verified(record['old_id'], version, record['networks'])
        record['state'] = 'rolled_back'
        private_json(recovery / 'transaction.json', record)
        if pending.exists():
            pending.unlink()
        return {'changed': True, 'recovered': True, 'checkpoint': str(recovery)}
    target = replace_image(original, policy['image'])
    model = json.loads(run([docker, 'compose', '--project-directory', str(PROXY), '-f', '-', 'config', '--format', 'json'], original))
    if mode == 'resume':
        if not pending.exists():
            raise PolicyError('No pending transaction to resume')
        pointer = json.loads(pending.read_text())
        record = read_checkpoint(Path(pointer['checkpoint']), fingerprint)
        if {k: v for k, v in pointer.items() if k != 'state'} != {k: v for k, v in record.items() if k != 'state'}:
            raise PolicyError('Pending transaction record mismatch')
        old = (Path(record['checkpoint']) / 'native.yml').read_text()
        target = replace_image(old, policy['image'])
        if digest(original) not in (record['original_sha256'], record['target_sha256']):
            raise PolicyError('Proxy configuration changed after interruption')
        if before and before['Image'] not in {record['old_id']} | target_ids(policy):
            raise PolicyError('Proxy content changed after interruption')
    else:
        networks = inspect_plan(original, before, model)
        identities = {x['image_id_x86_64'] for x in policy['upgrade_from']} | target_ids(policy)
        if before['Image'] not in identities:
            raise PolicyError('Unreviewed source image identity')
        if before['Image'] in target_ids(policy) and original == target:
            wait_verified(target_ids(policy), policy['version'], networks)
            return {'changed': False, 'verified': True, 'version': policy['version']}
        if mode == 'preflight':
            return {'changed': False, 'upgrade_required': True, 'version': policy['version']}
    run([docker, 'pull', policy['image']])
    image = json.loads(run([docker, 'image', 'inspect', policy['image']]))[0]
    expected_digest = 'traefik@' + policy['image'].split('@')[1]
    if image['Id'] not in target_ids(policy) or image.get('Architecture') != 'amd64' or image.get('Os') != 'linux' or expected_digest not in image.get('RepoDigests', []):
        raise PolicyError('Pulled target identity differs from reviewed manifest')
    run([docker, 'compose', '--project-directory', str(PROXY), '-f', '-', 'config', '--quiet'], target)
    if mode != 'resume':
        record = checkpoint(before, original, target, fingerprint, networks)
        private_json(pending, record)
    native(docker, {'mode': 'save', 'admin_user': admin, 'configuration': target, 'original_sha256': digest(original), 'restart': False})
    if interrupt:
        raise PolicyError('EXPECTED EVALUATION INTERRUPTION after Save; resume the retained transaction')
    native(docker, {'mode': 'get', 'admin_user': admin, 'restart': True})
    wait_verified(target_ids(policy), policy['version'], record['networks'])
    persisted = native(docker, {'mode': 'check', 'admin_user': admin})['configuration']
    if persisted != target or (PROXY / 'docker-compose.yml').read_text() != target:
        raise PolicyError('Native target configuration changed during upgrade')
    record['state'] = 'complete'
    private_json(Path(record['checkpoint']) / 'transaction.json', record)
    pending.unlink()
    return {'changed': True, 'verified': True, 'version': policy['version'], 'checkpoint': record['checkpoint']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--admin-user', required=True)
    parser.add_argument('--mode', choices=('preflight', 'upgrade', 'resume', 'rollback'), default='preflight')
    parser.add_argument('--confirm', default='')
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--test-interrupt-after-save', action='store_true')
    args = parser.parse_args()
    if args.mode == 'rollback' and args.checkpoint is None:
        parser.error('rollback requires --checkpoint')
    if os.geteuid() != 0:
        parser.error('root is required')
    try:
        if STATE.is_symlink() or CHECKPOINTS.is_symlink():
            raise PolicyError('Unsafe state directory')
        for directory in (STATE, CHECKPOINTS):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(directory, 0o700)
        with (STATE / 'lock').open('a') as lock:
            os.chmod(STATE / 'lock', 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print(json.dumps(execute(args.manifest, args.admin_user, args.mode, args.confirm, args.checkpoint, args.test_interrupt_after_save)))
    except (OSError, ValueError, KeyError, StopIteration, tarfile.TarError) as error:
        if isinstance(error, PolicyError) and str(error).startswith('EXPECTED EVALUATION'):
            print(str(error), file=__import__('sys').stderr)
        else:
            print('ERROR: explicit proxy lifecycle failed; inspect retained private checkpoint/transaction', file=__import__('sys').stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
