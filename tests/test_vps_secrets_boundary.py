from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.verify_vps_secrets_boundary import (
    Candidate,
    find_present_private_age_paths,
    private_age_candidates,
    resolve_admin_home,
)


class VpsSecretsBoundaryTests(unittest.TestCase):
    def test_candidate_set_is_small_and_explicit(self) -> None:
        candidates = private_age_candidates(Path("/home/example-admin"))
        self.assertEqual(
            [candidate.path for candidate in candidates],
            [
                Path("/home/example-admin/.config/solo-vps/age-key.txt"),
                Path("/home/example-admin/.config/sops/age/keys.txt"),
                Path("/root/.config/solo-vps/age-key.txt"),
                Path("/root/.config/sops/age/keys.txt"),
            ],
        )
        self.assertEqual([candidate.requires_sudo for candidate in candidates], [False, False, True, True])

    def test_default_root_run_fails_closed_without_admin_home(self) -> None:
        with patch("scripts.verify_vps_secrets_boundary.os.geteuid", return_value=0):
            with self.assertRaisesRegex(ValueError, "cannot infer the managed admin home"):
                resolve_admin_home(None)

    def test_root_can_use_explicit_non_root_admin_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("scripts.verify_vps_secrets_boundary.os.geteuid", return_value=0):
                self.assertEqual(resolve_admin_home(tmp), Path(tmp).resolve())

    def test_root_home_is_never_accepted_as_admin_home(self) -> None:
        with patch("scripts.verify_vps_secrets_boundary.os.geteuid", return_value=0):
            with self.assertRaisesRegex(ValueError, "distinct from /root"):
                resolve_admin_home("/root")

    def test_present_private_key_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            key = home / ".config/solo-vps/age-key.txt"
            key.parent.mkdir(parents=True)
            key.write_text("test-only\n", encoding="utf-8")

            def fake_exists(candidate: Candidate) -> bool:
                return candidate.path == key

            with patch("scripts.verify_vps_secrets_boundary.candidate_exists", side_effect=fake_exists):
                self.assertEqual(find_present_private_age_paths(home), [key])

    def test_clean_home_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch("scripts.verify_vps_secrets_boundary.candidate_exists", return_value=False):
                self.assertEqual(find_present_private_age_paths(home), [])


if __name__ == "__main__":
    unittest.main()
