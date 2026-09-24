from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.release_dry_run import ReleaseCheckError, run_checks, validate_version
from scripts.validate_release_process import ContractError, validate

ROOT = Path(__file__).resolve().parents[1]


class ReleaseProcessContractTests(unittest.TestCase):
    def test_current_source_contract_is_valid(self) -> None:
        messages = validate(ROOT)
        self.assertTrue(messages)

    def test_missing_external_uptime_release_gate_is_rejected(self) -> None:
        temp = Path(tempfile.mkdtemp(prefix="solo-vps-release-doc-test-"))
        self.addCleanup(shutil.rmtree, temp, True)
        shutil.copytree(
            ROOT,
            temp,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", ".venv-*", ".pytest_cache", "site", "tmp"),
        )
        path = temp / "docs/release-process.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("CRIT-015 external-uptime evidence", text)
        path.write_text(text.replace("CRIT-015 external-uptime evidence", "availability note", 1), encoding="utf-8")
        with self.assertRaises(ContractError):
            validate(temp)

    def test_missing_coolify_lifecycle_release_gate_is_rejected(self) -> None:
        temp = Path(tempfile.mkdtemp(prefix="solo-vps-release-doc-test-"))
        self.addCleanup(shutil.rmtree, temp, True)
        shutil.copytree(
            ROOT,
            temp,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", ".venv-*", ".pytest_cache", "site", "tmp"),
        )
        path = temp / "docs/release-process.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("CRIT-011 Coolify lifecycle evidence", text)
        path.write_text(text.replace("CRIT-011 Coolify lifecycle evidence", "platform lifecycle note", 1), encoding="utf-8")
        with self.assertRaises(ContractError):
            validate(temp)

    def test_v1_is_rejected_by_pre_alpha_dry_run(self) -> None:
        with self.assertRaises(ReleaseCheckError):
            validate_version("v1.0.0")

    def test_version_requires_v_prefix_and_three_components(self) -> None:
        for candidate in ("0.1.0", "v0.1", "v0.1.0-rc.1", "v0.0.0", "v0.0.1"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ReleaseCheckError):
                    validate_version(candidate)

    def _fixture_repo(self, version: str = "v0.1.0") -> Path:
        temp = Path(tempfile.mkdtemp(prefix="solo-vps-release-test-"))
        self.addCleanup(shutil.rmtree, temp, True)
        (temp / "docs").mkdir()
        files = {
            "README.md": "# Test\nPRE-ALPHA\n",
            "CHANGELOG.md": "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-08-11\n\n- test\n",
            "LICENSE": "test fixture license\n",
            "PROJECT_PASSPORT.md": "fixture\n",
            "ROADMAP.md": "fixture\n",
            "Makefile": "all:\n\t@true\n",
            "docs/release-process.md": "fixture\n",
        }
        for relative, content in files.items():
            path = temp / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        # The release checker itself must be safe to include in the tracked source
        # and must not trigger its own private-material scanner.
        script_target = temp / "scripts/release_dry_run.py"
        script_target.parent.mkdir(parents=True, exist_ok=True)
        script_target.write_text((ROOT / "scripts/release_dry_run.py").read_text(encoding="utf-8"), encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=temp, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=temp, check=True)
        subprocess.run(["git", "config", "user.name", "Solo VPS Test"], cwd=temp, check=True)
        subprocess.run(["git", "add", "."], cwd=temp, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=temp, check=True)
        return temp

    def test_dry_run_passes_on_clean_local_fixture(self) -> None:
        repo = self._fixture_repo()
        messages = run_checks(repo, "v0.1.0")
        self.assertTrue(any("DRY RUN ONLY" in message for message in messages))
        tags = subprocess.run(["git", "tag", "--list"], cwd=repo, text=True, stdout=subprocess.PIPE, check=True).stdout
        self.assertEqual(tags.strip(), "")

    def test_missing_license_is_rejected(self) -> None:
        repo = self._fixture_repo()
        (repo / "LICENSE").unlink()
        subprocess.run(["git", "add", "-u"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "remove license"], cwd=repo, check=True)
        with self.assertRaises(ReleaseCheckError):
            run_checks(repo, "v0.1.0")

    def test_dirty_worktree_is_rejected(self) -> None:
        repo = self._fixture_repo()
        with (repo / "README.md").open("a", encoding="utf-8") as handle:
            handle.write("dirty\n")
        with self.assertRaises(ReleaseCheckError):
            run_checks(repo, "v0.1.0")

    def test_existing_tag_is_rejected(self) -> None:
        repo = self._fixture_repo()
        subprocess.run(["git", "tag", "v0.1.0"], cwd=repo, check=True)
        with self.assertRaises(ReleaseCheckError):
            run_checks(repo, "v0.1.0")

    def test_deleted_private_key_material_in_history_is_rejected(self) -> None:
        repo = self._fixture_repo()
        path = repo / "temporary-secret.txt"
        header = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
        footer = "-----END " + "OPENSSH PRIVATE KEY-----"
        path.write_text(f"{header}\nZmFrZS1rZXktbWF0ZXJpYWw=\n{footer}\n", encoding="utf-8")
        subprocess.run(["git", "add", path.name], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "add accidental secret"], cwd=repo, check=True)
        path.unlink()
        subprocess.run(["git", "add", "-u"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "remove accidental secret"], cwd=repo, check=True)
        with self.assertRaises(ReleaseCheckError):
            run_checks(repo, "v0.1.0")

    def test_deleted_operator_file_in_history_is_rejected(self) -> None:
        for relative in ("inventory.yml", ".sops.yaml", "secrets/recipients/production.txt", ".env.production"):
            with self.subTest(relative=relative):
                repo = self._fixture_repo()
                path = repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("non-secret fixture\n", encoding="utf-8")
                subprocess.run(["git", "add", "-f", relative], cwd=repo, check=True)
                subprocess.run(["git", "commit", "-qm", "add operator fixture"], cwd=repo, check=True)
                path.unlink()
                subprocess.run(["git", "add", "-u"], cwd=repo, check=True)
                subprocess.run(["git", "commit", "-qm", "remove operator fixture"], cwd=repo, check=True)
                with self.assertRaises(ReleaseCheckError):
                    run_checks(repo, "v0.1.0")

    def test_tracked_local_config_is_rejected(self) -> None:
        repo = self._fixture_repo()
        path = repo / "config/config.yml"
        path.parent.mkdir(parents=True)
        path.write_text("server: local\n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", "config/config.yml"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "add forbidden local config"], cwd=repo, check=True)
        with self.assertRaises(ReleaseCheckError):
            run_checks(repo, "v0.1.0")

    def test_missing_release_changelog_entry_is_rejected(self) -> None:
        repo = self._fixture_repo()
        changelog = repo / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [Unreleased]\n", encoding="utf-8")
        subprocess.run(["git", "add", "CHANGELOG.md"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "remove release entry"], cwd=repo, check=True)
        with self.assertRaises(ReleaseCheckError):
            run_checks(repo, "v0.1.0")

    def test_full_project_snapshot_passes_with_fixture_release_prereqs(self) -> None:
        temp = Path(tempfile.mkdtemp(prefix="solo-vps-full-release-test-"))
        self.addCleanup(shutil.rmtree, temp, True)
        repo = temp / "repo"
        shutil.copytree(
            ROOT,
            repo,
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", ".venv-*", ".pytest_cache", "site", "tmp"),
        )
        (repo / "LICENSE").write_text("TEST FIXTURE LICENSE — NOT FOR DISTRIBUTION\n", encoding="utf-8")
        changelog = repo / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8")
        text = text.replace(
            "## [Unreleased]\n",
            "## [Unreleased]\n\n## [0.1.0] - 2026-08-11\n\n### Test fixture\n\n- release dry-run fixture only.\n",
            1,
        )
        changelog.write_text(text, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Solo VPS Test"], cwd=repo, check=True)
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "full source fixture"], cwd=repo, check=True)

        messages = run_checks(repo, "v0.1.0")
        self.assertTrue(any("tracked release snapshot inspection" in message for message in messages))
        tags = subprocess.run(["git", "tag", "--list"], cwd=repo, text=True, stdout=subprocess.PIPE, check=True).stdout
        self.assertEqual(tags.strip(), "")


if __name__ == "__main__":
    unittest.main()
