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
