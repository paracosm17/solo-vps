from pathlib import Path
import unittest
from unittest.mock import patch
from scripts.check_updates import report, select_release, source_identity
import subprocess
ROOT = Path(__file__).resolve().parents[1]

class UpdateCheckTests(unittest.TestCase):
    def test_unreadable_git_is_not_reported_as_clean(self):
        with patch('scripts.check_updates.subprocess.run', return_value=subprocess.CompletedProcess(['git'], 1, '', '')):
            source = source_identity(ROOT)
        self.assertIsNone(source['revision'])
        self.assertIsNone(source['dirty'])
        self.assertIn('unknown', source['error'])

    def test_new_upstream_is_not_installable(self):
        with patch('scripts.check_updates.source_identity', return_value={'exact_release': 'v0.1.0'}):
            value = report(ROOT, True, fetch=lambda repo: {'version': 'v4.99.0' if 'coolify' in repo else 'v0.2.0', 'prerelease': False})
        self.assertFalse(value['mutation'])
        self.assertTrue(value['upstream']['coolify']['newer_than_reviewed_target'])
        self.assertFalse(value['upstream']['coolify']['matches_reviewed_target'])
        self.assertTrue(value['upstream']['solo-vps']['newer_than_exact_source_release'])

    def test_offline_does_not_fetch(self):
        def fail(repo): raise AssertionError('offline must not use network')
        value = report(ROOT, fetch=fail)
        self.assertFalse(value['network_request'])
        self.assertEqual(value['upstream'], {})

    def test_matching_candidate_is_not_reported_as_installation_permission(self):
        target = report(ROOT)['coolify']['reviewed_target']
        value = report(ROOT, True, component='coolify', fetch=lambda _: {'version': 'v' + target, 'prerelease': False})
        self.assertTrue(value['upstream']['coolify']['matches_reviewed_target'])
        self.assertNotIn('installable_by_this_source', value['upstream']['coolify'])
        self.assertEqual(value['coolify']['evidence'], 'V2-source-candidate')

    def test_semver_selection_excludes_drafts_and_prereleases(self):
        releases = [{'tag_name': 'v4.9.0'}, {'tag_name': 'v4.10.0'}, {'tag_name': 'v5.0.0', 'prerelease': True}, {'tag_name': 'v6.0.0', 'draft': True}]
        self.assertEqual(select_release(releases)['version'], 'v4.10.0')
        self.assertTrue(select_release([{'tag_name': 'v0.1.0', 'prerelease': True}])['prerelease'])

    def test_invalid_response_fails(self):
        for data in ({'message': 'rate limit'}, [], [{'tag_name': 'latest'}]):
            with self.assertRaises(ValueError): select_release(data)
