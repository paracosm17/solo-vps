from __future__ import annotations
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / 'scripts/validate_observability_runtime.py'
FILES = [
    'Makefile',
    'CHANGELOG.md',
    'ROADMAP.md',
    'ansible/roles/observability/defaults/main.yml',
    'ansible/roles/observability/tasks/install-runtime.yml',
    'ansible/roles/observability/tasks/verify-runtime.yml',
    'ansible/roles/observability/tasks/audit-confidentiality.yml',
    'ansible/roles/observability/templates/config.alloy.j2',
    'ansible/roles/observability/templates/solo-vps-alloy.service.j2',
    'ansible/roles/observability/templates/solo-vps-observability.tmpfiles.j2',
    'ansible/playbooks/observability-runtime.yml',
    'ansible/playbooks/verify-observability-runtime.yml',
    'ansible/playbooks/audit-observability-confidentiality.yml',
    'docs/operations/observability.md',
    'docs/architecture.md',
    'docs/testing.md',
    'docs/state-layout.md',
]

class RuntimeContractTests(unittest.TestCase):
    def tree(self):
        td = tempfile.TemporaryDirectory()
        root = pathlib.Path(td.name)
        for rel in FILES:
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, target)
        return td, root

    def runv(self, root):
        return subprocess.run(['python3', str(VALIDATOR), str(root)], text=True, capture_output=True)

    def mutate(self, rel, old, new):
        td, root = self.tree()
        p = root / rel
        text = p.read_text()
        self.assertIn(old, text)
        p.write_text(text.replace(old, new, 1))
        return td, root

    def assert_rejected(self, rel, old, new):
        td, root = self.mutate(rel, old, new)
        with td:
            result = self.runv(root)
            self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_current_tree(self):
        result = self.runv(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_direct_alloy_docker_socket(self):
        self.assert_rejected('ansible/roles/observability/templates/config.alloy.j2', '{{ solo_vps_alloy_docker_host }}', 'unix:///var/run/docker.sock')

    def test_rejects_tcp_alloy_proxy(self):
        self.assert_rejected('ansible/roles/observability/defaults/main.yml', 'solo_vps_alloy_docker_host: unix:///run/solo-vps-docker-api/docker-api.sock', 'solo_vps_alloy_docker_host: tcp://127.0.0.1:2375')

    def test_rejects_missing_network_read_proxy(self):
        self.assert_rejected('ansible/roles/observability/tasks/install-runtime.yml', '      - --env\n      - NETWORKS=1\n      - --env\n      - POST=0\n', '      - --env\n      - NETWORKS=0\n      - --env\n      - POST=0\n')

    def test_rejects_post_write_proxy(self):
        self.assert_rejected('ansible/roles/observability/tasks/install-runtime.yml', '      - --env\n      - POST=0\n      - --env\n      - AUTH=0\n', '      - --env\n      - POST=1\n      - --env\n      - AUTH=0\n')


    def test_rejects_enabled_sensitive_proxy_section(self):
        self.assert_rejected('ansible/roles/observability/tasks/install-runtime.yml', '      - --env\n      - INFO=0\n', '      - --env\n      - INFO=1\n')

    def test_rejects_any_published_proxy_port(self):
        self.assert_rejected('ansible/roles/observability/tasks/install-runtime.yml', '      - --mount\n', '      - --publish\n      - 127.0.0.1:2375:2375\n      - --mount\n')

    def test_rejects_proxy_network_access(self):
        self.assert_rejected('ansible/roles/observability/tasks/install-runtime.yml', '      - --network\n      - none\n', '      - --network\n      - bridge\n')

    def test_rejects_missing_unix_bind_config(self):
        self.assert_rejected('ansible/roles/observability/tasks/install-runtime.yml', 'BIND_CONFIG={{ solo_vps_docker_api_proxy_bind_config }}', 'BIND_CONFIG=:2375')

    def test_rejects_world_traversable_proxy_directory(self):
        self.assert_rejected('ansible/roles/observability/templates/solo-vps-observability.tmpfiles.j2', '0750 root', '0755 root')

    def test_rejects_missing_runtime_directory_bind_mount(self):
        self.assert_rejected('ansible/roles/observability/tasks/install-runtime.yml', 'type=bind,source={{ solo_vps_docker_api_proxy_runtime_dir }},target={{ solo_vps_docker_api_proxy_container_socket_dir }}', 'type=bind,source=/tmp,target=/proxy')

    def test_rejects_legacy_removal_before_classification(self):
        td, root = self.tree()
        with td:
            p = root / 'ansible/roles/observability/tasks/install-runtime.yml'
            text = p.read_text()
            classify = text.index('- name: Classify exact desired or exact legacy Docker API proxy state before mutation')
            remove = text.index('- name: Remove only the exact known V3 loopback proxy before Unix-socket migration')
            block = text[remove:text.index('- name: Remove a stale managed proxy socket', remove)]
            text = text[:classify] + block + text[classify:remove] + text[text.index('- name: Remove a stale managed proxy socket', remove):]
            p.write_text(text)
            self.assertNotEqual(self.runv(root).returncode, 0)

    def test_rejects_root_alloy(self):
        self.assert_rejected('ansible/roles/observability/templates/solo-vps-alloy.service.j2', 'User={{ solo_vps_alloy_user }}', 'User=root')

    def test_rejects_dynamic_container_name_as_service(self):
        self.assert_rejected('ansible/roles/observability/templates/config.alloy.j2', '__meta_docker_container_label_coolify_serviceName', '__meta_docker_container_name')

    def test_rejects_pprof_enabled_runtime(self):
        self.assert_rejected('ansible/roles/observability/templates/solo-vps-alloy.service.j2', '--server.http.enable-pprof=false ', '')

    def test_rejects_missing_writable_working_directory_contract(self):
        self.assert_rejected('ansible/roles/observability/templates/solo-vps-alloy.service.j2', 'WorkingDirectory={{ solo_vps_alloy_state_dir }}\n', '')

    def test_rejects_config_inside_root_only_credential_tree(self):
        self.assert_rejected('ansible/roles/observability/defaults/main.yml', 'solo_vps_alloy_config_dir: /etc/solo-vps-alloy', 'solo_vps_alloy_config_dir: /etc/solo-vps/observability/alloy')

    def test_rejects_world_readable_alloy_config(self):
        self.assert_rejected('ansible/roles/observability/tasks/install-runtime.yml', 'mode: "0640"', 'mode: "0644"')

    def test_rejects_unquoted_runtime_mode_evidence(self):
        self.assert_rejected(
            'ansible/roles/observability/tasks/verify-runtime.yml',
            '      runtime_env_mode: "0600"\n',
            '      runtime_env_mode: 0600\n',
        )

    def test_rejects_missing_proxy_unrelated_identity_denial(self):
        self.assert_rejected('ansible/roles/observability/tasks/verify-runtime.yml', '      - solo_vps_alloy_runtime_proxy_unrelated_status == -1\n', '')

    def test_rejects_missing_stale_tcp_listener_denial(self):
        self.assert_rejected('ansible/roles/observability/tasks/verify-runtime.yml', '      - "\':2375\' not in (solo_vps_alloy_runtime_listeners.stdout | default(\'\'))"\n', '')

    def test_rejects_missing_direct_socket_denial_from_runtime_verify(self):
        self.assert_rejected('ansible/roles/observability/tasks/verify-runtime.yml', '      - solo_vps_alloy_runtime_direct_socket_read.rc != 0\n', '')

    def test_rejects_missing_bounded_alloy_startup_wait(self):
        self.assert_rejected('ansible/roles/observability/tasks/verify-runtime.yml', '    timeout: 15\n', '    timeout: 0\n')

    def test_rejects_missing_sanitized_startup_diagnostics(self):
        self.assert_rejected('ansible/roles/observability/tasks/verify-runtime.yml', 'startup_unknown_flag_error:', 'startup_flag_state:')

    def test_rejects_unscoped_alloy_journal_history(self):
        self.assert_rejected('ansible/roles/observability/tasks/verify-runtime.yml', '"_SYSTEMD_INVOCATION_ID={{ solo_vps_alloy_runtime_invocation_id.stdout | default(\'\') | trim }}"', '"--unit"')

    def test_rejects_current_invocation_journal_without_fail_closed_assertion(self):
        self.assert_rejected('ansible/roles/observability/tasks/verify-runtime.yml', '      - (solo_vps_alloy_runtime_recent_logs.rc | default(-1)) == 0\n', '')

    def test_rejects_bare_http_status_as_provider_auth_error(self):
        self.assert_rejected(
            'ansible/roles/observability/tasks/verify-runtime.yml',
            "regex_search('(?i)((loki|grafana|remote[_ -]?write|prometheus)[^\\n]*(401|403|unauthorized|forbidden)|(401|403|unauthorized|forbidden)[^\\n]*(loki|grafana|remote[_ -]?write|prometheus))')",
            "regex_search('(?i)(401|403|unauthorized|forbidden)')",
        )

    def test_rejects_confidentiality_probe_that_reads_response_body(self):
        self.assert_rejected('ansible/roles/observability/tasks/audit-confidentiality.yml', '              response.close()\n', '              response.read()\n              response.close()\n')

    def test_rejects_confidentiality_gate_that_allows_unrelated_http_response(self):
        self.assert_rejected('ansible/roles/observability/tasks/audit-confidentiality.yml', 'solo_vps_observability_confidentiality_unrelated_inspect_status == -1', 'solo_vps_observability_confidentiality_unrelated_inspect_status in [-1, 403]')

    def test_rejects_confidentiality_probe_without_directory_traversal_gate(self):
        self.assert_rejected('ansible/roles/observability/tasks/audit-confidentiality.yml', '      - (solo_vps_observability_confidentiality_unrelated_dir_access.rc | default(0)) != 0\n', '')

    def test_rejects_confidentiality_probe_without_direct_socket_denial(self):
        self.assert_rejected('ansible/roles/observability/tasks/audit-confidentiality.yml', '      - solo_vps_observability_confidentiality_alloy_socket_read.rc != 0\n', '')

    def test_rejects_disabled_endpoint_probe_not_using_alloy_identity(self):
        self.assert_rejected('ansible/roles/observability/tasks/audit-confidentiality.yml', '- name: Probe explicitly disabled Docker API sections as Alloy without reading response content', '- name: Probe explicitly disabled Docker API sections without trusted identity')

    def test_rejects_confidentiality_probe_without_disabled_endpoint_regression(self):
        self.assert_rejected('ansible/roles/observability/tasks/audit-confidentiality.yml', '      - solo_vps_observability_confidentiality_images_status == 403\n', '')

    def test_rejects_confidentiality_probe_that_exposes_container_probe_output(self):
        self.assert_rejected('ansible/roles/observability/tasks/audit-confidentiality.yml', '  no_log: true\n  register: solo_vps_observability_confidentiality_container_ids', '  register: solo_vps_observability_confidentiality_container_ids')

    def test_rejects_slurping_runtime_credentials_to_controller(self):
        td, root = self.tree()
        with td:
            p = root / 'ansible/roles/observability/tasks/install-runtime.yml'
            p.write_text(p.read_text() + '\n- name: bad\n  ansible.builtin.slurp:\n    src: /etc/solo-vps/observability/grafana-cloud.json\n')
            self.assertNotEqual(self.runv(root).returncode, 0)

if __name__ == '__main__':
    unittest.main()
