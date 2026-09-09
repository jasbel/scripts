# scripts / xtool

Arsenal de herramientas globales expuesto como comando `xtool`.
Cada herramienta es un módulo en `xtool/tools/` y se invoca como `xtool <comando>`.

## Instalar el comando `xtool` en esta Mac

Requisito: [uv](https://docs.astral.sh/uv/). Si no está:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Desde la raíz del proyecto (`.../scripts`):

```bash
uv tool install --editable .
```

Esto crea un entorno aislado y deja el ejecutable en `~/.local/bin/xtool`.
Con `--editable` los cambios y las nuevas herramientas que agregues a `xtool/tools/`
se reflejan sin reinstalar.

Verifica que `~/.local/bin` está en el PATH (zsh):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

Comprobar instalación:

```bash
xtool                 # lista los comandos disponibles
xtool kill-port 3000  # ejemplo de uso
```

## Emails

`xtool emails` maneja el proyecto de preview de emails que vive en `xtool/emails/`
(server Express con hot-reload para las plantillas de solocruceros y odoo).
Requiere node/npm en el PATH; la primera vez instala las dependencias solo.

```bash
xtool emails                # server de preview con hot-reload (default, puerto 3466)
xtool emails --port 3500    # server en otro puerto
xtool emails build          # compila MJML -> HTML una sola vez
xtool emails watch          # compila MJML y recompila al guardar
xtool emails extract        # extrae datos del HTML de referencia a data.json
```

Configuración del proyecto (rutas de templates, SMTP para envíos de prueba)
en `xtool/emails/.env` — ver `xtool/emails/.env.example`.

## git-cherry

`xtool git-cherry [ruta_repo_origen] [hash_commit>` transporta un commit de otro
repositorio local al repo del directorio actual, dejando los cambios en staging
sin commitear (revisa con `git diff --cached`).

Ambos argumentos son opcionales:

- **ruta_repo_origen**: si no se envía, se toma de la variable
  `GIT_CHERRY_ORIGEN` (entorno o `.env`, ej. el `.env` del arsenal con la ruta
  del monorepo de origen). Puede ser cualquier subdirectorio del repo origen.
- **hash_commit**: si no se envía: `stash@{0}` del origen → cambios sin
  commitear del origen (commit temporal con `git stash create`, sin tocar el
  repo) → error "no hay información de cambios". Los untracked de un
  `stash -u` también se transportan.

Hace un fetch mínimo por SHA con un remote temporal que remueve al terminar, y
resuelve los conflictos modify/delete cross-repo mapeando la ruta al sufijo que
exista en el destino.

## Autocompletado (bash)

El script `completions/xtool.bash` agrega autocompletado con TAB:

- `xtool <TAB>` — lista los comandos disponibles (se genera dinámicamente
  parseando la salida de `xtool`, así que los tools nuevos de `xtool/tools/`
  autocompletean sin tocar el script).
- `xtool help <TAB>` — los mismos comandos.
- `xtool emails <TAB>` — subcomandos (`server build watch extract`) y
  `xtool emails -<TAB>` — flags (`--port --no-install -h --help`).
- `xtool git-cherry <TAB>` — directorios (ruta del repo origen).

Activación: agregar al final del `~/.bashrc` (ajustar la ruta si el repo
vive en otro lugar):

```bash
source ~/projects/scripts/completions/xtool.bash
```

Y recargar la sesión (`source ~/.bashrc` o abrir terminal nueva). Para que
la completación dinámica funcione, `xtool` debe estar instalado y en el PATH.

## Actualizar / desinstalar

```bash
uv tool upgrade scripts    # tras cambiar dependencias en pyproject.toml
uv tool uninstall scripts  # elimina el comando xtool
```

## Desarrollo

Ejecutar sin instalar:

```bash
uv run --no-sync xtool
uv run --no-sync -m xtool.tools.git_diff
```
