from __future__ import annotations

import pathlib
import shutil
import tempfile
import unittest

from scripts.validate_hosted_ci_contract import ContractError, validate_root


ROOT = pathlib.Path(__file__).resolve().parents[1]


class HostedCiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name) / "repo"
        for relative in (".github/workflows/repository-ci.yml", "Makefile", "docs/testing.md", "docs/release-process.md"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def mutate(self, relative: str, old: str, new: str) -> None:
        path = self.root / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def remove_ci_fast_source_gate(self, *targets: str) -> None:
        path = self.root / "Makefile"
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        for index, line in enumerate(lines):
            if not line.startswith("ci-fast-source:"):
                continue
            for target in targets:
                token = f" {target}"
                self.assertIn(token, line)
                line = line.replace(token, "", 1)
            lines[index] = line
            path.write_text("".join(lines), encoding="utf-8")
            return
        self.fail("ci-fast-source target not found")

    def test_current_contract_is_valid(self) -> None:
        validate_root(self.root)

    def test_rejects_missing_runner_temp_state_boundary(self) -> None:
        self.mutate(
            ".github/workflows/repository-ci.yml",
            '          export SOLO_VPS_DATA_BASE="${RUNNER_TEMP}/solo-vps-ci-data"\n',
            "",
        )
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_pull_request_trigger(self) -> None:
        self.mutate(".github/workflows/repository-ci.yml", "  pull_request:\n", "")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_write_permissions(self) -> None:
        self.mutate(".github/workflows/repository-ci.yml", "  contents: read", "  contents: write")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_unpinned_runner_label(self) -> None:
        self.mutate(".github/workflows/repository-ci.yml", "runs-on: ubuntu-24.04", "runs-on: ubuntu-latest")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_external_action_dependency(self) -> None:
        self.mutate(
            ".github/workflows/repository-ci.yml",
            "      - name: Check out the exact workflow revision without third-party actions\n",
            "      - uses: actions/checkout@v7\n      - name: Check out the exact workflow revision without third-party actions\n",
        )
        with self.assertRaises(ContractError):
            validate_root(self.root)


    def test_rejects_checkout_token_at_job_scope(self) -> None:
        self.mutate(
            ".github/workflows/repository-ci.yml",
            '      PIP_DISABLE_PIP_VERSION_CHECK: "1"\n',
            '      PIP_DISABLE_PIP_VERSION_CHECK: "1"\n      SOLO_VPS_CHECKOUT_TOKEN: ${{ github.token }}\n',
        )
        self.mutate(
            ".github/workflows/repository-ci.yml",
            '        env:\n          SOLO_VPS_CHECKOUT_TOKEN: ${{ github.token }}\n',
            "",
        )
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_secret_dependency(self) -> None:
        self.mutate(
            ".github/workflows/repository-ci.yml",
            '      PIP_DISABLE_PIP_VERSION_CHECK: "1"',
            '      PIP_DISABLE_PIP_VERSION_CHECK: "${{ secrets.CI_VALUE }}"',
        )
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_full_validate_in_fast_job(self) -> None:
        self.mutate(".github/workflows/repository-ci.yml", "make ci-fast", "make validate")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_exact_revision_assertion(self) -> None:
        self.mutate(
            ".github/workflows/repository-ci.yml",
            '          test "$(git rev-parse HEAD)" = "${GITHUB_SHA}"\n',
            "",
        )
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_platform_lifecycle_source_gate(self) -> None:
        self.remove_ci_fast_source_gate("validate-platform-lifecycle", "test-platform-lifecycle")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_documentation_governance_source_gate(self) -> None:
        self.remove_ci_fast_source_gate("validate-documentation-governance", "test-documentation-governance")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_operator_surface_source_gate(self) -> None:
        self.remove_ci_fast_source_gate("validate-operator-surface", "test-operator-surface")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_application_migration_source_gate(self) -> None:
        self.remove_ci_fast_source_gate("validate-application-migration-contract", "test-application-migration-contract")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_disposable_clean_target_source_gate(self) -> None:
        self.remove_ci_fast_source_gate("validate-disposable-clean-target", "test-disposable-clean-target")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_disaster_recovery_source_gate(self) -> None:
        self.remove_ci_fast_source_gate("validate-disaster-recovery", "test-disaster-recovery")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_backup_runtime_source_gate(self) -> None:
        self.remove_ci_fast_source_gate("validate-backup-runtime", "test-backup-runtime")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_external_uptime_source_gate(self) -> None:
        self.remove_ci_fast_source_gate("validate-external-uptime", "test-external-uptime")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_qa_static(self) -> None:
        self.mutate("Makefile", "ci-fast: ci-fast-source qa-tools qa-static", "ci-fast: ci-fast-source qa-tools")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_workflow_outside_yamllint_scope(self) -> None:
        self.mutate("Makefile", " .github/workflows/repository-ci.yml", "")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_release_required_check_guidance(self) -> None:
        self.mutate("docs/release-process.md", "required status check", "optional status check")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_missing_self_repository_evidence_boundary(self) -> None:
        self.mutate("docs/testing.md", "Do not add `fast-source` to a consumer repository", "Do not add `fast-source` to an unrelated repository")
        with self.assertRaises(ContractError):
            validate_root(self.root)

    def test_rejects_release_process_that_accepts_consumer_checks(self) -> None:
        self.mutate("docs/release-process.md", "consumer-application checks never satisfy", "consumer-application checks may satisfy")
        with self.assertRaises(ContractError):
            validate_root(self.root)


if __name__ == "__main__":
    unittest.main()
