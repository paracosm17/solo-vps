from __future__ import annotations

import base64
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.initialize_coolify_env import SECRET_KEYS, complete_environment, initialize


class CoolifyEnvironmentTests(unittest.TestCase):
    def test_initializes_all_secrets_and_second_run_is_unchanged(self):
        initial = "# retained configuration\nAPP_ID=\nLATEST_IMAGE=4.1.2\n"
        completed = complete_environment(initial)
        fields = dict(line.split("=", 1) for line in completed.splitlines() if "=" in line)
        self.assertTrue(all(fields[key] for key in SECRET_KEYS))
        self.assertEqual(len(base64.b64decode(fields["APP_KEY"].removeprefix("base64:"))), 32)
        self.assertEqual(fields["LATEST_IMAGE"], "4.1.2")
        with mock.patch("scripts.initialize_coolify_env.generated_value", side_effect=AssertionError("must not rotate")):
            self.assertEqual(complete_environment(completed, require_existing=True), completed)

    def test_resumes_partially_populated_environment_without_rotating_values(self):
        initial = "APP_KEY=existing-key\nDB_PASSWORD=existing-password\nREDIS_PASSWORD=\n"
        result = complete_environment(initial)
        self.assertIn("APP_KEY=existing-key\n", result)
        self.assertIn("DB_PASSWORD=existing-password\n", result)
        self.assertNotIn("REDIS_PASSWORD=\n", result)

    def test_lost_committed_secret_and_duplicate_key_are_rejected(self):
        with self.assertRaises(ValueError):
            complete_environment("APP_KEY=\n", require_existing=True)
        with self.assertRaises(ValueError):
            complete_environment("DB_PASSWORD=first\nDB_PASSWORD=second\n")

    def test_failed_atomic_replace_preserves_original_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("APP_ID=\n", encoding="utf-8")
            with mock.patch("scripts.initialize_coolify_env.os.replace", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    initialize(path)
            self.assertEqual(path.read_text(), "APP_ID=\n")
            self.assertEqual(list(Path(directory).iterdir()), [path])
            self.assertTrue(initialize(path))
            before = path.read_bytes()
            self.assertFalse(initialize(path, require_existing=True))
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
