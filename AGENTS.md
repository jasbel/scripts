# AGENTS.md

## What this is

Personal global CLI toolkit distributed as the `xtool` command (`uv tool install --editable .` → `~/.local/bin/xtool`). Root `main.py` is unused uv scaffold — the real entrypoint is `xtool/cli.py` (see `[project.scripts]` in `pyproject.toml`).

## Adding / changing a tool

- A command = one file in `xtool/tools/<name>.py` exposing `main(argv)`. The CLI auto-discovers files; underscores become dashes (`git_diff.py` → `xtool git-diff`). Nothing else to register.
- The module docstring IS the help: first line appears in `xtool` listing, full docstring in `xtool help <cmd>`. Docstrings are read via AST **without importing**, so keep side effects inside `main()`.
- No CLI framework — parse `argv` manually like existing tools. Shared helpers go in `xtool/common/`.

## Running / verifying

- No tests, lint, or CI. Verify by executing the tool: `uv run --no-sync xtool <cmd>` or `uv run --no-sync -m xtool.tools.<name>` (module form relies on the `if __name__ == "__main__"` guard each tool has).
- After changing dependencies in `pyproject.toml`, run `uv tool upgrade scripts` — the installed `xtool` won't see them otherwise. Adding new tool *files* needs no reinstall (editable install).

## Env loading

`xtool/env_local.py` parses `.env` files with no library and runs **at import time**: cwd `.env` first (calling project overrides), then the arsenal's own `.env` up the tree. `.env` is gitignored. `TOKEN_AI` is required by the `git-diff` tool.

## Conventions

- Python 3.12, uv-managed, hatchling build. Deps: `zai-sdk` (AI for git-diff), `psutil`.
- 2-space indent in Python (not PEP8's 4) — match existing files.
- Docstrings, help text, and user-facing messages are in Spanish.
- Commit messages follow Conventional Commits (there's even an `xtool git-diff` tool that generates them from the staged diff).

## `xtool/emails/` subproject

Node/Express MJML email preview tooling (solocruceros + odoo) absorbed via git subtree — don't restructure its layout. It has its own `package.json` and `.env` (see `.env.example`); docs in `xtool/emails/emails.md`. `xtool emails` wraps it; requires node/npm in PATH.
Personal CLI arsenal exposed as the `xtool` command. Python 3.12 (uv-managed) with an embedded Node subproject for email preview. No tests, no lint, no CI — verify changes by running the affected tool.

## Commands

```bash
uv run --no-sync xtool                          # run without installing
uv run --no-sync -m xtool.tools.git_diff        # run one tool directly
uv tool install --editable .                    # install xtool globally (dev flow)
uv tool upgrade scripts                         # after changing deps in pyproject.toml
```

Package name in pyproject is `scripts`, but the command is `xtool`. Root `main.py` is a leftover stub — not the entrypoint (`xtool/cli.py` is).

## Adding a tool

Drop a module in `xtool/tools/`. The CLI discovers it automatically: filename becomes the subcommand (`_` → `-`), the module docstring becomes the manual (`xtool help <cmd>`, parsed via AST without importing), and it must define `main(argv) -> int`. No registry to update. New files work immediately with `uv run --no-sync xtool <cmd>`; under an editable install no reinstall is needed either.

## Env loading

`xtool/env_local.py::load_env()` merges all `.env` files: CWD first, then walking up from the package dir. First definition wins (`os.environ.setdefault`) — a project's own `.env` doesn't block the arsenal's `TOKEN_AI` (needed by `git-diff`). `.env` is gitignored; never commit it.

## Emails subproject (`xtool/emails/`)

Self-contained Node/Express preview server (own `package.json`, ESM, gitignored `node_modules`). Run via `xtool emails` — never `npm start` directly; the wrapper checks node/npm, auto-installs deps, and sets `PORT` (`--port`, default 3466). Subcommands: `build`, `watch`, `extract`; `--no-install` skips dep install.

- Config in `xtool/emails/.env` (see `.env.example`): SMTP for test sends, `FIGMA_TOKEN`, and template roots.
- `SOLOCRUCEROS_TEMPLATES_DIR` default is a Linux path to an external Symfony repo — on Windows it MUST be set in `.env` or the solocruceros project shows as unavailable (odoo still works, it lives in-repo).
- Two template engines (registry in `projects.js`): `solocruceros` (Mustache, external PHP repo) and `odoo` (inline `{{ }}` placeholders, `templates/odoo/<id>/body.html`).
- MJML convention: `templates/odoo/<id>/body.mjml` compiles to sibling `body.html`; odoo `{{ }}` placeholders survive MJML compilation intact. `body.html` is generated — edit the `.mjml` source.
- Preview server routes: `/` (UI), `/:project/:tpl/render[/:client]`, `/preview/:client`, `/api/templates`, `POST /:project/:tpl/send-test`. Hot-reload via injected WS snippet.
- Mustache escaping is deliberately matched to Mustache.php (only `& < > "`) — don't "fix" it to the JS default.

## Conventions

- Commit messages and code comments are in Spanish: Conventional Commits type + passive-voice Spanish ("Se agregó...", "Se ha implementado..."). Bullets use `* ` with a scope in parentheses.
- README.md documents user-facing install/usage — update it when adding tools or subcommands.
