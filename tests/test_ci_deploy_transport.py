from __future__ import annotations

import pathlib
import tempfile
import unittest

from scripts.ci_deploy_transport import (
    DEPLOY_USER,
    RUNNER_API_BASE_URL,
    TransportError,
    authorized_key_line,
    build_plan,
    runner_ssh_argv,
    sshd_match_block,
    validate_server_host,
)


KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG7x1dQ0aXg7xkV7jnX8mxpQ1L3xB7QOw1vH2zMq5d7x ci-deploy"


class CiDeployTransportTests(unittest.TestCase):
    def _keyfile(self, value: str = KEY):
        tmp = tempfile.TemporaryDirectory()
        path = pathlib.Path(tmp.name) / "deploy.pub"
        path.write_text(value + "\n", encoding="utf-8")
        return tmp, path

    def test_plan_uses_expected_fixed_boundaries(self):
        tmp, path = self._keyfile()
        self.addCleanup(tmp.cleanup)
        plan = build_plan("203.0.113.10", path).as_dict()
        self.assertEqual(plan["deploy_user"], DEPLOY_USER)
        self.assertEqual(plan["remote_api"], "127.0.0.1:8000")
        self.assertEqual(plan["runner_api_base_url"], RUNNER_API_BASE_URL)
        self.assertEqual(plan["mutation"], "none; plan-only source contract")

    def test_authorized_key_is_restricted_to_exact_coolify_destination(self):
        line = authorized_key_line(KEY)
        self.assertTrue(line.startswith('restrict,port-forwarding,permitopen="127.0.0.1:8000" '))
        self.assertNotIn("permitlisten", line)
        self.assertNotIn("command=", line)

    def test_sshd_match_disables_sessions_and_remote_forwarding(self):
        block = sshd_match_block()
        required = [
            "AllowTcpForwarding local",
            "AllowStreamLocalForwarding no",
            "PermitOpen 127.0.0.1:8000",
            "PermitListen none",
            "MaxSessions 0",
            "PasswordAuthentication no",
            "AuthenticationMethods publickey",
            "KbdInteractiveAuthentication no",
            "AllowAgentForwarding no",
            "PermitTTY no",
            "PermitTunnel no",
            "PermitUserRC no",
            "X11Forwarding no",
        ]
        for item in required:
            self.assertIn(item, block)
        self.assertNotIn("AllowTcpForwarding yes", block)
        self.assertNotIn("GatewayPorts yes", block)

    def test_runner_ssh_command_uses_strict_host_key_and_loopback_bind(self):
        argv = runner_ssh_argv("203.0.113.10")
        joined = " ".join(argv)
        self.assertIn("StrictHostKeyChecking=yes", joined)
        self.assertIn("ExitOnForwardFailure=yes", joined)
        self.assertIn("IdentitiesOnly=yes", joined)
        self.assertIn("GlobalKnownHostsFile=/dev/null", joined)
        self.assertIn("127.0.0.1:18000:127.0.0.1:8000", joined)
        self.assertNotIn("0.0.0.0:18000", joined)
        self.assertNotIn("StrictHostKeyChecking=no", joined)

    def test_runner_ssh_command_executes_no_remote_command(self):
        argv = runner_ssh_argv("203.0.113.10")
        self.assertIn("-N", argv)
        self.assertIn("-T", argv)
        self.assertEqual(argv[-1], f"{DEPLOY_USER}@203.0.113.10")

    def test_valid_dns_and_ipv4_hosts(self):
        self.assertEqual(validate_server_host("deploy.example.com"), "deploy.example.com")
        self.assertEqual(validate_server_host("203.0.113.10"), "203.0.113.10")

    def test_rejects_host_with_user_or_port_injection(self):
        for value in ["ops@203.0.113.10", "203.0.113.10:22", "https://example.com", "[::1]"]:
            with self.subTest(value=value):
                with self.assertRaises(TransportError):
                    validate_server_host(value)

    def test_rejects_uppercase_or_invalid_dns(self):
        for value in ["Deploy.EXAMPLE.com", "bad_host.example", "-bad.example"]:
            with self.subTest(value=value):
                with self.assertRaises(TransportError):
                    validate_server_host(value)

    def test_rejects_security_key_public_identity(self):
        tmp, path = self._keyfile(
            "sk-ssh-ed25519@openssh.com AAAAC3NzaC1lZDI1NTE5AAAAIG7x1dQ0aXg7xkV7jnX8mxpQ1L3xB7QOw1vH2zMq5d7x ci-deploy"
        )
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(TransportError):
            build_plan("203.0.113.10", path)

    def test_rejects_private_key_material(self):
        tmp, path = self._keyfile("-----BEGIN OPENSSH " + "PRIVATE KEY-----")
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(TransportError):
            build_plan("203.0.113.10", path)

    def test_rejects_rsa_key_for_narrow_new_ci_identity(self):
        tmp, path = self._keyfile("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCfake")
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(TransportError):
            build_plan("203.0.113.10", path)

    def test_rejects_multiple_public_keys(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = pathlib.Path(tmp.name) / "deploy.pub"
        path.write_text(KEY + "\n" + KEY + "\n", encoding="utf-8")
        with self.assertRaises(TransportError):
            build_plan("203.0.113.10", path)

    def test_plan_never_contains_private_key_or_token_values(self):
        tmp, path = self._keyfile()
        self.addCleanup(tmp.cleanup)
        plan = build_plan("203.0.113.10", path).as_dict()
        rendered = repr(plan)
        self.assertNotIn("PRIVATE KEY", rendered)
        self.assertNotIn("Bearer ", rendered)
        self.assertIn("COOLIFY_API_TOKEN", rendered)

    def test_makefile_requires_explicit_transport_mutation_confirmation(self):
        makefile = (pathlib.Path(__file__).resolve().parents[1] / "Makefile").read_text(encoding="utf-8")
        self.assertIn("CI_DEPLOY_TRANSPORT_CONFIRM_REQUIRED := I_HAVE_REVIEWED_THE_RESTRICTED_CI_SSH_TRANSPORT", makefile)
        self.assertIn("check-ci-deploy-transport-confirm", makefile)
        self.assertIn("ci-deploy-transport: doctor-admin-local check-ci-deploy-transport-confirm", makefile)

    def test_ansible_role_keeps_transport_out_of_default_bootstrap(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        bootstrap = (root / "ansible/playbooks/bootstrap.yml").read_text(encoding="utf-8")
        self.assertNotIn("ci-deploy-transport", bootstrap)
        self.assertNotIn("ci_deploy_transport", bootstrap)

    def test_ansible_role_uses_dedicated_nologin_user_without_sudo_or_docker_groups(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        defaults = (root / "ansible/roles/ci_deploy_transport/defaults/main.yml").read_text(encoding="utf-8")
        main = (root / "ansible/roles/ci_deploy_transport/tasks/main.yml").read_text(encoding="utf-8")
        self.assertIn("solo_vps_ci_deploy_user: solo-vps-ci", defaults)
        self.assertIn("solo_vps_ci_deploy_shell: /usr/sbin/nologin", defaults)
        self.assertIn('groups: ""', main)
        self.assertNotIn("sudo", main)
        self.assertNotIn("docker", main.lower())

    def test_ansible_sshd_template_has_match_reset_and_sessionless_local_forward_policy(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        template = (root / "ansible/roles/ci_deploy_transport/templates/sshd-ci-deploy.conf.j2").read_text(encoding="utf-8")
        self.assertIn("Match User {{ solo_vps_ci_deploy_user }}", template)
        self.assertIn("AllowTcpForwarding local", template)
        self.assertIn("PermitOpen {{ solo_vps_ci_deploy_remote_host }}:{{ solo_vps_ci_deploy_remote_port }}", template)
        self.assertIn("PermitListen none", template)
        self.assertIn("MaxSessions 0", template)
        self.assertIn("AuthenticationMethods publickey", template)
        self.assertTrue(template.rstrip().endswith("Match all"))

    def test_ansible_sshd_change_validates_before_reload_and_has_rollback(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        main = (root / "ansible/roles/ci_deploy_transport/tasks/main.yml").read_text(encoding="utf-8")
        validate_pos = main.index("Validate complete OpenSSH daemon syntax before reload")
        reload_pos = main.index("Reload OpenSSH only after the full candidate configuration validates")
        self.assertLess(validate_pos, reload_pos)
        self.assertIn("rescue:", main)
        self.assertIn("Restore the previous CI deploy sshd drop-in after validation failure", main)
        self.assertIn("Remove the invalid new CI deploy sshd drop-in when no previous file existed", main)

    def test_verify_role_checks_effective_sshd_policy_not_only_file_text(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        verify = (root / "ansible/roles/ci_deploy_transport/tasks/verify.yml").read_text(encoding="utf-8")
        self.assertIn("/usr/sbin/sshd", verify)
        self.assertIn("-T", verify)
        self.assertIn("allowtcpforwarding local", verify)
        self.assertIn("permitopen 127.0.0.1:8000", verify)
        self.assertIn("permitlisten none", verify)
        self.assertIn("maxsessions 0", verify)


if __name__ == "__main__":
    unittest.main()
