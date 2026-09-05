# AGENTS.md

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
