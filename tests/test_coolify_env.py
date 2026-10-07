from __future__ import annotations

import base64
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.initialize_coolify_env import SECRET_KEYS, complete_environment, complete_reverb_environment, initialize


class CoolifyEnvironmentTests(unittest.TestCase):
    def test_reverb_migration_preserves_credentials_and_browser_settings(self):
        source = complete_environment("PUSHER_BACKEND_HOST=coolify-realtime\nPUSHER_PORT=443\nPUSHER_HOST=panel.example.com\n")
        with mock.patch("scripts.initialize_coolify_env.generated_value", side_effect=AssertionError("must not rotate")):
            updated = complete_reverb_environment(complete_environment(source, require_existing=True))
        before = dict(line.split("=", 1) for line in source.splitlines() if "=" in line)
        after = dict(line.split("=", 1) for line in updated.splitlines() if "=" in line)
        for key in SECRET_KEYS + ("PUSHER_PORT", "PUSHER_HOST"):
            self.assertEqual(before[key], after[key])
        self.assertEqual(after["PUSHER_BACKEND_HOST"], "127.0.0.1")
        self.assertEqual(after["PUSHER_BACKEND_PORT"], "6001")
        self.assertEqual(complete_reverb_environment(updated), updated)

    def test_reverb_preflight_is_read_only_and_custom_backend_never_mutates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            source = complete_environment("PUSHER_BACKEND_HOST=coolify-realtime\n")
            path.write_text(source, encoding="utf-8")
            self.assertFalse(initialize(path, require_existing=True, reverb=True, check_only=True))
            self.assertEqual(path.read_text(), source)
            self.assertTrue(initialize(path, require_existing=True, reverb=True))
            for custom in ("PUSHER_BACKEND_HOST=custom.example.com\nPUSHER_BACKEND_PORT=443\n", "PUSHER_BACKEND_HOST=127.0.0.1\nPUSHER_BACKEND_PORT=7001\n"):
                source = complete_environment(custom)
                path.write_text(source, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "outside the reviewed"):
                    initialize(path, require_existing=True, reverb=True)
                self.assertEqual(path.read_text(), source)

    def test_duplicate_realtime_backend_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            complete_reverb_environment("PUSHER_BACKEND_PORT=6001\nPUSHER_BACKEND_PORT=7001\n")

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
