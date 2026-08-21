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
