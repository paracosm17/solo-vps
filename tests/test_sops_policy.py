from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import yaml

from scripts.sops_policy import LEGACY_SOPS_PATH_REGEX, SOPS_PATH_REGEX, render_sops_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INIT_SCRIPT = PROJECT_ROOT / "scripts" / "init_sops_policy.py"
# Public example recipients from the upstream SOPS documentation; no private identities are used.
VALID_RECIPIENT = "age1s3cqcks5genc6ru8chl0hkkd04zmxvczsvdxq99ekffe4gmvjpzsedk23c"
SECOND_RECIPIENT = "age1qe5lxzzeppw5k79vxn3872272sgy224g2nzqlzy3uljs84say3yqgvd0sw"


class SopsPolicyInitTests(unittest.TestCase):
    def run_init(self, state: Path, recipient: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(INIT_SCRIPT),
                "--policy",
                str(state / "sops/.sops.yaml"),
                "--recipient-file",
                str(state / "sops/production.txt"),
                "--recipient",
                recipient,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env={**dict(__import__("os").environ), "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def test_initializes_public_policy_without_private_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            result = self.run_init(state, VALID_RECIPIENT)
            self.assertEqual(result.returncode, 0, result.stderr)

            policy = yaml.safe_load((state / "sops/.sops.yaml").read_text(encoding="utf-8"))
            self.assertEqual(policy["creation_rules"][0]["age"], [VALID_RECIPIENT])
            self.assertEqual((state / "sops/production.txt").read_text(encoding="utf-8"), f"{VALID_RECIPIENT}\n")
            self.assertFalse(any("keys.txt" in str(path) for path in state.rglob("*")))
            self.assertNotIn(
                "AGE-" + "SECRET-KEY-",
                "\n".join(p.read_text(encoding="utf-8") for p in state.rglob("*") if p.is_file()),
            )
            self.assertIn("source checkout mutated: no", result.stdout)


    def test_creation_rule_matches_posix_and_windows_secret_paths(self) -> None:
        self.assertIsNotNone(re.search(SOPS_PATH_REGEX, "/home/dev/state/secrets/observability.enc.yaml"))
        self.assertIsNotNone(re.search(SOPS_PATH_REGEX, r"C:\Users\dev\state\secrets\observability.enc.yaml"))
        self.assertIsNone(re.search(SOPS_PATH_REGEX, r"C:\Users\dev\state\config\observability.enc.yaml"))

    def test_migrates_exact_legacy_unix_only_policy_without_rotating_recipient(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            policy_path = state / "sops/.sops.yaml"
            recipient_path = state / "sops/production.txt"
            policy_path.parent.mkdir(parents=True)
            policy_path.write_text(
                render_sops_config(VALID_RECIPIENT, path_regex=LEGACY_SOPS_PATH_REGEX),
                encoding="utf-8",
            )
            recipient_path.write_text(f"{VALID_RECIPIENT}\n", encoding="utf-8")

            result = self.run_init(state, VALID_RECIPIENT)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("migrated", result.stdout)
            self.assertEqual(policy_path.read_text(encoding="utf-8"), render_sops_config(VALID_RECIPIENT))
            self.assertEqual(recipient_path.read_text(encoding="utf-8"), f"{VALID_RECIPIENT}\n")

    def test_second_identical_run_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            first = self.run_init(state, VALID_RECIPIENT)
            second = self.run_init(state, VALID_RECIPIENT)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("unchanged", second.stdout)

    def test_refuses_implicit_recipient_rotation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            first = self.run_init(state, VALID_RECIPIENT)
            second = self.run_init(state, SECOND_RECIPIENT)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 2)
            self.assertIn("recipient-rotation workflow", second.stderr)
            self.assertEqual((state / "sops/production.txt").read_text(encoding="utf-8"), f"{VALID_RECIPIENT}\n")

    def test_rejects_invalid_recipient_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            invalid = VALID_RECIPIENT[:-1] + ("q" if VALID_RECIPIENT[-1] != "q" else "p")
            result = self.run_init(state, invalid)
            self.assertEqual(result.returncode, 2)
            self.assertIn("checksum", result.stderr)
            self.assertFalse((state / "sops/.sops.yaml").exists())


if __name__ == "__main__":
    unittest.main()
