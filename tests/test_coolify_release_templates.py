"""Evaluate the real manifest bindings with the pinned Ansible engine, offline."""
from copy import deepcopy
from pathlib import Path
import unittest
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template
from ansible.plugins.loader import init_plugin_loader
from scripts.coolify_release import load_release, variables

ROOT = Path(__file__).resolve().parents[1]

class CoolifyReleaseTemplateTests(unittest.TestCase):
    def setUp(self):
        init_plugin_loader()
        self.loader = DataLoader()
        self.role = ROOT / 'ansible/roles/coolify'
        self.defaults = self.loader.load_from_file(str(self.role / 'defaults/main.yml'), trusted_as_template=True)

    def test_actual_role_lookup_and_release_aliases(self):
        templar = Templar(loader=self.loader, variables={**self.defaults, 'role_path': str(self.role),
            'playbook_dir': str(ROOT / 'ansible/playbooks')})
        for key, expected in variables(load_release()).items():
            self.assertEqual(templar.template(trust_as_template('{{ ' + key + ' }}')), expected, key)

    def test_embedded_origin_still_requires_an_upgrade(self):
        release = deepcopy(load_release())
        release['version'] = '9.2.0'
        release['upgrade_from'].update(version='9.1.0', realtime='embedded')
        tasks = self.loader.load_from_file(str(self.role / 'tasks/upgrade-preflight.yml'))
        task = next(t for t in tasks if t['name'] == 'Derive whether the exact supported Coolify upgrade is required')
        templar = Templar(loader=self.loader, variables={**self.defaults, 'solo_vps_coolify_release': release,
            'solo_vps_coolify_upgrade_from_version': '9.1.0'})
        expression = task['ansible.builtin.set_fact']['solo_vps_coolify_upgrade_required']
        self.assertIs(templar.template(trust_as_template(expression)), True)
