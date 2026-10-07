from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml
from scripts.coolify_release import load_release, load_defaults, validate_manifest, variables, release_fingerprint
from scripts.platform_lifecycle import load_policy, build_plan
from docs.hooks.coolify_release import on_page_markdown

ROOT = Path(__file__).resolve().parents[1]

class ReleaseManifestTests(unittest.TestCase):
    def test_one_manifest_changes_all_compatible_release_consumers(self):
        data = deepcopy(load_release())
        data['version'] = '9.2.0'
        data['upgrade_from']['version'] = '9.1.0'
        data['upgrade_from']['realtime'] = 'embedded'
        data['qualification']['release_sha256'] = release_fingerprint(data)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for rel in ('config/coolify-release.yml', 'docs/contracts/platform-lifecycle-policy.yml', 'ansible/roles/coolify/defaults/main.yml'):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(yaml.safe_dump(data) if rel.startswith('config/') else (ROOT / rel).read_text(), encoding='utf-8')
            defaults = load_defaults(root/'ansible/roles/coolify/defaults/main.yml')
            self.assertEqual(defaults['solo_vps_coolify_version'], '9.2.0')
            self.assertEqual(defaults['solo_vps_coolify_expected_image'], 'docker.io/coollabsio/coolify:9.2.0')
            self.assertTrue(all('/v9.2.0/' in a['url'] for a in defaults['solo_vps_coolify_release_artifacts']))
            self.assertEqual(build_plan(load_policy(root/'docs/contracts/platform-lifecycle-policy.yml'))['coolify']['upgrade_path'], '9.1.0 -> 9.2.0')
        with patch('docs.hooks.coolify_release.load_release', return_value=data):
            rendered = on_page_markdown('{{ solo_vps_coolify_origin }} -> {{ solo_vps_coolify_target }}', None, None, None)
        self.assertEqual(rendered, '9.1.0 -> 9.2.0')

    def test_malformed_or_incomplete_release_fails_closed(self):
        for update in ({'version': 'latest'}, {'schema_version': 999}, {'registry': 'attacker.example'}, {'artifacts': {}}, {'version': '0.0.1'}, {'upgrade_from': []}):
            with self.subTest(update=update):
                data = deepcopy(load_release())
                data.update(update)
                with self.assertRaises(ValueError): validate_manifest(data)

    def test_manifest_artifact_hashes_and_sentinel_identity_are_mandatory(self):
        data = deepcopy(load_release())
        data['artifacts']['docker-compose.yml'] = 'sha256:bad'
        with self.assertRaises(ValueError): variables(data)

    def test_evidence_cannot_follow_a_changed_release_implicitly(self):
        data = deepcopy(load_release())
        data['version'] = '9.2.0'
        with self.assertRaisesRegex(ValueError, 'qualification must be renewed'):
            validate_manifest(data)
        data = deepcopy(load_release())
        data['sentinel']['image_id_x86_64'] = ''
        with self.assertRaises(ValueError): variables(data)
