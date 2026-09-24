from __future__ import annotations

import pathlib
import shutil
import tempfile
import unittest

from scripts.validate_qa_contract import ContractError, validate_root


ROOT = pathlib.Path(__file__).resolve().parents[1]


class QaContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name) / "repo"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns(".venv", "__pycache__"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_current_contract_is_valid(self):
        validate_root(self.root)

    def test_rejects_floating_python_dependency(self):
        path = self.root / "tools/qa-requirements.txt"
        path.write_text(path.read_text().replace("ansible-core==2.21.3", "ansible-core>=2.21"))
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_ansible_core_version_drift(self):
        path = self.root / "tools/qa-requirements.txt"
        path.write_text(path.read_text().replace("2.21.3", "2.21.2"))
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_collection_range(self):
        path = self.root / "ansible/requirements.yml"
        path.write_text(path.read_text().replace('version: "13.0.1"', 'version: ">=13,<14"'))
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_broken_roles_path(self):
        path = self.root / "ansible/ansible.cfg"
        path.write_text(path.read_text().replace("roles_path = roles", "roles_path = ansible/roles"))
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_global_runtime_ansible_default(self):
        path = self.root / "Makefile"
        text = path.read_text().replace(
            "ANSIBLE_PLAYBOOK ?= $(QA_ANSIBLE_PLAYBOOK)",
            "ANSIBLE_PLAYBOOK ?= ansible-playbook",
        )
        path.write_text(text)
        with self.assertRaises(ContractError):
            validate_root(self.root)


    def test_rejects_broad_var_naming_skip(self):
        path = self.root / ".ansible-lint"
        path.write_text(path.read_text().replace("var-naming[no-role-prefix]", "var-naming"))
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_incompatible_yamllint_policy(self):
        path = self.root / ".yamllint"
        path.write_text(path.read_text().replace("comments-indentation: false", "comments-indentation: true"))
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_unnamed_imported_playbook(self):
        path = self.root / "ansible/playbooks/bootstrap.yml"
        text = path.read_text()
        text = text.replace(
            "- name: Run target preflight before bootstrap\n  ansible.builtin.import_playbook: preflight.yml",
            "- ansible.builtin.import_playbook: preflight.yml",
            1,
        )
        path.write_text(text)
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_non_string_assert_condition(self):
        path = self.root / "ansible/roles/firewall/tasks/verify.yml"
        text = path.read_text()
        text = text.replace(
            '\"solo_vps_firewall_ufw_status.stdout is search(\'(?m)^Status: active$\')\"',
            "solo_vps_firewall_ufw_status.stdout is search('(?m)^Status: active$')",
            1,
        )
        path.write_text(text)
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_set_fact_sibling_dependency(self):
        path = self.root / "ansible/roles/firewall/tasks/sibling-regression.yml"
        path.write_text(
            "---\n"
            "- name: Demonstrate invalid sibling fact dependency\n"
            "  ansible.builtin.set_fact:\n"
            "    solo_vps_example_first: 22\n"
            "    solo_vps_example_second: \"{{ solo_vps_example_first }}\"\n"
        )
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_trailing_blank_line_in_yaml(self):
        path = self.root / "ansible/roles/coolify/tasks/install.yml"
        path.write_text(path.read_text() + "\n")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_network_install_inside_qa_static(self):
        path = self.root / "Makefile"
        text = path.read_text()
        text = text.replace("qa-static: qa-check", "qa-static: qa-check\n\t@pip install surprise-package")
        path.write_text(text)
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_ready_marker_commit(self):
        path = self.root / "Makefile"
        text = path.read_text()
        text = text.replace('\t@touch "$(QA_READY_MARKER)"\n', '')
        path.write_text(text)
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_lint_order_drift(self):
        path = self.root / "Makefile"
        text = path.read_text()
        text = text.replace(
            "\t@$(QA_YAMLLINT) -c .yamllint $(QA_YAML_PATHS)\n"
            "\t@$(QA_PYTHON) -m unittest tests.test_docker_version_templates tests.test_firewall_listener_templates\n"
            "\t@ANSIBLE_COLLECTIONS_PATH=\"$(abspath $(QA_COLLECTIONS_DIR))\" $(MAKE) --no-print-directory ansible-syntax",
            "\t@$(QA_PYTHON) -m unittest tests.test_docker_version_templates tests.test_firewall_listener_templates\n"
            "\t@ANSIBLE_COLLECTIONS_PATH=\"$(abspath $(QA_COLLECTIONS_DIR))\" $(MAKE) --no-print-directory ansible-syntax\n"
            "\t@$(QA_YAMLLINT) -c .yamllint $(QA_YAML_PATHS)",
        )
        path.write_text(text)
        with self.assertRaises(ContractError):
            validate_root(self.root)


if __name__ == "__main__":
    unittest.main()
