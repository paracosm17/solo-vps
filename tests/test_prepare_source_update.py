from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.prepare_source_update import SourceUpdateError, prepare


class PrepareSourceUpdateTests(unittest.TestCase):
    def test_rejects_non_tag_version_before_git(self) -> None:
        with patch("scripts.prepare_source_update.git") as git:
            with self.assertRaises(SourceUpdateError):
                prepare(Path.cwd(), "main;rm -rf /tmp/other")
            git.assert_not_called()

    def test_rejects_dirty_source_before_clone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "solo-vps"
            current.mkdir()
            with patch("scripts.prepare_source_update.git", side_effect=[str(current), " M Makefile"]) as git:
                with self.assertRaisesRegex(SourceUpdateError, "local changes"):
                    prepare(current, "v0.2.3")
            self.assertEqual(git.call_count, 2)

    def test_exact_tag_clones_to_sibling_and_checks_cleanliness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "solo-vps"
            current.mkdir()
            target = Path(directory) / "solo-vps-v0.2.3"
            with patch("scripts.prepare_source_update.git", side_effect=[str(current), "", "", "v0.2.3", ""]) as git:
                self.assertEqual(prepare(current, "v0.2.3"), target)
            self.assertEqual(git.call_args_list[2].args[:5],
                             ("clone", "--branch", "v0.2.3", "--depth", "1"))

    def test_existing_target_is_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "solo-vps"
            current.mkdir()
            (Path(directory) / "solo-vps-v0.2.3").mkdir()
            with patch("scripts.prepare_source_update.git", side_effect=[str(current), ""]) as git:
                with self.assertRaisesRegex(SourceUpdateError, "already exists"):
                    prepare(current, "v0.2.3")
            self.assertEqual(git.call_count, 2)


if __name__ == "__main__":
    unittest.main()
