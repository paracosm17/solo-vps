#!/usr/bin/env python3
"""Create a standalone hello application with the complete Solo VPS CI template."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def create_app(destination: Path, *, root: Path = ROOT) -> Path:
    destination = destination.expanduser().absolute()
    if destination.is_symlink() or destination.exists():
        raise ValueError("choose a new directory; existing application files are never overwritten")
    destination = destination.resolve()
    if destination.is_relative_to(root.resolve()):
        raise ValueError("create the application outside the Solo VPS source checkout")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".solo-vps-app-", dir=destination.parent))
    files = {
        **{f"examples/hello-app/{name}": name for name in (
            "app.py", "test_app.py", "migration_preflight.py", "Dockerfile", ".dockerignore", "requirements-dev.txt", "ruff.toml",
        )},
        "templates/github-actions/app-README.md": "README.md",
        "templates/github-actions/app-gitignore": ".gitignore",
        "templates/github-actions/hello-app-ci.yml": ".github/workflows/app.yml",
        **{f"scripts/{name}.py": f"scripts/{name}.py" for name in (
            "coolify_deploy_api", "validate_coolify_image_handoff", "check_release_revision",
        )},
        **{f"templates/github-actions/tests/{name}.py": f"tests/{name}.py" for name in (
            "test_coolify_deploy_api", "test_coolify_image_handoff",
        )},
        "tests/test_release_revision.py": "tests/test_release_revision.py",
    }
    try:
        for source, target in files.items():
            path = staging / target
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / source, path)
        workflow = staging / ".github/workflows/app.yml"
        workflow.write_text(workflow.read_text(encoding="utf-8").replace("APP_DIR: examples/hello-app", "APP_DIR: ."), encoding="utf-8")
        (staging / "scripts/__init__.py").touch()
        (staging / "tests/__init__.py").touch()
        staging.rename(destination)
    finally:
        if staging.exists():
            # Delete only the temporary directory created by this invocation.
            if staging.resolve().parent != destination.parent.resolve() or not staging.name.startswith(".solo-vps-app-"):
                raise ValueError("unexpected staging path; cleanup refused")
            shutil.rmtree(staging)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        destination = create_app(args.destination)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"ERROR app starter: {exc}\n")
    print(f"Created application: {destination}")
    print("Next: follow the First application guide. Publish the first image before enabling SOLO_VPS_DEPLOY_ENABLED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
