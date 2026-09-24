#!/usr/bin/env python3
"""Validate the published English/Russian documentation pairing and i18n shell."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


class ContractError(ValueError):
    pass


def parse_excluded(mkdocs: str) -> set[str]:
    match = re.search(r"^exclude_docs:\s*\|\s*\n(?P<body>(?:  .*(?:\n|$))*)", mkdocs, re.MULTILINE)
    if not match:
        return set()
    excluded: set[str] = set()
    for line in match.group("body").splitlines():
        value = line.strip()
        if value:
            excluded.add(value)
    return excluded


def validate(root: Path) -> None:
    root = root.resolve()
    mkdocs_path = root / "mkdocs.yml"
    requirements_path = root / "requirements-docs.txt"
    docs = root / "docs"

    mkdocs = mkdocs_path.read_text(encoding="utf-8")
    requirements = requirements_path.read_text(encoding="utf-8")

    required_config = (
        "docs_structure: suffix",
        "reconfigure_material: true",
        "locale: en",
        "default: true",
        "locale: ru",
        "name: Русский",
        "custom_dir: overrides",
    )
    for needle in required_config:
        if needle not in mkdocs:
            raise ContractError(f"mkdocs.yml missing i18n requirement: {needle!r}")

    # Public docs UX contract: users see task navigation in the left sidebar,
    # but unrelated subtrees remain folded until they are needed.
    if re.search(r"^\s*-\s+navigation\.tabs\s*$", mkdocs, re.MULTILINE):
        raise ContractError("public docs must not use navigation.tabs; keep task navigation in the left sidebar")
    if not re.search(r"^\s*-\s+navigation\.sections\s*$", mkdocs, re.MULTILINE):
        raise ContractError("public docs must use navigation.sections for persistent left-sidebar grouping")
    if re.search(r"^\s*-\s+navigation\.expand\s*$", mkdocs, re.MULTILINE):
        raise ContractError("public docs navigation must be collapsed by default; do not enable navigation.expand")
    if not re.search(r"^\s*font:\s+false\s*$", mkdocs, re.MULTILINE):
        raise ContractError("public docs must use system fonts instead of remote Google Fonts")

    # Pygments is the supported code highlighter. Keep the recommended Material
    # hooks so bash, shell, PowerShell, YAML, Python, etc. receive token classes.
    for needle in ("line_spans: __span", "pygments_lang_class: true"):
        if needle not in mkdocs:
            raise ContractError(f"syntax-highlighting configuration missing: {needle}")

    css_path = docs / "stylesheets" / "extra.css"
    css = css_path.read_text(encoding="utf-8")
    if "linear-gradient(" in css or "radial-gradient(" in css:
        raise ContractError("docs UI must use neutral surfaces without decorative gradients")
    if re.search(r"html\s*\{[^}]*font-size:\s*100%", css, re.DOTALL):
        raise ContractError("docs UI must not shrink Material root typography to 16px")
    if not re.search(r"html\s*\{[^}]*font-size:\s*125%", css, re.DOTALL):
        raise ContractError("docs UI must preserve Material 20px root scale for readable navigation and TOC")
    if ".md-nav__item--nested:not(.md-nav__item--section) > nav.md-nav" not in css:
        raise ContractError("docs UI must retain nested navigation hierarchy")
    if "--solo-tree" in css or re.search(r"border-left:\s*1px\s+solid\s+var\(--solo-tree\)", css):
        raise ContractError("docs navigation must not use decorative gray tree rails")

    if ".solo-shell-command" not in css or ".solo-shell-option" not in css:
        raise ContractError("shell code blocks must visibly distinguish commands and options")
    copy_contract = (
        '.solo-copy-button',
        'background: #21262d',
        'color: #f0f6fc',
        'border-color: #58a6ff',
        'background: #30363d',
    )
    for needle in copy_contract:
        if needle not in css:
            raise ContractError(f"custom dark-theme code copy control missing high-contrast contract: {needle}")
    if 'content.code.copy' in mkdocs:
        raise ContractError("Material copy control must stay disabled; Solo VPS owns the deterministic copy button")
    for token in (
        '--md-default-bg-color: #0d1117',
        '--solo-surface: #161b22',
        '--solo-border: #30363d',
        '--md-typeset-a-color: #356a8a',
        '--md-typeset-a-color: #78a9c4',
        '--solo-active: #e5eef3',
        '--solo-active: #1b2931',
    ):
        if token not in css:
            raise ContractError(f"calm Solo VPS docs palette missing required token: {token}")
    if "padding: 0.2rem 0.72rem 2rem" not in css:
        raise ContractError("primary navigation must keep compact vertical spacing")

    # Material's navigation below the tablet breakpoint is intentionally a
    # layered mobile drawer. Desktop-only rules that flatten nested .md-nav
    # panes must never leak into mobile, or several levels render on top of
    # each other. Keep the complete custom primary-navigation block scoped to
    # Material's desktop breakpoint.
    primary_start = css.find("/* Primary navigation ---------------------------------------------------- */")
    content_start = css.find("/* Content --------------------------------------------------------------- */")
    if primary_start < 0 or content_start <= primary_start:
        raise ContractError("docs CSS is missing the primary-navigation contract block")
    primary_css = css[primary_start:content_start]
    desktop_gate = "@media screen and (min-width: 76.25em) {"
    if desktop_gate not in primary_css:
        raise ContractError("custom primary navigation must be desktop-only so Material mobile panes do not overlap")
    before_gate = primary_css.split(desktop_gate, 1)[0]
    if ".md-sidebar--primary" in before_gate or ".md-nav--primary" in before_gate:
        raise ContractError("primary navigation selectors must not run before the desktop media gate")
    if "Keep mobile navigation on" not in primary_css or "Material's native layout" not in primary_css:
        raise ContractError("docs CSS must document the native Material mobile-navigation boundary")

    extra_js = (docs / "javascripts" / "extra.js").read_text(encoding="utf-8")
    for needle in ("solo-shell-command", "apt-get", "make", "shellSelector", "setupCopyButtons", "solo-copy-button"):
        if needle not in extra_js:
            raise ContractError(f"shell syntax enhancer missing required behavior: {needle}")

    for needle in ("setupTocSync", "solo-toc-active", "clickLockUntil", "activationLine"):
        if needle not in extra_js:
            raise ContractError(f"TOC active-state synchronization missing required behavior: {needle}")
    if "navigation.tracking" in mkdocs:
        raise ContractError("custom TOC synchronization owns anchor state; navigation.tracking must stay disabled")
    if "solo-toc-sync" not in css:
        raise ContractError("TOC CSS must suppress stale Material active state after custom synchronization starts")
    if "first-child" not in css or "font-weight: 650" not in css:
        raise ContractError("Overview and Quick Start must remain visually prominent in the first navigation section")

    syntax_vars = (
        "--md-code-hl-number-color",
        "--md-code-hl-special-color",
        "--md-code-hl-function-color",
        "--md-code-hl-constant-color",
        "--md-code-hl-keyword-color",
        "--md-code-hl-string-color",
        "--md-code-hl-name-color",
        "--md-code-hl-operator-color",
        "--md-code-hl-punctuation-color",
        "--md-code-hl-comment-color",
        "--md-code-hl-generic-color",
        "--md-code-hl-variable-color",
    )
    for var in syntax_vars:
        if css.count(var) < 2:
            raise ContractError(f"both light and dark schemes must define syntax token variable {var}")

    for homepage in (docs / "index.md", docs / "index.ru.md"):
        text = homepage.read_text(encoding="utf-8")
        if "solo-hero" in text:
            raise ContractError(f"documentation homepage must not use a marketing hero: {homepage.name}")
        if re.search(r'href=["\'][^"\']+\.md(?:#[^"\']*)?["\']', text):
            raise ContractError(f"raw HTML links must use built pretty URLs, not .md source URLs: {homepage.name}")

    if "mkdocs==1.6.1" not in requirements:
        raise ContractError("requirements-docs.txt must pin mkdocs==1.6.1 while the site uses MkDocs 1.x plugins/overrides")
    if "mkdocs-material==9.7.7" not in requirements:
        raise ContractError("requirements-docs.txt must pin mkdocs-material==9.7.7 for the reviewed theme override contract")
    if "mkdocs-static-i18n==1.3.1" not in requirements:
        raise ContractError("requirements-docs.txt must pin mkdocs-static-i18n==1.3.1")

    if re.search(r"^\s*admonition_translations:\s*\n\s*-\s+\w+:", mkdocs, re.MULTILINE):
        raise ContractError("admonition_translations must be a mapping, not a YAML list")

    alternate = root / "overrides" / "partials" / "alternate.html"
    if not alternate.is_file() or "solo-language__code" not in alternate.read_text(encoding="utf-8"):
        raise ContractError("visible EN/RU Material language selector override is missing")

    main_override = root / "overrides" / "main.html"
    if not main_override.is_file():
        raise ContractError("Material site_meta override is missing; per-page alternate sitemap requests would return 404")
    main_text = main_override.read_text(encoding="utf-8")
    if "{% block site_meta %}" not in main_text or 'config.extra.alternate' in main_text:
        raise ContractError("site_meta override must omit head alternate links while static-i18n owns the localized sitemap")

    excluded = parse_excluded(mkdocs)
    english: list[Path] = []
    russian: list[Path] = []
    for path in sorted(docs.rglob("*.md")):
        rel = path.relative_to(docs).as_posix()
        if rel in excluded:
            continue
        if path.name.endswith(".ru.md"):
            russian.append(path)
        else:
            english.append(path)

    missing_ru: list[str] = []
    for path in english:
        ru = path.with_name(path.stem + ".ru.md")
        if not ru.is_file():
            missing_ru.append(path.relative_to(docs).as_posix())

    missing_en: list[str] = []
    for path in russian:
        en = path.with_name(path.name.removesuffix(".ru.md") + ".md")
        if not en.is_file():
            missing_en.append(path.relative_to(docs).as_posix())

    if missing_ru:
        raise ContractError("published pages missing Russian pair: " + ", ".join(missing_ru))
    if missing_en:
        raise ContractError("Russian pages missing English source pair: " + ", ".join(missing_en))

    localized_link = re.compile(r"(?:\]\(|href=[\"'])[^)\"']+\.ru\.md(?:[#?)\"']|$)")
    raw_md_href = re.compile(r'href=["\'][^"\']+\.md(?:#[^"\']*)?["\']')
    bad_links: list[str] = []
    bad_raw_html: list[str] = []
    for path in english + russian:
        text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
        # Ignore inline-code examples such as `href="page.md"`; only rendered
        # raw HTML attributes can bypass MkDocs' Markdown link rewriting.
        text = re.sub(r"`[^`\n]*`", "", text)
        rel = path.relative_to(docs).as_posix()
        if localized_link.search(text):
            bad_links.append(rel)
        if raw_md_href.search(text):
            bad_raw_html.append(rel)
    if bad_links:
        raise ContractError(
            "published Markdown must use language-neutral .md links, found .ru.md in: "
            + ", ".join(bad_links)
        )
    if bad_raw_html:
        raise ContractError(
            "raw HTML href values are not rewritten by MkDocs; use pretty built URLs instead of .md in: "
            + ", ".join(bad_raw_html)
        )

    nav_paths = re.findall(r":\s+([^\s]+\.md)\s*$", mkdocs, flags=re.MULTILINE)
    for rel in nav_paths:
        source = docs / rel
        if not source.is_file():
            raise ContractError(f"nav page missing: {rel}")
        ru = source.with_name(source.stem + ".ru.md")
        if not ru.is_file():
            raise ContractError(f"nav page missing Russian pair: {rel}")

    print(
        "PASS docs i18n: English is default, contextual EN/RU switching is configured without per-page sitemap requests, "
        f"code syntax colors are explicit, and {len(english)} published pages have Russian pairs"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate(Path(args.root))
    except (OSError, ContractError) as exc:
        print(f"ERROR docs i18n: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
