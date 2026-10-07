import json
import subprocess
import unittest
from unittest.mock import Mock
from scripts.remove_legacy_coolify_realtime import retire


class LegacyRealtimeTests(unittest.TestCase):
    def container(self, **updates):
        data = {'Name': '/coolify-realtime', 'Id': 'inspected-container-id',
                'Config': {'Image': 'docker.io/coollabsio/coolify-realtime:1.0.19', 'Labels': {'coolify.managed': 'true'}}}
        data.update(updates)
        return data

    def test_only_the_inspected_owned_container_is_removed_without_volumes(self):
        run = Mock(side_effect=[subprocess.CompletedProcess([], 0, json.dumps([self.container()]), ''),
                                subprocess.CompletedProcess([], 0, '', '')])
        self.assertTrue(retire(run)['changed'])
        self.assertEqual(run.call_args_list[1].args[0], ['/usr/bin/docker', 'rm', '-f', 'inspected-container-id'])

    def test_missing_is_noop_but_daemon_error_is_not(self):
        run = Mock(return_value=subprocess.CompletedProcess([], 1, '', 'Error: No such object: coolify-realtime'))
        self.assertFalse(retire(run)['changed'])
        run.return_value = subprocess.CompletedProcess([], 1, '', 'Cannot connect to Docker daemon')
        with self.assertRaises(ValueError): retire(run)

    def test_foreign_container_is_never_removed(self):
        for data in (self.container(Name='/another-app'), self.container(Config={'Image': 'redis:7', 'Labels': {'coolify.managed': 'true'}}),
                     self.container(Config={'Image': 'coollabsio/coolify-realtime:1.0.19', 'Labels': {}})):
            run = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps([data]), ''))
            with self.assertRaises(ValueError): retire(run)
            self.assertEqual(run.call_count, 1)
