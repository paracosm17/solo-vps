"""Render current release values from the same offline manifest as the runtime."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.coolify_release import load_release  # noqa: E402


def on_page_markdown(markdown, page, config, files):
    release = load_release(ROOT / "config/coolify-release.yml")
    replacements = {
        "solo_vps_coolify_origin": release["upgrade_from"]["version"],
        "solo_vps_coolify_target": release["version"],
        "solo_vps_coolify_qualification": release["qualification"]["level"],
        "solo_vps_coolify_evidence": release["qualification"]["evidence"],
    }
    for name, value in replacements.items():
        markdown = markdown.replace("{{ " + name + " }}", value)
    return markdown
