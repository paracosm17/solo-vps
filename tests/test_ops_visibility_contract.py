from __future__ import annotations

import pathlib
import shutil
import tempfile
import unittest

import yaml

from scripts.validate_ops_visibility_contract import OpsVisibilityContractError, validate

ROOT = pathlib.Path(__file__).resolve().parents[1]


class OpsVisibilityContractTests(unittest.TestCase):
    FILES = (
        "Makefile",
        "ansible/playbooks/ops-status.yml",
        "ansible/playbooks/ops-logs.yml",
        "ansible/roles/ops_status/tasks/main.yml",
        "ansible/roles/ops_status/defaults/main.yml",
        "ansible/roles/ops_logs/tasks/main.yml",
        "ansible/roles/ops_logs/defaults/main.yml",
        "docs/operations/status-and-logs.md",
        "docs/operations/operator-ui.md",
        "docs/operations/observability.md",
        "docs/operations/observability.ru.md",
        "docs/operations/postgresql-backups.md",
        "docs/operations/postgresql-backups.ru.md",
        "docs/operations/application-config-and-secrets.md",
        "docs/operations/coolify-dashboard-domain.md",
        "PROJECT_PASSPORT.md",
    )

    def copy_contract(self, destination: pathlib.Path) -> pathlib.Path:
        for relative in self.FILES:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        return destination

    def test_current_contract_is_valid(self) -> None:
        validate(ROOT)

    def test_rejects_mutating_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/ops_status/tasks/main.yml"
            tasks = yaml.safe_load(path.read_text(encoding="utf-8"))
            tasks.insert(0, {"name": "Bad mutation", "ansible.builtin.file": {"path": "/tmp/x", "state": "touch"}})
            path.write_text(yaml.safe_dump(tasks, sort_keys=False), encoding="utf-8")
            with self.assertRaises(OpsVisibilityContractError):
                validate(root)

    def test_rejects_command_without_changed_when_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/ops_logs/tasks/main.yml"
            tasks = yaml.safe_load(path.read_text(encoding="utf-8"))
            for task in tasks:
                if "ansible.builtin.command" in task:
                    task.pop("changed_when", None)
                    break
            path.write_text(yaml.safe_dump(tasks, sort_keys=False), encoding="utf-8")
            with self.assertRaises(OpsVisibilityContractError):
                validate(root)

    def test_rejects_unbounded_log_tail_help(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "Makefile"
            text = path.read_text(encoding="utf-8").replace("TAIL must be an integer from 1 to 1000", "TAIL can be anything")
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(OpsVisibilityContractError):
                validate(root)


    def test_makefile_accepts_public_container_and_tail_arguments(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("OPS_LOG_CONTAINER ?= $(CONTAINER)", makefile)
        self.assertIn("OPS_LOG_TAIL ?= $(if $(TAIL),$(TAIL),100)", makefile)

    def test_rejects_cli_as_primary_daily_ux(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "docs/operations/status-and-logs.md"
            text = path.read_text(encoding="utf-8").replace("not the normal daily", "the normal daily")
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(OpsVisibilityContractError):
                validate(root)


    def test_rejects_ops_status_that_promotes_cli_as_daily_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "ansible/roles/ops_status/tasks/main.yml"
            text = path.read_text(encoding="utf-8").replace(
                'daily_ui: "GitHub Actions for CI; Coolify for deployments, runtime logs, secrets and terminals"',
                'daily_ui: "make ops-logs"',
            )
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(OpsVisibilityContractError):
                validate(root)

    def test_rejects_vault_like_runtime_secrets_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "docs/operations/application-config-and-secrets.md"
            text = path.read_text(encoding="utf-8").replace("not equivalent to Vault", "equivalent to Vault")
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(OpsVisibilityContractError):
                validate(root)



    def test_rejects_observability_card_without_text_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "docs/operations/observability.md"
            text = path.read_text(encoding="utf-8").replace(
                '<span>1</span><div><strong>Application · VPS</strong>',
                '<span>1</span><strong>Application · VPS</strong>',
            )
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(OpsVisibilityContractError):
                validate(root)

    def test_rejects_observability_windows_path_without_unblock_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "docs/operations/observability.md"
            text = path.read_text(encoding="utf-8").replace(
                r"Get-ChildItem .\scripts\windows\*.ps1 | Unblock-File",
                "# unblock step removed",
            )
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(OpsVisibilityContractError):
                validate(root)

    def test_rejects_second_vps_as_observability_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "docs/operations/observability.md"
            text = path.read_text(encoding="utf-8").replace(
                "does **not** require a second VPS",
                "requires a second VPS",
            )
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(OpsVisibilityContractError):
                validate(root)

    def test_rejects_one_variable_per_json_field_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "docs/operations/application-config-and-secrets.md"
            text = path.read_text(encoding="utf-8").replace("APP_CONFIG_JSON", "APP_CONFIG_REMOVED")
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(OpsVisibilityContractError):
                validate(root)

    def test_rejects_public_terminal_management_ports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "docs/operations/coolify-dashboard-domain.md"
            text = path.read_text(encoding="utf-8").replace(
                "raw management ports remain private",
                "publish raw management ports",
            )
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(OpsVisibilityContractError):
                validate(root)

    def test_rejects_missing_log_sharing_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_contract(pathlib.Path(tmp))
            path = root / "docs/operations/status-and-logs.md"
            text = path.read_text(encoding="utf-8").replace("review before sharing", "share freely")
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(OpsVisibilityContractError):
                validate(root)


if __name__ == "__main__":
    unittest.main()
