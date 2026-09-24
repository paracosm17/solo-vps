from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.validate_workstation_secrets_contract import ContractError, validate


ROOT = Path(__file__).resolve().parents[1]


class WorkstationSecretsContractTests(unittest.TestCase):
    def test_repository_contract_passes(self) -> None:
        validate(ROOT)

    def test_obsolete_offvps_helper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in [
                "PROJECT_PASSPORT.md",
                "ROADMAP.md",
                "Makefile",
                "docs/secrets-sops-age.md",
                "docs/adr/0002-controller-side-sops-decryption.md",
                ".gitignore",
            ]:
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text((ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
            bad = root / "scripts/offvps_controller_access.py"
            bad.parent.mkdir(parents=True, exist_ok=True)
            bad.write_text("# obsolete\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                validate(root)


    def test_windows_installer_is_required_and_pinned(self) -> None:
        installer = ROOT / "scripts/windows/install-secrets-tools.ps1"
        text = installer.read_text(encoding="utf-8")
        self.assertIn("age-v$AgeVersion-windows-amd64.zip", text)
        self.assertIn("sops-v$SopsVersion.amd64.exe", text)
        self.assertIn("Get-FileHash", text)
        self.assertIn("SHA-256: verified", text)
        self.assertNotIn("winget", text.lower())
        self.assertNotIn("choco", text.lower())

    def test_windows_key_helpers_point_to_project_installer(self) -> None:
        for rel in ("scripts/windows/new-age-key.ps1", "scripts/windows/test-age-key.ps1"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("install-secrets-tools.ps1", text)
            self.assertIn("LOCALAPPDATA", text)


    def test_windows_downloaded_scripts_are_unblocked_without_policy_changes(self) -> None:
        docs = (ROOT / "docs/secrets-sops-age.md").read_text(encoding="utf-8")
        self.assertIn("Get-ChildItem .\\scripts\\windows\\*.ps1 | Unblock-File", docs)
        self.assertIn("RemoteSigned", docs)
        self.assertIn("Get-ExecutionPolicy -List", docs)
        self.assertNotIn("Set-ExecutionPolicy", docs)

    def test_windows_key_generation_handles_native_stderr_and_is_idempotent(self) -> None:
        text = (ROOT / "scripts/windows/new-age-key.ps1").read_text(encoding="utf-8")
        self.assertIn('$ErrorActionPreference = "Continue"', text)
        self.assertIn("2>$null", text)
        self.assertIn('PASS Solo VPS age key already exists', text)
        self.assertIn('existing key replaced: no', text)
        self.assertNotIn('throw "Refusing to overwrite existing age key', text)

    def test_windows_key_generation_restricts_ntfs_acl(self) -> None:
        text = (ROOT / "scripts/windows/new-age-key.ps1").read_text(encoding="utf-8")
        self.assertIn("SetAccessRuleProtection($true, $false)", text)
        self.assertIn('S-1-5-18', text)
        self.assertIn('S-1-5-32-544', text)
        self.assertIn("Set-SoloVpsPrivateAcl -Path $keyDir", text)
        self.assertIn("Set-SoloVpsPrivateAcl -Path $fullKeyPath", text)

    def test_windows_public_policy_initializer_is_idempotent_and_public_only(self) -> None:
        text = (ROOT / "scripts/windows/init-sops-policy.ps1").read_text(encoding="utf-8")
        self.assertIn("StateRoot", text)
        self.assertIn("LOCALAPPDATA", text)
        self.assertIn("sops\\.sops.yaml", text)
        self.assertIn("sops\\production.txt", text)
        self.assertIn("Refusing to overwrite existing public SOPS policy file", text)
        self.assertIn("private age key copied to repository/VPS: no", text)
        self.assertIn("source checkout mutated: no", text)
        self.assertNotIn("AGE-" + "SECRET-KEY-", text)
        self.assertNotIn("Copy-Item -LiteralPath $fullKeyPath", text)
        self.assertNotIn('Join-Path $fullProjectRoot ".sops.yaml"', text)
        self.assertIn("survive source replacement/reclone", text)

    def test_windows_public_policy_migration_uses_legal_backup_path(self) -> None:
        text = (ROOT / "scripts/windows/init-sops-policy.ps1").read_text(encoding="utf-8")
        self.assertIn('".backup."', text)
        self.assertIn("[System.IO.File]::Replace($temporary, $Path, $backup)", text)
        self.assertIn("Remove-Item -LiteralPath $backup -Force", text)
        self.assertNotIn("[System.IO.File]::Replace($temporary, $Path, $null)", text)


    def test_windows_public_policy_supports_safe_clean_reruns_without_deleting_ciphertext(self) -> None:
        text = (ROOT / "scripts/windows/init-sops-policy.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$ResetPublicPolicy", text)
        self.assertIn("[switch]$StartFresh", text)
        self.assertIn('Get-ChildItem -LiteralPath $Root -Recurse -File -Filter "*.enc.yaml"', text)
        self.assertIn("Existing public SOPS state does not match the current age key", text)
        self.assertIn("encrypted bundles found:", text)
        self.assertIn("Archive-And-RemoveLocalSecretState", text)
        self.assertIn('archive\\workstation-secrets', text)
        self.assertIn("previous local secret state archived", text)
        self.assertIn("Private age key copied here: no", text)
        self.assertIn("Refusing -ResetPublicPolicy because encrypted state bundles exist", text)
        self.assertNotIn("Copy-Item -LiteralPath $fullKeyPath", text)

    def test_windows_observability_secret_init_reuses_valid_existing_bundle(self) -> None:
        text = (ROOT / "scripts/windows/init-observability-secrets.ps1").read_text(encoding="utf-8")
        self.assertIn("test-observability-secrets.ps1", text)
        self.assertIn("already exists; reusing it", text)
        self.assertIn("existing ciphertext replaced: no", text)
        self.assertIn("init-sops-policy.ps1 -StartFresh", text)


    def test_vps_boundary_verifier_is_small_and_read_only(self) -> None:
        text = (ROOT / "scripts/verify_vps_secrets_boundary.py").read_text(encoding="utf-8")
        self.assertIn("/root/.config/solo-vps/age-key.txt", text)
        self.assertIn("/root/.config/sops/age/keys.txt", text)
        self.assertIn("filesystem mutation: none", text)
        self.assertIn("cannot infer the managed admin home while running as root", text)
        self.assertNotIn("find /", text)
        self.assertNotIn("unlink(", text)
        self.assertNotIn("rmtree", text)
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("verify-vps-secrets-boundary: validate-secrets-policy", makefile)
        self.assertIn("VPS_SECRETS_ADMIN_HOME", makefile)

    def test_makefile_cannot_reintroduce_second_controller_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in [
                "PROJECT_PASSPORT.md",
                "ROADMAP.md",
                "Makefile",
                "docs/secrets-sops-age.md",
                "docs/adr/0002-controller-side-sops-decryption.md",
                ".gitignore",
            ]:
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                text = (ROOT / rel).read_text(encoding="utf-8")
                if rel == "Makefile":
                    text += "\nplan-offvps-controller-access:\n\t@true\n"
                dest.write_text(text, encoding="utf-8")
            with self.assertRaises(ContractError):
                validate(root)


if __name__ == "__main__":
    unittest.main()
