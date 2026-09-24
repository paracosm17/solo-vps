from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import test_sops_roundtrip  # noqa: E402
from secrets_toolchain import DEFAULT_MANIFEST  # noqa: E402

VALID_RECIPIENT = "age1s3cqcks5genc6ru8chl0hkkd04zmxvczsvdxq99ekffe4gmvjpzsedk23c"


def write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


class SopsRoundtripHelperTests(unittest.TestCase):
    def test_roundtrip_uses_only_disposable_identity_and_placeholder_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bin_dir = root / "bin"
            bin_dir.mkdir()

            age_keygen = bin_dir / "age-keygen"
            write_executable(
                age_keygen,
                f'''\
                #!/usr/bin/env python3
                import os
                from pathlib import Path
                import sys

                if "-o" in sys.argv:
                    if os.environ.get("SOPS_AGE_KEY_FILE"):
                        raise SystemExit(9)
                    target = Path(sys.argv[sys.argv.index("-o") + 1])
                    target.write_text("DISPOSABLE-IDENTITY-FIXTURE\\n", encoding="utf-8")
                    raise SystemExit(0)
                if "-y" in sys.argv:
                    print("{VALID_RECIPIENT}")
                    raise SystemExit(0)
                raise SystemExit(2)
                ''',
            )

            encrypted_fixture = (
                "roundtrip:\n"
                "  purpose: ENC[AES256_GCM,data:test]\n"
                "  value: ENC[AES256_GCM,data:test]\n"
                "sops:\n"
                "  age:\n"
                f"    - recipient: {VALID_RECIPIENT}\n"
                "      enc: |\n"
                "        -----BEGIN AGE ENCRYPTED FILE-----\n"
                "        fixture\n"
                "        -----END AGE ENCRYPTED FILE-----\n"
                "  mac: ENC[AES256_GCM,data:test]\n"
                "  version: 3.13.3\n"
            )
            sops = bin_dir / "sops"
            write_executable(
                sops,
                f'''\
                #!/usr/bin/env python3
                import os
                from pathlib import Path
                import sys

                target = Path(sys.argv[-1])
                if "--encrypt" in sys.argv:
                    target.write_text({encrypted_fixture!r}, encoding="utf-8")
                    raise SystemExit(0)
                if "--decrypt" in sys.argv:
                    identity = os.environ.get("SOPS_AGE_KEY_FILE", "")
                    if not identity or not Path(identity).is_file():
                        raise SystemExit(8)
                    print("roundtrip:")
                    print("  purpose: disposable-local-test")
                    print("  value: SOLO_VPS_DISPOSABLE_ROUNDTRIP_VALUE")
                    raise SystemExit(0)
                raise SystemExit(2)
                ''',
            )

            age = bin_dir / "age"
            write_executable(age, "#!/usr/bin/env python3\nraise SystemExit(0)\n")
            paths = {"sops": sops, "age": age, "age-keygen": age_keygen}

            with patch.dict(os.environ, {"SOPS_AGE_KEY_FILE": "/must/not-be-used"}, clear=False):
                with patch.object(test_sops_roundtrip, "check_installation", return_value=paths):
                    test_sops_roundtrip.run_roundtrip(DEFAULT_MANIFEST, root / "cache")


if __name__ == "__main__":
    unittest.main()
