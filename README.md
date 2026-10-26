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

## git-diff

`xtool git-diff` genera un mensaje de commit Conventional Commits en español
(voz pasiva, con bullets y alcance) a partir del diff staged, usando IA
(zai-sdk, modelo `glm-5.3-flash`).

```bash
git add ...            # staging de los cambios a commitear
xtool git-diff         # analiza el diff y genera el mensaje
```

- Requiere `TOKEN_AI` en el `.env` del proyecto o en el del arsenal.
- El commit ganador se copia al portapapeles (listo para `git commit`).
- Si la rama actual lleva un ID numérico (`feat-123`, `issue/45`,
  `hotfix-789`, ...), se antepone `[123]` al commit generado.
- El diff se limita a 1M de caracteres: se excluyen lockfiles, binarios y
  generados y, si aún supera el límite, se trunca por archivo dejando un
  resumen (`--compact-summary`) de lo omitido.

## run-css

`xtool run-css` ejecuta `npm run css` (compilación SASS vía gulp) en todos los
directorios `symfony_*` de solocruceros, del origen elegido:

- `es` (default): `sites/solocruceros.com/DDD/1_Presentation/Web`
- `la`: `sites/solocruceros_latam/solocruceros.com/DDD/1_Presentation/Web`

```bash
xtool run-css                        # origen es
xtool run-css --origin la            # origen la (satélite latam)
xtool run-css --base <otro/dir>      # otro directorio base arbitrario
```

- Al terminar muestra un resumen con los directorios donde el comando no se
  pudo ejecutar (sin `package.json`/script `css` o con error de npm).
- Devuelve código de salida 1 si alguno no se ejecutó — útil para scripts.

## git-cherry

`xtool git-cherry [ruta_repo_origen] [hash_commit]` transporta un commit de otro
repositorio local al repo del directorio actual, dejando los cambios en staging
sin commitear (revisa con `git diff --cached`).

Ambos argumentos son opcionales:

- **ruta_repo_origen**: si no se envía, se toma del origen por defecto, con
  esta prioridad: override temporal de `git-cherry-origin` (vigente) >
  variable `GIT_CHERRY_ORIGEN` (entorno o `.env`, ej. el `.env` del arsenal
  con la ruta del monorepo de origen). Puede ser cualquier subdirectorio del
  repo origen.
- **hash_commit**: si no se envía: `stash@{0}` del origen → cambios sin
  commitear del origen (commit temporal con `git stash create`, sin tocar el
  repo) → error "no hay información de cambios". Los untracked de un
  `stash -u` también se transportan.

El repo destino debe estar limpio (`git status` limpio, untracked incluido;
el chequeo es sobre toda la raíz del repo destino). Si está sucio, el error
lista las entradas exactas que ve git; con `-f`/`--force` se continúa de
todos modos.

### Origen temporal (git-cherry-origin)

`xtool git-cherry-origin` cambia el origen por defecto de `git-cherry` por un
tiempo limitado, sin tocar `GIT_CHERRY_ORIGEN`:

```bash
xtool git-cherry-origin /ruta/.../Web/symfony_colombia        # activa 30 min
xtool git-cherry-origin /ruta/.../Web/symfony_mexico --min 60 # otra duración
xtool git-cherry-origin                                       # estado y minutos restantes
xtool git-cherry-origin --reset                               # cancela ya
```

- El vencimiento es **perezoso**: no hay proceso de fondo; al expirar,
  `git-cherry` vuelve solo al valor de `GIT_CHERRY_ORIGEN` (aunque la máquina
  se haya reiniciado entremedias). Mientras está vigente, `git-cherry` avisa
  en cada corrida cuánto falta.
- El override es **global**: afecta a `git-cherry` desde cualquier directorio.
  Prioridad: ruta como argumento > override temporal > `GIT_CHERRY_ORIGEN`.

### Modo acotado (origen = subdirectorio)

Si la ruta del origen es un subdirectorio del repo origen (p.ej.
`.../Web/symfony_home`), solo se transportan los cambios bajo ese
subdirectorio y se mapean de forma determinista al subdirectorio del repo
destino donde se ejecuta el comando (p.ej. `.../Web/symfony_chile`):

```
<origen_sub>/ruta/archivo  ->  <destino_sub>/ruta/archivo
```

Se aplica archivo por archivo con `git apply -3` (sin detección de renombres),
así que en un monorepo con varias apps parecidas git no puede "adivinar" y
esparcir cambios en apps no deseadas. Si un diff no aplica limpio: archivo
inexistente en destino → se agrega completo; conflicto → queda como merge
conflict real (unmerged: `git status` lo muestra y se lista con
`git diff --name-only --diff-filter=U`; resuelve editando + `git add`, o
`git checkout --ours/--theirs`); si no, la versión del origen queda como
`<ruta>.desde_origen`.

### Modo repo completo (origen = raíz del repo)

Hace un fetch mínimo por SHA con un remote temporal que remueve al terminar,
cherry-pick `-n -Xno-renames` (sin renombres: nada se reubica por similitud) y
resuelve los conflictos modify/delete cross-repo mapeando la ruta al sufijo que
exista en el destino.

## git-deploy

`xtool git-deploy [commit_o_rango]` despliega commits del repo actual a los
clones de preproducción (sc_clone / sc_clone_2): cherry-pick acotado al
subdirectorio, commit con prefijo `[pre] ` y push. Es el flujo "ir a sc_clone,
buscar el commit, cherry-pick, push" reducido a un solo comando ejecutado
desde donde trabajaste.

```bash
cd ~/projects/symfony-sites/sites/solocruceros.com/DDD/1_Presentation/Web/symfony_home
git add ... && git commit -m "..."
xtool git-deploy              # HEAD -> sc_clone, commitea "[pre] ..." y pushea
xtool git-deploy abc1234      # un commit específico
xtool git-deploy HEAD~2..HEAD # rango: se aplasta (squash) en UN commit por destino
xtool git-deploy -y           # sin pedir confirmación con Enter
xtool git-deploy --no-push    # aplica y commitea, sin pushear
```

- Un commit que toca varios subdirectorios mapeados (p.ej. `symfony_home` y
  `symfony_lujo`) se despliega a **todos** sus destinos en secuencia; los
  archivos fuera de los mapeos se ignoran (se informa el total).
- Resumen + Enter antes de actuar (Ctrl+C cancela). Validaciones: destino
  limpio (si está sucio se excluye, salvo `-f`/`--force`); la rama activa se
  compara con la esperada del mapeo y **solo avisa** si difiere.
- Antes de pushear se actualiza el destino con `git pull --rebase --autostash
  <remote> <rama>` (se omite si la rama aún no existe en el remote). Si el
  rebase conflictúa se aborta y el destino queda SIN PUSH, con el commit
  local intacto para resolver a mano.
- El push es `git push <remote del mapeo> <rama activa del destino>`; no hace
  falta pushear el origen antes: los blobs se leen del repo local.
- Mensaje: `[pre] <subject original>` (con `Origen: <sha>` en el cuerpo y el
  autor original). Los rangos generan un solo commit
  `[pre] <subject más nuevo> (N commits)` con la lista completa.
- Si un destino conflictúa (merge conflicts o `.desde_origen`), queda SIN
  commitear ni pushear (cambios en staging para resolver a mano) y se continúa
  con los demás. Sale con código 1 si algo falló o quedó pendiente.

### scss → css compilado

Si algún archivo transportado de un app es `*.scss`, se ejecuta `npm run css`
en el subdirectorio del **destino** antes de commitear y el css generado entra
en el **mismo commit `[pre]`** (los css compilados están trackeados en estos
repos). Si el app no tiene `package.json` o no define el script `css`: aviso y
se commitea sin compilar. Si `npm run css` falla: ese destino queda PENDIENTE
(sin commit/push).

Los conflictos o `.desde_origen` en `assets/css/base/*.css` se **auto-resuelven
con la versión del origen** (incoming): son artefactos compilados, no código a
conciliar. Si tras resolverlos no queda ningún otro conflicto, el destino se
commitea y pushea normal; si quedan conflictos en otros archivos, el destino
queda PENDIENTE con los css ya resueltos en staging.

### Configuración

`~/.config/xtool/git-deploy.json` (o la ruta de la variable `GIT_DEPLOY_CONFIG`):

```json
{
  "mapeos": [
    {
      "origen": "~/projects/symfony-sites/sites/solocruceros.com/DDD/1_Presentation/Web",
      "destino": "~/projects/symfony-sites/sites/sc_clone/DDD/1_Presentation/Web",
      "patron": "symfony_*",
      "rama": "home-symfony",
      "remote": "origin"
    }
  ]
}
```

- `origen`/`destino`: subdirectorios (admiten `~`); `rama` es la esperada en el
  destino (solo validación con aviso) y `remote` el destino del push (default
  `origin`).
- `patron`: expande el mapeo a los subdirectorios de primer nivel de `origen`
  cuyo nombre matchee el glob — un solo mapeo `Web -> Web` con `symfony_*`
  cubre todos los apps `symfony_*` actuales y futuros, y cada app se despliega
  por separado (su propio commit `[pre]`) solo si el commit lo toca. Un mapeo
  explícito (sin `patron`) con el mismo `origen` gana sobre el patrón.
- La lógica de transporte (modo acotado archivo por archivo con `git apply -3`)
  vive en `xtool/common/git_transport.py`, compartida con `git-cherry`.

## info

`xtool info` muestra información del arsenal en un solo lugar:

- **Ruta del proyecto**, versión (leída de `pyproject.toml`), rama git y
  cantidad de comandos.
- **Ejecutable en uso**: qué `xtool` estás corriendo (venv del proyecto con
  `uv run` o instalación global editable) y cuál resuelve el PATH.
- **PATH**: si `~/.local/bin` está presente (y el comando exacto para
  agregarlo si falta).
- **Entorno**: versión de Python y presencia del `.env` (sin mostrar valores).

```bash
xtool info
```

## Autocompletado

### zsh (oh-my-zsh)

`completions/_xtool` es un completion nativo de zsh con descripciones y menú
interactivo. La lista de comandos se genera con el comando oculto
`xtool __complete` (formato `comando:descripción`), así que los tools nuevos
de `xtool/tools/` autocompletean sin tocar nada.

Activación: symlink en el fpath de oh-my-zsh (así se actualiza solo con
`xtool update`):

```bash
mkdir -p ~/.oh-my-zsh/custom/completions
ln -sf ~/projects/script/scripts/completions/_xtool ~/.oh-my-zsh/custom/completions/_xtool
```

Abrir terminal nueva (o `exec zsh`). Para zsh sin oh-my-zsh: poner el archivo
en un directorio del `fpath` antes de `compinit`.

### bash

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

### Qué completa zsh

- `xtool <TAB>` y `xtool help <TAB>` — comandos con su descripción (menú
  navegable con las flechas).
- `xtool emails <TAB>` — subcomandos (`server build watch extract dist`) y
  flags (`--port --no-install`).
- `xtool git-cherry <TAB>` — directorios; segundo TAB hashes del repo origen.
- `xtool git-cherry-origin <TAB>` — directorios y flags (`--reset --min`).
- `xtool git-deploy <TAB>` — hashes recientes del repo actual + `HEAD~N`, y
  flags (`-y --yes -f --force --no-push`).

## Actualizar / desinstalar

```bash
xtool update               # git pull del arsenal desde cualquier directorio
uv tool upgrade scripts    # tras cambiar dependencias en pyproject.toml
uv tool uninstall scripts  # elimina el comando xtool
```

## Desarrollo

Ejecutar sin instalar:

```bash
uv run --no-sync xtool
uv run --no-sync -m xtool.tools.git_diff
```
