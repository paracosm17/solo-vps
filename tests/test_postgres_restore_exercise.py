from __future__ import annotations

from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts.postgres_restore_exercise import (
    RESTORE_CONFIRMATION,
    RestoreExerciseError,
    exercise_restore,
    inspect_archive,
    validate_pgpass,
    validate_verify_query,
)


class Runner:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        output = self.outputs.pop(0)
        if isinstance(output, tuple):
            code, stdout, stderr = output
        else:
            code, stdout, stderr = 0, output, ""
        return subprocess.CompletedProcess(command, code, stdout, stderr)


class PostgresRestoreExerciseTests(unittest.TestCase):
    def test_verify_query_is_read_only_select(self):
        self.assertEqual(validate_verify_query(" SELECT count(*) FROM messages; "), "SELECT count(*) FROM messages")
        for unsafe in ("DELETE FROM x", "SELECT 1; DROP TABLE x", "WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x"):
            with self.subTest(unsafe=unsafe), self.assertRaises(RestoreExerciseError):
                validate_verify_query(unsafe)

    def test_pgpass_must_be_private_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pgpass"
            path.write_text("host:5432:db:user:secret-value\n", encoding="utf-8")
            os.chmod(path, 0o600)
            self.assertEqual(validate_pgpass(path), ["secret-value"])
            os.chmod(path, 0o644)
            with self.assertRaises(RestoreExerciseError):
                validate_pgpass(path)

    def test_pgpass_supports_escaped_colon_and_backslash_for_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pgpass"
            path.write_text(r"host:5432:db:user:sec\:ret\\value" + "\n", encoding="utf-8")
            os.chmod(path, 0o600)
            values = validate_pgpass(path)
            self.assertIn(r"sec:ret\value", values)
            self.assertIn(r"sec\:ret\\value", values)

    def test_archive_inspection_requires_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "backup.dmp"
            archive.write_bytes(b"fake")
            runner = Runner(["; comment\n1; 1259 1 TABLE public messages postgres\n"])
            with mock.patch("scripts.postgres_restore_exercise.shutil.which", return_value="/usr/bin/pg_restore"):
                result = inspect_archive(archive, runner=runner)
            self.assertEqual(result["archive_objects"], 1)
            self.assertIn("--list", runner.calls[0][0])

    def test_restore_requires_confirmation_and_disposable_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive = base / "backup.dmp"; archive.write_bytes(b"fake")
            pgpass = base / "pgpass"; pgpass.write_text("*:5432:*:postgres:secret\n"); os.chmod(pgpass, 0o600)
            with self.assertRaises(RestoreExerciseError):
                exercise_restore(archive=archive, host="127.0.0.1", port=5432, user="postgres", database="production", pgpass=pgpass, verify_query="SELECT 1", expected="1")
            with mock.patch.dict(os.environ, {"SOLO_VPS_DATABASE_RESTORE_CONFIRM": RESTORE_CONFIRMATION}):
                with self.assertRaises(RestoreExerciseError):
                    exercise_restore(archive=archive, host="127.0.0.1", port=5432, user="postgres", database="production", pgpass=pgpass, verify_query="SELECT 1", expected="1")

    def test_empty_target_check_covers_relations_functions_and_custom_types(self):
        self.assertIn("user_relations", __import__("scripts.postgres_restore_exercise", fromlist=["EMPTY_CHECK"]).EMPTY_CHECK)
        self.assertIn("user_functions", __import__("scripts.postgres_restore_exercise", fromlist=["EMPTY_CHECK"]).EMPTY_CHECK)
        self.assertIn("user_types", __import__("scripts.postgres_restore_exercise", fromlist=["EMPTY_CHECK"]).EMPTY_CHECK)

    def test_restore_refuses_nonempty_target_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive = base / "backup.dmp"; archive.write_bytes(b"fake")
            pgpass = base / "pgpass"; pgpass.write_text("*:5432:*:postgres:secret\n"); os.chmod(pgpass, 0o600)
            runner = Runner(["1; TABLE public messages\n", "2\n"])
            with mock.patch.dict(os.environ, {"SOLO_VPS_DATABASE_RESTORE_CONFIRM": RESTORE_CONFIRMATION}), mock.patch("scripts.postgres_restore_exercise.shutil.which", side_effect=lambda x: f"/usr/bin/{x}"):
                with self.assertRaisesRegex(RestoreExerciseError, "not empty"):
                    exercise_restore(archive=archive, host="127.0.0.1", port=5432, user="postgres", database="solo_vps_restore_test", pgpass=pgpass, verify_query="SELECT count(*) FROM messages", expected="2", runner=runner)
            self.assertEqual(len(runner.calls), 2)

    def test_restore_runs_inspect_empty_restore_then_application_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive = base / "backup.dmp"; archive.write_bytes(b"fake")
            pgpass = base / "pgpass"; pgpass.write_text("*:5432:*:postgres:secret-value\n"); os.chmod(pgpass, 0o600)
            runner = Runner(["1; TABLE public messages\n", "0\n", "", "42\n"])
            with mock.patch.dict(os.environ, {"SOLO_VPS_DATABASE_RESTORE_CONFIRM": RESTORE_CONFIRMATION}), mock.patch("scripts.postgres_restore_exercise.shutil.which", side_effect=lambda x: f"/usr/bin/{x}"):
                evidence = exercise_restore(archive=archive, host="127.0.0.1", port=5432, user="postgres", database="solo_vps_restore_test", pgpass=pgpass, verify_query="SELECT count(*) FROM messages", expected="42", runner=runner)
            self.assertEqual(evidence["application_verification"], "PASS")
            restore_command = runner.calls[2][0]
            for flag in ("--clean", "--if-exists", "--no-owner", "--no-acl", "--exit-on-error"):
                self.assertIn(flag, restore_command)
            self.assertEqual(runner.calls[1][1]["env"]["PGOPTIONS"], "-c default_transaction_read_only=on")
            self.assertNotIn("PGOPTIONS", runner.calls[2][1]["env"])
            self.assertEqual(runner.calls[3][1]["env"]["PGOPTIONS"], "-c default_transaction_read_only=on")
            for _, kwargs in runner.calls[1:]:
                self.assertEqual(kwargs["env"]["PGPASSFILE"], str(pgpass))
                self.assertNotIn("secret-value", str(kwargs["env"]))

    def test_failed_command_redacts_pgpass_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive = base / "backup.dmp"; archive.write_bytes(b"fake")
            pgpass = base / "pgpass"; pgpass.write_text("*:5432:*:postgres:secret-value\n"); os.chmod(pgpass, 0o600)
            runner = Runner(["1; TABLE public messages\n", "0\n", (1, "", "connection secret-value failed")])
            with mock.patch.dict(os.environ, {"SOLO_VPS_DATABASE_RESTORE_CONFIRM": RESTORE_CONFIRMATION}), mock.patch("scripts.postgres_restore_exercise.shutil.which", side_effect=lambda x: f"/usr/bin/{x}"):
                with self.assertRaises(RestoreExerciseError) as caught:
                    exercise_restore(archive=archive, host="127.0.0.1", port=5432, user="postgres", database="solo_vps_restore_test", pgpass=pgpass, verify_query="SELECT 1", expected="1", runner=runner)
            self.assertNotIn("secret-value", str(caught.exception))
            self.assertIn("[REDACTED]", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
