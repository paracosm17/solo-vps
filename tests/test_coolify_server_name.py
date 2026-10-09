import unittest
from unittest.mock import patch
from scripts.coolify_server_name import desired_name, execute


class ServerNameTests(unittest.TestCase):
    def setUp(self):
        self.server = dict(id=0, team_id=0, ip='host.docker.internal', user='ops', name='localhost')

    def test_default_name_and_custom_names(self):
        self.assertEqual(desired_name(self.server, 'ops', 'app-host'), 'app-host')
        for name in ('app-host', 'My production host'):
            self.server['name'] = name
            self.assertEqual(desired_name(self.server, 'ops', 'app-host'), name)

    def test_wrong_identity_fails_closed(self):
        for key, value in dict(id=1, team_id=1, ip='remote.example', user='root', name=None).items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                desired_name({**self.server, key:value}, 'ops', 'app-host')

    def test_hostname_matches_config_dns_contract(self):
        self.assertEqual(desired_name(self.server, 'ops', 'app.example'), 'app.example')
        for name in ('', 'a..b', '-host', 'Host', "host';exit();", 'a'*64):
            with self.subTest(name=name), patch('scripts.coolify_server_name.subprocess.run') as run, self.assertRaises(ValueError):
                execute('/usr/bin/docker', 'ops', name)
            run.assert_not_called()

    def test_native_failure_and_missing_marker_are_rejected(self):
        for rc, stdout in ((2,''), (0,'Exception rendered with exit zero')):
            with self.subTest(rc=rc), patch('scripts.coolify_server_name.subprocess.run') as run:
                run.return_value.returncode=rc
                run.return_value.stdout=stdout
                with self.assertRaises(ValueError): execute('/usr/bin/docker','ops','app-host')
