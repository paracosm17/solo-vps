from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_observability_log_drain.py"
FILES = [
    "Makefile",
    "scripts/windows/copy-observability-log-drain.ps1",
    "ansible/playbooks/verify-observability-log-drain.yml",
    "ansible/playbooks/verify-observability-log-drain-disabled.yml",
    "ansible/playbooks/diagnose-observability-log-drain.yml",
    "ansible/playbooks/test-observability-loki.yml",
    "ansible/roles/observability/tasks/test-loki-delivery.yml",
    "ansible/roles/observability/tasks/verify-log-drain.yml",
    "ansible/roles/observability/tasks/verify-log-drain-disabled.yml",
    "ansible/roles/observability/tasks/diagnose-log-drain.yml",
    "docs/operations/grafana-cloud-log-drain.md",
    "docs/operations/observability.md",
    "ROADMAP.md",
]


class ObservabilityLogDrainContractTests(unittest.TestCase):
    def _tree(self) -> pathlib.Path:
        temp = pathlib.Path(tempfile.mkdtemp(prefix="solo-vps-observability-drain-"))
        self.addCleanup(shutil.rmtree, temp, True)
        for relative in FILES:
            source = ROOT / relative
            dest = temp / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
        return temp

    def _run(self, root: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(VALIDATOR), str(root)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_current_tree_passes(self) -> None:
        result = self._run(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS historical log-drain contract", result.stdout)

    def test_rejects_docker_socket_path(self) -> None:
        root = self._tree()
        path = root / "scripts/windows/copy-observability-log-drain.ps1"
        path.write_text(path.read_text() + "\n# /var/run/docker.sock\n")
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_loopback_verification(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/verify-log-drain.yml"
        path.write_text(path.read_text().replace("127.0.0.1:24224", "0.0.0.0:24224"))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)


    def test_rejects_dynamic_container_as_loki_label(self) -> None:
        root = self._tree()
        path = root / "scripts/windows/copy-observability-log-drain.ps1"
        path.write_text(path.read_text().replace("Label_Keys  `$service_name,`$source", "Label_Keys  `$service_name,`$container,`$source"))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_clipboard_secret_boundary(self) -> None:
        root = self._tree()
        path = root / "scripts/windows/copy-observability-log-drain.ps1"
        path.write_text(path.read_text().replace("token printed: no", "token printed: yes"))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_roles_list_tasks_from_bug(self) -> None:
        root = self._tree()
        path = root / "ansible/playbooks/verify-observability-log-drain.yml"
        path.write_text("""---
- name: broken
  hosts: all
  gather_facts: false
  become: true
  roles:
    - role: observability
      tasks_from: verify-log-drain
""")
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_non_drilldown_service_label(self) -> None:
        root = self._tree()
        path = root / "scripts/windows/copy-observability-log-drain.ps1"
        text = path.read_text()
        text = text.replace("Rename            COOLIFY_APP_NAME service_name", "Rename            COOLIFY_APP_NAME service")
        text = text.replace("Label_Keys  `$service_name,`$source", "Label_Keys  `$service,`$source")
        path.write_text(text)
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_loki_smoke_privacy_boundary(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/test-loki-delivery.yml"
        path.write_text(path.read_text().replace("no_log: true", "no_log: false", 1))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_generated_compose_publication_check(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/verify-log-drain.yml"
        path.write_text(path.read_text().replace("/data/coolify/log-drains/docker-compose.yml", "/tmp/missing-compose.yml"))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_runtime_portbindings_check(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/verify-log-drain.yml"
        path.write_text(path.read_text().replace("HostConfig.PortBindings", "HostConfig.Binds"))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_tcp_reachability_probe(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/verify-log-drain.yml"
        path.write_text(path.read_text().replace("connect_ex", "socket_probe"))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_manual_generated_coolify_patch_guidance(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/verify-log-drain.yml"
        path.write_text(path.read_text().replace("Do not hand-edit /data/coolify/log-drains", "Edit /data/coolify/log-drains manually"))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_disabled_recovery_probe(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/verify-log-drain-disabled.yml"
        path.write_text(path.read_text().replace("connect_ex", "socket_probe"))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_manual_disabled_recovery_mutation(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/verify-log-drain-disabled.yml"
        path.write_text(path.read_text().replace("Do not remove containers or edit /data/coolify/log-drains manually", "Run docker rm manually"))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_diagnostic_network_name_disclosure(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/diagnose-log-drain.yml"
        path.write_text(path.read_text().replace("docker_network_names_printed: false", "docker_network_names: '{{ solo_vps_log_drain_diag_network_names }}'"))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)


    def test_rejects_ansible_lint_unspaced_docker_format_escape(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/diagnose-log-drain.yml"
        path.write_text(
            path.read_text().replace(
                "'{{ \"{{\" }}.Server.Version{{ \"}}\" }}'",
                "'{{\"{{\"}}.Server.Version{{\"}}\"}}'",
            )
        )
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_mutating_diagnostic_network_connect(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/diagnose-log-drain.yml"
        path.write_text(path.read_text() + "\n# docker network connect appnet coolify-log-drain\n")
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_extra_network_diagnosis(self) -> None:
        root = self._tree()
        path = root / "ansible/roles/observability/tasks/diagnose-log-drain.yml"
        path.write_text(path.read_text().replace("collector_extra_network_count", "collector_other_count"))
        result = self._run(root)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
