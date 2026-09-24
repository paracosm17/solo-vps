from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.validate_github_actions_template import validate

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/github-actions/hello-app-ci.yml"
TEMPLATE_TESTS = ROOT / "templates/github-actions/tests"


class GithubActionsTemplateContractTests(unittest.TestCase):
    def test_deploy_input_diagnostics_execute_without_exposing_values(self) -> None:
        import yaml

        bash = shutil.which("bash")
        if not bash and Path("C:/Program Files/Git/bin/bash.exe").is_file():
            bash = "C:/Program Files/Git/bin/bash.exe"
        if not bash:
            self.skipTest("Bash is required to execute workflow input validation")
        workflow = yaml.load(TEMPLATE.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        deployment = workflow["jobs"]["deploy"]["steps"][-1]["run"]
        # Execute the actual preflight, stopping before private-key files or SSH.
        preflight = deployment[deployment.index("fail_deploy_config() {"):]
        preflight = preflight.split('printf \'%s\\n\' "${SOLO_VPS_DEPLOY_SSH_KEY}"', 1)[0]
        env = dict(os.environ, IMAGE_REF="ghcr.io/example/app@sha256:" + "a" * 64,
                   SOLO_VPS_DEPLOY_HOST="203.0.113.10", COOLIFY_RESOURCE_UUID="example123resource456",
                   SOLO_VPS_DEPLOY_SSH_FINGERPRINT="SHA256:" + "a" * 43,
                   SOLO_VPS_DEPLOY_SSH_KEY="private-key-must-not-appear",
                   COOLIFY_API_TOKEN="api-token-must-not-appear",
                   SOLO_VPS_SSH_KNOWN_HOSTS="203.0.113.10 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI" + "A" * 43)

        def run(overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
            return subprocess.run([bash, "--noprofile", "--norc", "-c", "set -euo pipefail\n" + preflight],
                                  env=env | overrides, capture_output=True, text=True, timeout=10)

        valid = run({})
        self.assertEqual(valid.returncode, 0, valid.stderr)
        for name, value, hint in (
            ("SOLO_VPS_DEPLOY_SSH_FINGERPRINT", "a" * 43, "SHA256:"),
            ("SOLO_VPS_DEPLOY_SSH_FINGERPRINT", "", "SHA256:"),
            ("SOLO_VPS_DEPLOY_SSH_FINGERPRINT", "SHA256:" + "a" * 43 + " comment", "SHA256:"),
            ("SOLO_VPS_SSH_KNOWN_HOSTS", "192.0.2.1 ssh-ed25519 AAAA", "must match"),
            ("SOLO_VPS_DEPLOY_SSH_KEY", "", "secret"),
            ("COOLIFY_API_TOKEN", "", "secret"),
        ):
            with self.subTest(name=name, hint=hint):
                result = run({name: value})
                self.assertEqual(result.returncode, 1)
                self.assertIn("::error::", result.stderr)
                self.assertIn(name, result.stderr)
                self.assertIn(hint, result.stderr)
                for secret in (env["SOLO_VPS_DEPLOY_SSH_KEY"], env["COOLIFY_API_TOKEN"]):
                    self.assertNotIn(secret, result.stdout + result.stderr)

    def _mutated(self, old: str, new: str) -> Path:
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(old, text)
        temp = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False, encoding="utf-8")
        self.addCleanup(Path(temp.name).unlink, missing_ok=True)
        with temp:
            temp.write(text.replace(old, new, 1))
        return Path(temp.name)

    def test_current_template_is_valid(self) -> None:
        validate(TEMPLATE)

    def test_deployment_helper_contract_tests_are_required(self) -> None:
        path = self._mutated(
            "      - name: Run deployment helper contract tests\n        run: python3 -m unittest discover -s tests -p 'test_*.py'\n",
            "",
        )
        with self.assertRaises(ValueError):
            validate(path)

    def test_consumer_test_bundle_is_portable_subset_of_canonical_contract_tests(self) -> None:
        import ast

        for name in ("test_coolify_deploy_api.py", "test_coolify_image_handoff.py"):
            with self.subTest(name=name):
                template_text = (TEMPLATE_TESTS / name).read_text(encoding="utf-8")
                canonical_text = (ROOT / "tests" / name).read_text(encoding="utf-8")
                self.assertNotIn("Makefile", template_text)
                template_tests = {
                    node.name
                    for node in ast.walk(ast.parse(template_text))
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
                }
                canonical_tests = {
                    node.name
                    for node in ast.walk(ast.parse(canonical_text))
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
                }
                self.assertTrue(template_tests)
                self.assertTrue(template_tests <= canonical_tests)

    def test_migration_preflight_job_is_required_and_gates_build_publish(self) -> None:
        path = self._mutated("  migration-preflight:\n", "  migration-preflight-disabled:\n")
        with self.assertRaises(ValueError):
            validate(path)
        path = self._mutated("      - migration-preflight\n", "      - test\n")
        with self.assertRaises(ValueError):
            validate(path)

    def test_migration_preflight_cannot_gain_production_environment(self) -> None:
        path = self._mutated(
            "  migration-preflight:\n    name: Application migration preflight\n",
            "  migration-preflight:\n    name: Application migration preflight\n    environment: production\n",
        )
        with self.assertRaises(ValueError):
            validate(path)

    def test_migration_preflight_hook_command_is_required(self) -> None:
        path = self._mutated(
            '        run: python3 "${APP_DIR}/migration_preflight.py"\n',
            '        run: python3 "${APP_DIR}/unsafe_migrate.py"\n',
        )
        with self.assertRaises(ValueError):
            validate(path)

    def test_verify_job_is_required(self) -> None:
        path = self._mutated("  verify-published:\n", "  verify-published-disabled:\n")
        with self.assertRaises(ValueError):
            validate(path)

    def test_verify_job_cannot_gain_package_write(self) -> None:
        path = self._mutated("      packages: read\n", "      packages: write\n")
        with self.assertRaises(ValueError):
            validate(path)

    def test_verify_job_must_pull_digest_output(self) -> None:
        path = self._mutated(
            '          IMAGE_REF: ${{ needs.publish.outputs.image_ref }}\n',
            '          IMAGE_REF: ghcr.io/example/app:sha-deadbeef\n',
        )
        with self.assertRaises(ValueError):
            validate(path)

    def test_verify_job_must_bind_only_to_runner_loopback(self) -> None:
        path = self._mutated(
            "            --publish 127.0.0.1:18080:8080 \\\n",
            "            --publish 18080:8080 \\\n",
        )
        with self.assertRaises(ValueError):
            validate(path)

    def test_verify_job_must_reuse_pulled_digest_without_repulling(self) -> None:
        path = self._mutated("            --pull never \\\n", "")
        with self.assertRaises(ValueError):
            validate(path)

    def test_deploy_job_is_required_and_waits_for_registry_verification(self) -> None:
        path = self._mutated("  deploy:\n", "  deploy-disabled:\n")
        with self.assertRaises(ValueError):
            validate(path)
        path = self._mutated("      - verify-published\n", "")
        with self.assertRaises(ValueError):
            validate(path)

    def test_deploy_job_must_use_production_environment_and_serialization(self) -> None:
        path = self._mutated("    environment: production\n", "    environment: staging\n")
        with self.assertRaises(ValueError):
            validate(path)
        path = self._mutated("      cancel-in-progress: false\n", "      cancel-in-progress: true\n")
        with self.assertRaises(ValueError):
            validate(path)

    def test_deploy_job_cannot_gain_write_permissions(self) -> None:
        path = self._mutated(
            "  deploy:\n    name: Deploy immutable image to Coolify\n",
            "  deploy:\n    name: Deploy immutable image to Coolify\n",
        )
        text = path.read_text(encoding="utf-8")
        marker = "  deploy:\n"
        before, after = text.split(marker, 1)
        after = after.replace("    permissions:\n      contents: read\n", "    permissions:\n      contents: write\n", 1)
        path.write_text(before + marker + after, encoding="utf-8")
        with self.assertRaises(ValueError):
            validate(path)

    def test_deploy_job_must_consume_publish_digest_not_mutable_tag(self) -> None:
        path = self._mutated(
            "      IMAGE_REF: ${{ needs.publish.outputs.image_ref }}\n",
            "      IMAGE_REF: ghcr.io/example/app:latest\n",
        )
        with self.assertRaises(ValueError):
            validate(path)

    def test_deploy_secrets_are_environment_scoped_to_one_step(self) -> None:
        path = self._mutated(
            "          COOLIFY_API_TOKEN: ${{ secrets.COOLIFY_API_TOKEN }}\n",
            "          COOLIFY_API_TOKEN: hard-coded-token\n",
        )
        with self.assertRaises(ValueError):
            validate(path)
        path = self._mutated(
            "          SOLO_VPS_DEPLOY_SSH_KEY: ${{ secrets.SOLO_VPS_DEPLOY_SSH_KEY }}\n",
            "          SOLO_VPS_DEPLOY_SSH_KEY: ${{ secrets.OPS_SSH_KEY }}\n",
        )
        with self.assertRaises(ValueError):
            validate(path)

    def test_deploy_must_pin_host_key_and_forbid_dynamic_trust(self) -> None:
        path = self._mutated("            -o StrictHostKeyChecking=yes \\\n", "            -o StrictHostKeyChecking=no \\\n")
        with self.assertRaises(ValueError):
            validate(path)
        path = self._mutated(
            "          printf '%s\\n' \"${SOLO_VPS_SSH_KNOWN_HOSTS}\" > \"${known_hosts_path}\"\n",
            "          ssh-keyscan \"${SOLO_VPS_DEPLOY_HOST}\" > \"${known_hosts_path}\"\n",
        )
        with self.assertRaises(ValueError):
            validate(path)

    def test_deploy_must_use_exact_restricted_local_forward(self) -> None:
        path = self._mutated(
            "            -L 127.0.0.1:18000:127.0.0.1:8000 \\\n",
            "            -L 127.0.0.1:18000:127.0.0.1:6001 \\\n",
        )
        with self.assertRaises(ValueError):
            validate(path)
        path = self._mutated("          ssh -F /dev/null -N -T \\\n", "          ssh -F /dev/null -T \\\n")
        with self.assertRaises(ValueError):
            validate(path)

    def test_deploy_must_check_tunnel_before_api_mutation(self) -> None:
        path = self._mutated("http://127.0.0.1:18000/api/health", "http://127.0.0.1:18001/api/health")
        with self.assertRaises(ValueError):
            validate(path)
        path = self._mutated("            --check\n\n          python3", "            --apply\n\n          python3")
        with self.assertRaises(ValueError):
            validate(path)

    def test_deploy_helper_uses_fixed_tunnel_and_accepts_domains_in_both_calls(self) -> None:
        path = self._mutated(
            "--base-url http://127.0.0.1:18000/api/v1",
            "--base-url http://203.0.113.10:8000/api/v1",
        )
        with self.assertRaises(ValueError):
            validate(path)
        path = self._mutated("            --allow-domain \\\n", "")
        with self.assertRaises(ValueError):
            validate(path)

    def test_workflow_domain_mode_reaches_the_actual_application_validator(self) -> None:
        import yaml
        from scripts.coolify_deploy_api import build_plan, validate_application_state
        workflow = yaml.load(TEMPLATE.read_text(), Loader=yaml.BaseLoader)
        deployment = workflow["jobs"]["deploy"]["steps"][-1]["run"]
        for invocation in deployment.split("python3 scripts/coolify_deploy_api.py")[1:]:
            plan = build_plan(base_url="http://127.0.0.1:18000/api/v1", resource_uuid="example123resource456",
                              image_ref="ghcr.io/example/app@sha256:" + "a" * 64, allow_domain="--allow-domain" in invocation)
            validate_application_state({"uuid": plan.resource_uuid, "build_pack": "dockerimage", "ports_exposes": "8080",
                                        "ports_mappings": None, "fqdn": "https://app.example.com"}, plan)

    def test_deploy_requires_explicit_enable_and_freshness_check(self) -> None:
        for old, new in (
            ("github.event_name == 'push' && vars.SOLO_VPS_DEPLOY_ENABLED == 'true'", "github.event_name == 'push'"),
            ("python3 scripts/check_release_revision.py || revision_status=$?", "true"),
        ):
            with self.subTest(old=old), self.assertRaises(ValueError):
                validate(self._mutated(old, new))

    def test_deploy_private_key_fingerprint_check_is_required(self) -> None:
        path = self._mutated(
            '[[ "${actual_fingerprint}" == "${SOLO_VPS_DEPLOY_SSH_FINGERPRINT}" ]]',
            "true",
        )
        with self.assertRaises(ValueError):
            validate(path)


if __name__ == "__main__":
    unittest.main()
