from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validate_application_migration_contract import MigrationContractError, validate

ROOT = Path(__file__).resolve().parents[1]


class ApplicationMigrationContractTests(unittest.TestCase):
    def _copy_root(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="solo-vps-migration-contract-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        for relative in (
            "docs/contracts/application-migration-policy.yml",
            "templates/github-actions/hello-app-ci.yml",
            "examples/hello-app/migration_preflight.py",
            "scripts/coolify_deploy_api.py",
            "docs/operations/deployment-rollback.md",
            "docs/ci-ghcr.md",
            "templates/github-actions/README.md",
        ):
            source = ROOT / relative
            target = temp / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return temp

    def _replace(self, root: Path, relative: str, old: str, new: str) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_current_contract_is_valid(self) -> None:
        validate(ROOT)

    def test_reference_hook_executes_without_mutation(self) -> None:
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, str(ROOT / "examples/hello-app/migration_preflight.py")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS application migration preflight", result.stdout)
        self.assertIn("migration_mode: none", result.stdout)
        self.assertIn("database_mutation: false", result.stdout)
        self.assertIn("database_schema_rollback: false", result.stdout)

    def test_database_rollback_cannot_be_claimed(self) -> None:
        root = self._copy_root()
        self._replace(
            root,
            "docs/contracts/application-migration-policy.yml",
            "  database_schema_rollback: false\n",
            "  database_schema_rollback: true\n",
        )
        with self.assertRaises(MigrationContractError):
            validate(root)

    def test_application_must_own_migrations(self) -> None:
        root = self._copy_root()
        self._replace(root, "docs/contracts/application-migration-policy.yml", "owner: application", "owner: solo-vps")
        with self.assertRaises(MigrationContractError):
            validate(root)

    def test_migration_job_is_required(self) -> None:
        root = self._copy_root()
        self._replace(root, "templates/github-actions/hello-app-ci.yml", "  migration-preflight:\n", "  migration-preflight-disabled:\n")
        with self.assertRaises(MigrationContractError):
            validate(root)

    def test_migration_job_cannot_receive_production_environment(self) -> None:
        root = self._copy_root()
        self._replace(
            root,
            "templates/github-actions/hello-app-ci.yml",
            "    permissions:\n      contents: read\n    steps:\n",
            "    permissions:\n      contents: read\n    environment: production\n    steps:\n",
        )
        with self.assertRaises(MigrationContractError):
            validate(root)

    def test_build_and_publish_must_wait_for_preflight(self) -> None:
        for occurrence in ("build", "publish"):
            with self.subTest(occurrence=occurrence):
                root = self._copy_root()
                text = (root / "templates/github-actions/hello-app-ci.yml").read_text(encoding="utf-8")
                block = f"  {occurrence}:\n"
                before, after = text.split(block, 1)
                after = after.replace("      - migration-preflight\n", "      - test\n", 1)
                (root / "templates/github-actions/hello-app-ci.yml").write_text(before + block + after, encoding="utf-8")
                with self.assertRaises(MigrationContractError):
                    validate(root)

    def test_sample_hook_must_remain_explicitly_non_mutating(self) -> None:
        root = self._copy_root()
        self._replace(root, "examples/hello-app/migration_preflight.py", "database_mutation: false", "database_mutation: true")
        with self.assertRaises(MigrationContractError):
            validate(root)

    def test_deploy_helper_must_expose_image_only_scope(self) -> None:
        root = self._copy_root()
        self._replace(root, "scripts/coolify_deploy_api.py", 'ROLLBACK_SCOPE = "container-image-only"', 'ROLLBACK_SCOPE = "full-stack"')
        with self.assertRaises(MigrationContractError):
            validate(root)

    def test_irreversible_change_requires_recovery_prerequisites(self) -> None:
        root = self._copy_root()
        self._replace(
            root,
            "docs/contracts/application-migration-policy.yml",
            "    - tested restore or explicit forward-fix recovery plan\n",
            "",
        )
        with self.assertRaises(MigrationContractError):
            validate(root)


if __name__ == "__main__":
    unittest.main()
