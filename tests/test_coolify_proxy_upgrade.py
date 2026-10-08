import copy
import json
from pathlib import Path
import tempfile
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import yaml
from scripts.coolify_proxy_upgrade import replace_image, inspect_plan, read_checkpoint, private_json, PolicyError, execute, CONFIRM
from scripts.coolify_release import load_release

CONFIG = '''name: coolify-proxy
networks:
  coolify:
    external: true
services:
  traefik:
    image: 'traefik:v3.6'
    container_name: coolify-proxy
    labels:
      coolify.proxy: true
    ports: ['80:80/tcp', '443:443/tcp']
    command: ['--accesslog=true', '--accesslog.filepath=/traefik/access.log']
    volumes: ['/data/coolify/proxy:/traefik', '/var/run/docker.sock:/var/run/docker.sock:ro']
    environment:
      CUSTOM: on
'''


def before():
    return {'Image': 'old-id', 'Config': {'Image': 'traefik:v3.6'},
            'State': {'Running': True, 'Health': {'Status': 'healthy'}},
            'HostConfig': {'PortBindings': {'80/tcp': [{'HostIp': '', 'HostPort': '80'}], '443/tcp': [{'HostIp': '', 'HostPort': '443'}]}},
            'NetworkSettings': {'Networks': {'coolify': {}}, 'Ports': {'80/tcp': [{'HostIp': '', 'HostPort': '80'}], '443/tcp': [{'HostIp': '', 'HostPort': '443'}]}}}


class ProxyUpgradeTests(unittest.TestCase):
    def test_image_only_patch_preserves_analytics_and_yaml_scalars(self):
        result = replace_image(CONFIG, 'traefik:v3.7.14@sha256:' + 'a'*64)
        self.assertEqual(result.replace('"traefik:v3.7.14@sha256:' + 'a'*64 + '"', "'traefik:v3.6'"), CONFIG)
        self.assertIn('CUSTOM: on', result)

    def test_same_image_retains_native_scalar_spelling_without_restart(self):
        for value in (CONFIG,CONFIG.replace("'traefik:v3.6'",'traefik:v3.6')):
            self.assertEqual(replace_image(value,'traefik:v3.6'),value)

    def test_alias_duplicate_image_and_unsafe_ports_fail_closed(self):
        for value in (CONFIG.replace("image: 'traefik:v3.6'", "image: &image 'traefik:v3.6'"),
                      CONFIG.replace("image: 'traefik:v3.6'", "image: 'traefik:v3.6'\n    image: 'traefik:v3.7'"),
                      CONFIG.replace("'443:443/tcp'", "'8080:8080/tcp'"),
                      CONFIG.replace('coolify.proxy: true', 'coolify.proxy: false')):
            with self.subTest(value=value), self.assertRaises(PolicyError):
                replace_image(value, 'traefik:v3.7.14')

    def test_preflight_rejects_network_loss_and_saved_image_drift(self):
        current=before();model=yaml.safe_load(CONFIG)
        self.assertEqual(inspect_plan(CONFIG,current,model), ['coolify'])
        current['NetworkSettings']['Networks']['business-extra']={}
        with self.assertRaises(PolicyError):inspect_plan(CONFIG,current,model)
        current=before();model['services']['traefik']['image']='traefik:v3.7'
        with self.assertRaises(PolicyError):inspect_plan(CONFIG,current,model)

    def test_checkpoint_rejects_tampering_and_wrong_fingerprint(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'proxy-test';directory.mkdir(mode=0o700)
            files = {'native.yml':'original', 'proxy.tar.gz':'archive', 'previous-image.tar':'image'}
            for name, value in files.items(): (directory/name).write_text(value)
            record={'schema':1,'fingerprint':'abc','checkpoint':str(directory),'files':{name:hashlib.sha256(value.encode()).hexdigest() for name,value in files.items()}}
            (directory/'transaction.json').write_text(json.dumps(record))
            original_stat = Path.stat
            def owned_stat(path, *args, **kwargs):
                value = original_stat(path, *args, **kwargs)
                return SimpleNamespace(st_uid=0, st_mode=value.st_mode) if path == directory else value
            with patch('scripts.coolify_proxy_upgrade.CHECKPOINTS',Path(root)), patch.object(Path,'stat',owned_stat):
                self.assertEqual(read_checkpoint(directory,'abc'),record)
                with self.assertRaises(PolicyError): read_checkpoint(directory,'wrong')
                (directory/'native.yml').write_text('tampered')
                with self.assertRaises(PolicyError): read_checkpoint(directory,'abc')

    def test_stale_temporary_file_does_not_block_atomic_state_write(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'transaction.json'
            path.with_suffix('.tmp').write_text('interrupted')
            private_json(path,{'state':'complete'})
            self.assertEqual(json.loads(path.read_text()),{'state':'complete'})
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertEqual(list(Path(root).glob('transaction.json.*.tmp')),[])

    def test_other_pending_checkpoint_prevents_any_rollback_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            proxy=Path(root); (proxy/'docker-compose.yml').write_text(CONFIG)
            (proxy/'pending.json').write_text(json.dumps({'checkpoint':'other'}))
            with patch('scripts.coolify_proxy_upgrade.load_release',return_value=load_release()), patch('scripts.coolify_proxy_upgrade.PROXY',proxy), patch('scripts.coolify_proxy_upgrade.STATE',proxy), patch('scripts.coolify_proxy_upgrade.read_checkpoint',return_value={}), patch('scripts.coolify_proxy_upgrade.proxy_state',return_value=before()), patch('scripts.coolify_proxy_upgrade.native',return_value={'configuration':CONFIG}) as native, patch('scripts.coolify_proxy_upgrade.run') as command:
                with self.assertRaises(PolicyError): execute(Path('unused'),'ops','rollback',CONFIRM,proxy)
                command.assert_not_called()
                self.assertEqual(native.call_count,1)

    def test_wrong_pulled_content_never_saves_or_creates_checkpoint(self):
        release=copy.deepcopy(load_release());release['proxy']['upgrade_from'][0]['image_id_x86_64']='old-id'
        def command(args, stdin=None):
            if 'inspect' in args:return json.dumps([{'Id':'wrong-id'}])
            if '--format' in args:return json.dumps(yaml.safe_load(CONFIG))
            return ''
        with tempfile.TemporaryDirectory() as root:
            proxy=Path(root);(proxy/'docker-compose.yml').write_text(CONFIG)
            with patch('scripts.coolify_proxy_upgrade.load_release',return_value=release), patch('scripts.coolify_proxy_upgrade.PROXY',proxy), patch('scripts.coolify_proxy_upgrade.STATE',proxy), patch('scripts.coolify_proxy_upgrade.proxy_state',return_value=before()), patch('scripts.coolify_proxy_upgrade.native',return_value={'configuration':CONFIG}) as native, patch('scripts.coolify_proxy_upgrade.run',side_effect=command), patch('scripts.coolify_proxy_upgrade.checkpoint') as checkpoint:
                with self.assertRaises(PolicyError):execute(Path('unused'),'ops','upgrade',CONFIRM)
                checkpoint.assert_not_called()
                self.assertEqual(native.call_count,1)

    def test_rollback_pins_mutable_source_before_native_pull(self):
        release=copy.deepcopy(load_release());release['proxy']['upgrade_from'][0]['image_id_x86_64']='old-id'
        from scripts.coolify_proxy_upgrade import digest
        with tempfile.TemporaryDirectory() as root:
            proxy=Path(root);(proxy/'docker-compose.yml').write_text(CONFIG);(proxy/'native.yml').write_text(CONFIG)
            pinned='traefik:v3.6@sha256:'+'b'*64
            record={'state':'prepared','checkpoint':str(proxy),'original_sha256':digest(CONFIG),'target_sha256':'target','old_id':'old-id','old_image_pinned':pinned,'networks':['coolify']}
            with patch('scripts.coolify_proxy_upgrade.load_release',return_value=release), patch('scripts.coolify_proxy_upgrade.PROXY',proxy), patch('scripts.coolify_proxy_upgrade.STATE',proxy), patch('scripts.coolify_proxy_upgrade.read_checkpoint',return_value=record), patch('scripts.coolify_proxy_upgrade.proxy_state',return_value=before()), patch('scripts.coolify_proxy_upgrade.native',return_value={'configuration':CONFIG}) as native, patch('scripts.coolify_proxy_upgrade.run'), patch('scripts.coolify_proxy_upgrade.wait_verified') as verified:
                self.assertTrue(execute(Path('unused'),'ops','rollback',CONFIRM,proxy)['recovered'])
                payload=native.call_args.args[1]
                self.assertEqual(yaml.safe_load(payload['configuration'])['services']['traefik']['image'],pinned)
                self.assertTrue(payload['restart'])
                verified.assert_called_once_with('old-id','3.6.25',['coolify'])

    def test_drift_after_interrupted_save_never_restarts(self):
        release=load_release(); fingerprint='bound'
        with tempfile.TemporaryDirectory() as root:
            proxy=Path(root);(proxy/'docker-compose.yml').write_text(CONFIG)
            record={'state':'prepared','checkpoint':str(proxy),'original_sha256':'other','target_sha256':'other-target','old_id':'old-id'}
            (proxy/'pending.json').write_text(json.dumps(record))
            (proxy/'native.yml').write_text(CONFIG)
            with patch('scripts.coolify_proxy_upgrade.PROXY',proxy), patch('scripts.coolify_proxy_upgrade.STATE',proxy), patch('scripts.coolify_proxy_upgrade.load_release',return_value=release), patch('scripts.coolify_proxy_upgrade.release_fingerprint',return_value=fingerprint), patch('scripts.coolify_proxy_upgrade.read_checkpoint',return_value=record), patch('scripts.coolify_proxy_upgrade.proxy_state',return_value=before()), patch('scripts.coolify_proxy_upgrade.native',return_value={'configuration':CONFIG}) as native, patch('scripts.coolify_proxy_upgrade.run',return_value=json.dumps(yaml.safe_load(CONFIG))):
                with self.assertRaises(PolicyError):execute(Path('unused'),'ops','resume',CONFIRM)
                self.assertEqual(native.call_count,1)


if __name__ == '__main__':unittest.main()
