# Documentation site

Solo VPS documentation is plain Markdown rendered with **Material for MkDocs**. English is the default site language; every published page has a Russian counterpart selectable from the language control in the header.

The Markdown files in `docs/` remain the source of truth. Theme overrides live in `overrides/`, while the visual layer lives in `docs/stylesheets/extra.css` and `docs/assets/brand/`.

## Preview locally

On Windows, double-click `docs.bat` in the repository root, or run it in PowerShell:

```powershell
.\docs.bat
```

The launcher creates `.venv-docs`, installs the pinned documentation dependencies, and serves the site at `http://127.0.0.1:8000/` (Russian: `http://127.0.0.1:8000/ru/`). Wait for the serving message, then open the address in your browser. Keep the terminal open; press `Ctrl+C` to stop. Changes to Markdown appear after automatic rebuilds.

The first run needs Python 3.12 or newer and internet access. Make, WSL and PowerShell activation are not needed. If Python is not on PATH or registered with `py`, set `DOCS_PYTHON` to the full path of `python.exe`. Run `.\docs.bat build` for a strict static build. If port 8000 is occupied, stop the previous preview before starting another one.

On Linux/macOS, from the repository root:

```bash
make docs
```

The first run creates an isolated `.venv-docs` environment and installs `requirements-docs.txt`. Open the local address printed by MkDocs, normally `http://127.0.0.1:8000/`.

The documentation stack intentionally pins `MkDocs 1.6.1`: this site uses the MkDocs 1.x plugin API and Material theme overrides. Do not upgrade to MkDocs 2.x without a dedicated docs-stack migration.

Press `Ctrl+C` to stop the preview server.

## Build exactly as CI does

```bash
make docs-build
```

This runs:

```bash
mkdocs build --strict
```

The generated static site is written to `site/`. Treat any strict-build warning as documentation debt rather than suppressing it by default.

Material 9.7.2+ prints an upstream MkDocs 2.0 compatibility notice before direct `mkdocs` commands. It is informational and is not a MkDocs build warning. `make docs`, `make docs-build`, and docs CI set `NO_MKDOCS_2_WARNING=1`; for a direct PowerShell command you can do the same for the current shell:

```powershell
$env:NO_MKDOCS_2_WARNING="1"
mkdocs build --strict
```

## Run without Make

Linux/macOS:

```bash
python3 -m venv .venv-docs
source .venv-docs/bin/activate
python -m pip install -r requirements-docs.txt
mkdocs serve
```

Windows PowerShell:

```powershell
py -m venv .venv-docs
.\.venv-docs\Scripts\Activate.ps1
python -m pip install -r requirements-docs.txt
mkdocs serve
```

If PowerShell blocks virtual-environment activation, allow scripts only for the current shell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Localization contract

`mkdocs-static-i18n` uses the suffix structure:

```text
docs/quick-start.md       -> /
docs/quick-start.ru.md    -> /ru/
```

Keep Markdown links language-neutral — for example, both localized source files link to `quick-start.md`, not `quick-start.ru.md`. The plugin resolves the correct localized target during the build. Raw HTML links are not rewritten by MkDocs, so use the built pretty URL form such as `href="quick-start/"`, never `href="quick-start.md"`.

When a published English page changes, update its `.ru.md` pair in the same change. Do not translate commands, file paths, configuration keys, environment variables, API fields, Make targets, or machine-readable confirmation tokens.

Internal release/evidence pages remain in the repository and are deliberately excluded from the public user site.

## Visual customization

The site intentionally uses Material as an engine, not as the final visual identity. Colors, typography, navigation states, cards and code blocks are defined in `docs/stylesheets/extra.css`. The visible language control is a small override of Material's alternate-language partial at `overrides/partials/alternate.html`. `overrides/main.html` keeps Material 9.7 from issuing invalid per-page sitemap requests while `mkdocs-static-i18n` remains responsible for the localized sitemap.

Keep overrides narrow. Prefer CSS and documented Material extension points over copying large upstream templates.

## GitHub Pages

`.github/workflows/docs.yml` validates the site with a strict build on documentation pull requests. Changes under both `docs/` and `overrides/` trigger the documentation workflow. A push to `main` uploads the built site as a Pages artifact and deploys it to the `github-pages` environment.

After the public repository exists:

1. Open the repository **Settings → Pages**.
2. Set **Build and deployment → Source** to **GitHub Actions**. Restrict the `github-pages` environment to the default branch.
3. Add the actual Pages URL as `site_url` in `mkdocs.yml`, including the repository path and trailing slash for a project site. This base URL keeps language links correct.
4. Set `repo_url` to the actual repository URL and enable `edit_uri: edit/main/docs/` only if `main` is the default branch.
5. Run `make docs-build` before committing the URL change, then verify the hosted deployment, English/Russian links, and edit links.

Do not add a fake repository URL or production documentation domain before those resources exist.

## Navigation policy

`mkdocs.yml` is task-oriented. New user-facing pages should live under the smallest relevant section rather than mirroring Ansible roles or repository internals.

Release evidence, clean-target procedures and deep maintainer test material stay in the repository instead of occupying the public product navigation.
