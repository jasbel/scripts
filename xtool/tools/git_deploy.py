#!/usr/bin/env python3
"""Despliega commits del repo actual a los clones de preproducción (cherry-pick + push).

Uso (desde el repo origen, idealmente el subdirectorio donde trabajaste):
  xtool git-deploy [commit_o_rango]

Automatiza el flujo "ir a sc_clone, buscar el commit, cherry-pick, push":

  1. Detecta en ~/.config/xtool/git-deploy.json los mapeos cuyo repo origen
     sea el del directorio actual. Un commit que toca varios subdirectorios
     mapeados (p.ej. symfony_home y symfony_lujo) se despliega a TODOS sus
     destinos en secuencia; los archivos fuera de los mapeos se ignoran
     (se informa el total).
  2. Valida cada destino: que exista, sea repo git y esté limpio (si está
     sucio ese destino se omite con error, salvo -f/--force). La rama activa
     se compara con la esperada del mapeo: si difiere SOLO AVISA (no aborta).
  3. Muestra un resumen y pide Enter (Ctrl+C cancela). -y/--yes lo salta.
  4. Transporta con el modo acotado de git-cherry (archivo por archivo,
     'git apply -3', mapeo determinista <origen_sub>/ruta -> <destino_sub>/ruta).
     Los blobs se leen del repo origen LOCAL: no hace falta pushear el origen
     antes de desplegar.
  5. Commitea en cada destino UN solo commit con prefijo:
       [pre] <subject original>            (commit individual)
       [pre] <subject más nuevo> (N commits)   (rango, aplastado)
     El cuerpo lista el/los commit(s) de origen ('Origen: <sha>') y se
     conserva el autor original.
  6. Antes de pushear actualiza el destino con
     'git pull --rebase --autostash <remote> <rama activa>' (si la rama ya
     existe en el remote; si el rebase conflictúa se aborta y el destino
     queda SIN PUSH, con el commit local intacto).
  7. Pushea: git push <remote del mapeo> <rama activa del destino>.
     Con --no-push aplica y commitea sin pushear (sin pull).

Argumentos:
  - commit_o_rango: commit (abc1234, HEAD~1) o rango (abc..def, HEAD~2..HEAD).
    Default: HEAD (acotado al subdirectorio: no incluye cambios de otros
    subdirectorios del monorepo).

Opciones:
  -y/--yes      salta la confirmación con Enter.
  -f/--force    continúa aunque el destino esté sucio (bajo tu propio riesgo).
  --no-push     aplica y commitea, pero no pushea.

scss / css compilado:
  - Si algún archivo transportado de un app es *.scss, se ejecuta
    'npm run css' en el subdirectorio del DESTINO antes de commitear; el
    css generado se incluye en el MISMO commit [pre] (los css compilados
    están trackeados en estos repos).
  - Si el app no tiene package.json o no define el script 'css': aviso y
    se commitea sin compilar.
  - Si 'npm run css' falla: ese destino queda PENDIENTE (sin commit ni
    push); arregla el build, commitea con el mensaje sugerido y pushea.

Conflictos de css compilado:
  - Los conflictos o '.desde_origen' en assets/css/base/*.css se
    auto-resuelven con la versión del ORIGEN (incoming): son artefactos
    compilados, no código a conciliar. Si tras resolverlos no queda ningún
    otro conflicto, el destino se commitea y pushea normal; si quedan
    conflictos en otros archivos, ese destino queda PENDIENTE (con los css
    ya resueltos y staged).

Configuración en ~/.config/xtool/git-deploy.json (o la ruta de la variable
de entorno GIT_DEPLOY_CONFIG):

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

- origen/destino: subdirectorios (con ~ si quieres); el repo destino se
  resuelve desde 'destino'.
- patron: (opcional) expande el mapeo a los subdirectorios de PRIMER nivel
  de 'origen' cuyo nombre matchee el glob: un solo mapeo Web -> Web con
  "symfony_*" cubre todos los apps symfony_* actuales y futuros (cada app
  se despliega por separado, con su propio commit [pre], solo si el commit
  lo toca). Un mapeo explícito (sin patron) con el mismo 'origen' que uno
  expandido gana sobre él.
- rama: rama esperada en el destino (solo validación con aviso).
- remote: remote al que pushear (default "origin"); se pushea la rama
  ACTIVA del destino (donde cayó el commit).

Si un destino conflictúa (merge conflicts o archivos .desde_origen), ese
destino queda SIN commitear ni pushear, con los cambios en staging para
resolver a mano, y se continúa con los demás destinos. Código de salida:
0 si todos los destinos quedaron desplegados, 1 si alguno falló o quedó
pendiente.
"""

import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from xtool.common.git_transport import (
  EMPTY_TREE,
  aplicar_acotado,
  conflicted_files,
  escribir_blob,
  out,
  run,
  subdir_relativo,
)

ENV_CONFIG = "GIT_DEPLOY_CONFIG"
CONFIG_DEFAULT = Path.home() / ".config" / "xtool" / "git-deploy.json"
PREFIJO = "[pre]"

# Css compilado (artefacto): en conflictos, la versión del origen manda
CSS_BASE = "assets/css/base/"
SUFIJO_DESDE_ORIGEN = ".desde_origen"

EJEMPLO = """{
  "mapeos": [
    {
      "origen": "~/projects/symfony-sites/sites/solocruceros.com/DDD/1_Presentation/Web",
      "destino": "~/projects/symfony-sites/sites/sc_clone/DDD/1_Presentation/Web",
      "patron": "symfony_*",
      "rama": "home-symfony",
      "remote": "origin"
    }
  ]
}"""


def mostrar_ruta(ruta: Path) -> str:
  """Ruta para mostrar, con ~ en lugar del home."""
  return str(ruta).replace(str(Path.home()), "~", 1)


def cargar_mapeos():
  """Lee la configuración JSON. Devuelve la lista de mapeos o None si falla."""
  ruta = Path(os.environ.get(ENV_CONFIG, "") or CONFIG_DEFAULT)
  if not ruta.is_file():
    print(f"ERROR: no existe la configuración {mostrar_ruta(ruta)}")
    print("Crea el archivo con tus mapeos (origen y destino requeridos; rama y remote opcionales):")
    print(EJEMPLO)
    return None
  try:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
  except (json.JSONDecodeError, OSError) as e:
    print(f"ERROR: no se pudo leer {ruta}: {e}")
    return None
  mapeos_raw = datos.get("mapeos") if isinstance(datos, dict) else None
  if not isinstance(mapeos_raw, list) or not mapeos_raw:
    print(f"ERROR: {ruta} debe tener una lista no vacía bajo la clave 'mapeos'")
    return None
  mapeos = []
  for i, m in enumerate(mapeos_raw):
    if not isinstance(m, dict) or not str(m.get("origen") or "").strip() or not str(m.get("destino") or "").strip():
      print(f"ERROR: el mapeo #{i + 1} de {ruta} es inválido (requiere 'origen' y 'destino'): {m}")
      return None
    mapeos.append({
      "origen": Path(str(m["origen"]).strip()).expanduser().resolve(),
      "destino": Path(str(m["destino"]).strip()).expanduser().resolve(),
      "patron": str(m.get("patron") or "").strip() or None,
      "rama": str(m.get("rama") or "").strip() or None,
      "remote": str(m.get("remote") or "origin").strip() or "origin",
    })
  return mapeos


def expandir_mapeo(m, origen_repo: Path):
  """Expande un mapeo en candidatos concretos por subdirectorio.

  Sin 'patron': un único candidato (el mapeo tal cual).
  Con 'patron' (glob): un candidato por subdirectorio de primer nivel de
  'origen' cuyo nombre matchee: origen/<sub> -> destino/<sub>.
  """
  if not m["patron"]:
    return [{**m, "origen_sub": subdir_relativo(m["origen"], origen_repo)}]
  virtuales = []
  for sub in sorted(m["origen"].iterdir()):
    if sub.is_dir() and fnmatch.fnmatch(sub.name, m["patron"]):
      virtuales.append({
        **m,
        "origen": sub,
        "destino": m["destino"] / sub.name,
        "origen_sub": subdir_relativo(sub, origen_repo),
      })
  if not virtuales:
    print(f"AVISO: el patrón '{m['patron']}' no matchea ningún subdirectorio de {mostrar_ruta(m['origen'])}")
  return virtuales


def resolver_commits(origen_repo: Path, spec: str):
  """Resuelve el argumento en lista de commits (viejo -> nuevo) o None si error.

  Acepta un rev (abc1234, HEAD~1, HEAD) o un rango a..b (los merge commits
  del rango se omiten con aviso).
  """
  if ".." in spec:
    partes = spec.split("..")
    if len(partes) != 2 or not partes[0] or not partes[1]:
      print(f"ERROR: rango inválido: {spec} (formato esperado: a..b)")
      return None
    for ext in partes:
      if not out("git", "rev-parse", "--verify", "-q", f"{ext}^{{commit}}", cwd=origen_repo).strip():
        print(f"ERROR: '{ext}' no es un commit de {origen_repo}")
        return None
    shas = [l for l in out("git", "rev-list", "--reverse", spec, cwd=origen_repo).splitlines() if l]
    if not shas:
      print(f"ERROR: el rango {spec} está vacío en {origen_repo}")
      return None
    finales = []
    for sha in shas:
      if run("git", "rev-parse", "--verify", "-q", f"{sha}^2", cwd=origen_repo, check=False).returncode == 0:
        oneline = out("git", "log", "-1", "--oneline", sha, cwd=origen_repo).strip()
        print(f"AVISO: se omite el merge commit {oneline} (un rango no transporta merges).")
        continue
      finales.append(sha)
    if not finales:
      print("ERROR: el rango solo contiene merges; no hay nada que transportar.")
      return None
    return finales

  sha = out("git", "rev-parse", "--verify", f"{spec}^{{commit}}", cwd=origen_repo).strip()
  if not sha:
    print(f"ERROR: '{spec}' no es un commit de {origen_repo}")
    return None
  return [sha]


def archivos_commit(origen_repo: Path, sha: str):
  """Archivos que cambió el commit (contra su padre; empty tree si es raíz)."""
  base = f"{sha}^1"
  if run("git", "rev-parse", "--verify", "-q", f"{sha}^1", cwd=origen_repo, check=False).returncode != 0:
    base = EMPTY_TREE
  return [l for l in out("git", "diff", "--name-only", "--no-renames", base, sha, cwd=origen_repo).splitlines() if l]


def metadatos(origen_repo: Path, sha: str, formato: str) -> str:
  return out("git", "log", "-1", f"--format={formato}", sha, cwd=origen_repo).strip()


def armar_mensaje(origen_repo: Path, commits):
  """Mensaje del commit destino: prefijo [pre] + subject original + Origen."""
  if len(commits) == 1:
    sha = commits[0]
    subject = metadatos(origen_repo, sha, "%s")
    lineas = [f"{PREFIJO} {subject}"]
    body = metadatos(origen_repo, sha, "%b")
    if body:
      lineas += ["", body]
    lineas += ["", f"Origen: {sha[:8]} ({origen_repo.name})"]
    return "\n".join(lineas)
  subject = metadatos(origen_repo, commits[-1], "%s")
  lineas = [f"{PREFIJO} {subject} ({len(commits)} commits)", ""]
  for sha in commits:
    lineas.append(f"- {sha[:8]} {metadatos(origen_repo, sha, '%s')}")
  lineas += ["", f"Origen: {origen_repo.name}"]
  return "\n".join(lineas)


def validar_destino(candidato, force):
  """Valida el destino de un mapeo afectado. Devuelve (plan, errores, avisos)."""
  errores, avisos = [], []
  destino = candidato["destino"]
  destino_repo = None
  destino_sub = ""
  rama_activa = ""
  if not destino.is_dir():
    errores.append(f"el destino no existe: {mostrar_ruta(destino)}")
  else:
    repo_str = out("git", "rev-parse", "--show-toplevel", cwd=destino).strip()
    if not repo_str:
      errores.append(f"el destino no es un repo git: {mostrar_ruta(destino)}")
    else:
      destino_repo = Path(repo_str)
      destino_sub = subdir_relativo(destino, destino_repo)
      rama_activa = out("git", "branch", "--show-current", cwd=destino_repo).strip()
      if not rama_activa:
        errores.append(f"el destino está en HEAD detached: {mostrar_ruta(destino_repo)}")
      sucio = out("git", "status", "--porcelain", cwd=destino_repo).strip()
      if sucio:
        entradas = [l for l in sucio.splitlines() if l.strip()]
        if force:
          avisos.append(f"destino sucio ({len(entradas)} entrada(s) en git status); --force activo")
        else:
          errores.append("destino con cambios sin commitear (commitea/stashea o usa -f/--force):")
          errores += [f"    {e}" for e in entradas[:10]]
          if len(entradas) > 10:
            errores.append(f"    (... y {len(entradas) - 10} más)")
      if candidato["rama"] and rama_activa and rama_activa != candidato["rama"]:
        avisos.append(f"la rama activa '{rama_activa}' no es la esperada '{candidato['rama']}' (se continuará igual)")
  plan = {**candidato, "destino_repo": destino_repo, "destino_sub": destino_sub, "rama_activa": rama_activa}
  return plan, errores, avisos


def compilar_css(plan):
  """Ejecuta 'npm run css' en el subdirectorio del destino y stagea el css generado.

  Devuelve ('ok', None), ('sin-build', motivo) si no hay nada que ejecutar
  (se commitea sin compilar, con aviso) o ('fallo', None) si el build falló.
  """
  app = plan["destino"]
  pkg = app / "package.json"
  if not pkg.is_file():
    return "sin-build", f"no hay package.json en {mostrar_ruta(app)}"
  try:
    scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
  except (json.JSONDecodeError, OSError) as e:
    return "sin-build", f"package.json ilegible en {mostrar_ruta(app)}: {e}"
  if "css" not in scripts:
    return "sin-build", f"el package.json de {mostrar_ruta(app)} no define el script 'css'"
  if not shutil.which("npm"):
    return "sin-build", "npm no está en el PATH"

  print(f"==> scss transportados: compilando css en {mostrar_ruta(app)} (npm run css)...")
  resultado = subprocess.run(("npm", "run", "css"), cwd=app, text=True, capture_output=True)
  if resultado.returncode != 0:
    salida = (resultado.stderr.strip() or resultado.stdout.strip()).splitlines()
    print("ERROR: falló npm run css:")
    for linea in salida[-20:]:
      print(f"    {linea}")
    return "fallo", None

  # El css generado (trackeado) entra en el mismo commit [pre]
  sub = plan["destino_sub"] or "."
  run("git", "add", "-A", "--", sub, cwd=plan["destino_repo"])
  print("==> css compilado y agregado al staging")
  return "ok", None


def resolver_conflictos_css(plan, origen_repo: Path, commit_final: str):
  """Auto-resuelve conflictos/atenciones de css compilado con la versión del origen.

  Para archivos assets/css/base/*.css (artefactos compilados) el 'incoming'
  manda: se escribe la versión del repo origen en el commit final y se stagea.
  Devuelve la lista de rutas destino resueltas.
  """
  repo = plan["destino_repo"]
  destino_sub = plan["destino_sub"]
  origen_sub = plan["origen_sub"]

  def a_origen(path: str) -> str:
    rel = path[len(destino_sub) + 1:] if destino_sub else path
    return (origen_sub + "/" + rel) if origen_sub else rel

  def resolver(destino: str):
    origen_path = a_origen(destino)
    if run("git", "cat-file", "-e", f"{commit_final}:{origen_path}", cwd=origen_repo, check=False).returncode != 0:
      print(f"AVISO: no se pudo auto-resolver {destino} (no existe en {commit_final[:8]}).")
      return False
    escribir_blob(origen_repo, repo, commit_final, origen_path, destino)
    print(f"==> Auto-resuelto (css compilado, versión del origen): {destino}")
    return True

  resueltos = []
  for status, path in conflicted_files(repo):
    if "U" in status and path.endswith(".css") and CSS_BASE in path:
      if resolver(path):
        resueltos.append(path)
  for status, path in conflicted_files(repo):
    if path.endswith(SUFIJO_DESDE_ORIGEN):
      destino = path[: -len(SUFIJO_DESDE_ORIGEN)]
      if destino.endswith(".css") and CSS_BASE in destino and resolver(destino):
        (repo / path).unlink(missing_ok=True)
        resueltos.append(destino)
  return resueltos


def actualizar_destino(plan):
  """Trae lo nuevo del remote con pull --rebase antes de pushear.

  Si la rama aún no existe en el remote (push inicial) se omite. Si el rebase
  conflictúa se aborta (el commit local queda intacto) y devuelve False.
  """
  repo = plan["destino_repo"]
  remote, rama = plan["remote"], plan["rama_activa"]
  heads = run("git", "ls-remote", "--heads", remote, rama, cwd=repo, check=False)
  if heads.returncode != 0 or not heads.stdout.strip():
    print(f"==> La rama {rama} aún no existe en {remote} (push inicial); se omite el pull.")
    return True
  print(f"==> Actualizando el destino antes de pushear: git pull --rebase {remote} {rama}")
  pull = run("git", "pull", "--rebase", "--autostash", remote, rama, cwd=repo, check=False)
  if pull.returncode == 0:
    print(f"==> Destino actualizado: {out('git', 'log', '-1', '--oneline', cwd=repo).strip()}")
    return True
  run("git", "rebase", "--abort", cwd=repo, check=False)  # sin rebase en curso es inofensivo
  print(f"ERROR: falló git pull --rebase {remote} {rama}; se abortó el rebase y NO se pushea:")
  print((pull.stderr.strip() or pull.stdout.strip())[:1000])
  print("    El commit local sigue intacto; resuelve a mano y pushea:")
  print(f"      git -C {repo} pull --rebase {remote} {rama}   # resuelve y 'git rebase --continue'")
  print(f"      git -C {repo} push {remote} {rama}")
  return False


def desplegar(plan, commits, origen_repo, patch_file, msg_file, autor, no_push):
  """Aplica los commits en el destino, commitea y pushea. Devuelve el estado."""
  nombre = plan["origen_sub"] or "(raíz)"
  print(f"\n==> Desplegando {nombre} -> {mostrar_ruta(plan['destino'])}")

  for sha in commits:
    aplicar_acotado(plan["destino_repo"], origen_repo, sha, plan["origen_sub"], plan["destino_sub"], patch_file)

  # Css compilado en conflicto: la versión del origen (incoming) es autoritativa
  resolver_conflictos_css(plan, origen_repo, commits[-1])

  entradas = conflicted_files(plan["destino_repo"])
  pendiente = any("U" in s or p.endswith(SUFIJO_DESDE_ORIGEN) for s, p in entradas)

  if pendiente:
    print("==> PENDIENTE: este destino quedó con conflictos/atenciones; NO se commitea ni pushea.")
    print("    Resuelve a mano y luego commitea (mensaje sugerido abajo) y pushea:")
    print(f"      git -C {plan['destino_repo']} status")
    print(f"      git -C {plan['destino_repo']} diff --name-only --diff-filter=U   # conflictos")
    print("      ... editar + git add <archivo>; decidir los *.desde_origen")
    print(f"      git -C {plan['destino_repo']} push {plan['remote']} {plan['rama_activa']}")
    print("    Mensaje sugerido:")
    for linea in msg_file.read_text(encoding="utf-8").splitlines():
      print(f"      | {linea}")
    return "pendiente"

  if plan.get("scss"):
    estado_css, detalle = compilar_css(plan)
    if estado_css == "sin-build":
      print(f"AVISO: no se compiló el css ({detalle}); se commitea sin él.")
    elif estado_css == "fallo":
      print("==> PENDIENTE: falló npm run css; NO se commitea ni pushea.")
      print("    Arregla el build, compila, commitea (mensaje sugerido abajo) y pushea:")
      print(f"      cd {plan['destino']}")
      print("      npm run css")
      print(f"      git -C {plan['destino_repo']} add -A -- {plan['destino_sub'] or '.'}")
      print(f"      git -C {plan['destino_repo']} push {plan['remote']} {plan['rama_activa']}")
      print("    Mensaje sugerido:")
      for linea in msg_file.read_text(encoding="utf-8").splitlines():
        print(f"      | {linea}")
      return "pendiente"

  commit = run("git", "commit", "-F", str(msg_file), f"--author={autor}", cwd=plan["destino_repo"], check=False)
  if commit.returncode != 0:
    print("ERROR: no se pudo commitear en el destino:")
    print((commit.stderr.strip() or commit.stdout.strip())[:1000])
    return "error"

  oneline = out("git", "log", "-1", "--oneline", cwd=plan["destino_repo"]).strip()
  print(f"==> Commit creado en el destino: {oneline}")

  if no_push:
    print(f"==> Sin push (--no-push). Cuando quieras:")
    print(f"    git -C {plan['destino_repo']} push {plan['remote']} {plan['rama_activa']}")
    return "ok"

  if not actualizar_destino(plan):
    return "push_error"

  push = run("git", "push", plan["remote"], plan["rama_activa"], cwd=plan["destino_repo"], check=False)
  if push.returncode != 0:
    print(f"ERROR: no se pudo pushear a {plan['remote']}/{plan['rama_activa']}:")
    print((push.stderr.strip() or push.stdout.strip())[:1000])
    print("    El pull --rebase previo no alcanzó (el remote avanzó entre medias); resuelve y reintenta el push.")
    return "push_error"
  print(f"==> Pusheado a {plan['remote']}/{plan['rama_activa']}")
  return "ok"


def main(argv=None):
  argv = list(sys.argv[1:]) if argv is None else list(argv)

  if argv and argv[0] in ("-h", "--help"):
    print(__doc__)
    return 0

  yes = any(a in ("-y", "--yes") for a in argv)
  force = any(a in ("-f", "--force") for a in argv)
  no_push = "--no-push" in argv
  resto = [a for a in argv if a not in ("-y", "--yes", "-f", "--force", "--no-push")]
  if len(resto) > 1 or any(a.startswith("-") for a in resto):
    print("Uso: xtool git-deploy [-y|--yes] [-f|--force] [--no-push] [commit_o_rango]")
    return 1
  spec = resto[0] if resto else "HEAD"

  # --- Repo origen: el del directorio actual ---
  top = run("git", "rev-parse", "--show-toplevel", check=False)
  if top.returncode != 0 or not top.stdout.strip():
    print("ERROR: el directorio actual no es un repo git (ejecuta el comando desde el repo origen).")
    return 1
  origen_repo = Path(top.stdout.strip())
  print(f"==> Repo origen: {mostrar_ruta(origen_repo)}")

  mapeos = cargar_mapeos()
  if mapeos is None:
    return 1

  # --- Mapeos de este repo origen (los de 'patron' se expanden por app) ---
  explicitos, por_patron = {}, []
  for m in mapeos:
    if not m["origen"].is_dir():
      print(f"AVISO: se ignora el mapeo con origen inexistente: {mostrar_ruta(m['origen'])}")
      continue
    repo_str = out("git", "rev-parse", "--show-toplevel", cwd=m["origen"]).strip()
    if not repo_str:
      print(f"AVISO: se ignora el mapeo cuyo origen no está en un repo git: {mostrar_ruta(m['origen'])}")
      continue
    if Path(repo_str) != origen_repo:
      continue
    for c in expandir_mapeo(m, origen_repo):
      if m["patron"]:
        por_patron.append(c)
      else:
        explicitos[str(c["origen"])] = c
  # El mapeo explícito gana al expandido por patrón para el mismo subdirectorio
  candidatos = list(explicitos.values()) + [c for c in por_patron if str(c["origen"]) not in explicitos]
  if not candidatos:
    print(f"ERROR: no hay mapeos de git-deploy para el repo {mostrar_ruta(origen_repo)}")
    print("Revisa los valores de 'origen' en ~/.config/xtool/git-deploy.json.")
    return 1

  # --- Commits a desplegar ---
  commits = resolver_commits(origen_repo, spec)
  if not commits:
    return 1

  todos_archivos = set()
  for sha in commits:
    todos_archivos.update(archivos_commit(origen_repo, sha))

  # --- Mapeos afectados por esos commits ---
  afectados = []
  for c in candidatos:
    prefijo = (c["origen_sub"] + "/") if c["origen_sub"] else ""
    archivos_sub = list(todos_archivos) if not prefijo else [a for a in todos_archivos if a.startswith(prefijo)]
    if archivos_sub:
      afectados.append({
        **c,
        "archivos": len(archivos_sub),
        "scss": any(a.endswith(".scss") for a in archivos_sub),
      })
  if not afectados:
    print(f"ERROR: el commit no toca ningún subdirectorio mapeado de {mostrar_ruta(origen_repo)}:")
    for c in candidatos:
      print(f"    {c['origen_sub'] or '(raíz)'} -> {mostrar_ruta(c['destino'])}")
    return 1
  if any(not c["origen_sub"] for c in candidatos):
    fuera = []  # hay un mapeo con origen en la raíz: nada queda fuera
  else:
    prefijos = [(c["origen_sub"] + "/") for c in candidatos]
    fuera = [a for a in sorted(todos_archivos) if not any(a.startswith(p) for p in prefijos)]

  # --- Validación de destinos ---
  planes, excluidos = [], []
  for a in afectados:
    plan, errores, avisos = validar_destino(a, force)
    if errores:
      excluidos.append((plan, errores))
    else:
      planes.append((plan, avisos))
  if not planes:
    print("\nERROR: ningún destino pasó la validación:")
    for plan, errores in excluidos:
      print(f"  {mostrar_ruta(plan['destino'])}:")
      for e in errores:
        print(f"    {e}")
    return 1

  # --- Resumen + confirmación ---
  print(f"\n==> Despliegue de {len(commits)} commit(s) a {len(planes)} destino(s):")
  for i, (plan, avisos) in enumerate(planes, 1):
    rama = plan["rama_activa"] + (f" (esperada: {plan['rama']})" if plan["rama"] else "")
    print(f"  [{i}] {plan['origen_sub'] or '(raíz)'} -> {mostrar_ruta(plan['destino'])}")
    print(f"        repo destino: {mostrar_ruta(plan['destino_repo'])} | rama: {rama} | remote: {plan['remote']}")
    print(f"        {plan['archivos']} archivo(s) afectado(s)" + (" | incluye .scss -> npm run css" if plan.get("scss") else ""))
    for sha in commits:
      print(f"        {sha[:8]} {metadatos(origen_repo, sha, '%s')}")
    for a in avisos:
      print(f"        AVISO: {a}")
  for plan, errores in excluidos:
    print(f"  [EXCLUIDO] {mostrar_ruta(plan['destino'])}:")
    for e in errores:
      print(f"    {e}")
  if fuera:
    print(f"  {len(fuera)} archivo(s) del commit fuera de los mapeos serán ignorados.")

  if not yes:
    try:
      input("\nEnter para desplegar (Ctrl+C para cancelar)... ")
    except EOFError:
      print("ERROR: no hay stdin para confirmar; usa -y/--yes (p.ej. en scripts).")
      return 1
    except KeyboardInterrupt:
      print("\nCancelado.")
      return 130

  # --- Ejecución ---
  mensaje = armar_mensaje(origen_repo, commits)
  autor = metadatos(origen_repo, commits[-1], "%an <%ae>")
  patch_file = Path(tempfile.mkstemp(prefix="git_deploy_", suffix=".patch")[1])
  msg_file = Path(tempfile.mkstemp(prefix="git_deploy_", suffix=".msg")[1])
  try:
    msg_file.write_text(mensaje + "\n", encoding="utf-8")
    resultados = []
    pendientes_repo = set()  # destinos que quedaron pendientes (no ensuciar planes siguientes)
    for plan, _avisos in planes:
      if plan["destino_repo"] in pendientes_repo:
        print(f"\n==> OMISO {mostrar_ruta(plan['destino'])}: otro despliegue al mismo repo destino quedó pendiente; resuélvelo primero.")
        resultados.append((plan, "pendiente", None))
        continue
      estado = desplegar(plan, commits, origen_repo, patch_file, msg_file, autor, no_push)
      resultados.append((plan, estado, None))
      if estado != "ok":
        pendientes_repo.add(plan["destino_repo"])
  finally:
    patch_file.unlink(missing_ok=True)
    msg_file.unlink(missing_ok=True)

  # --- Resumen final ---
  print("\n==> Resumen del despliegue:")
  fallos = 0
  for plan, estado, _ in resultados:
    nombre = plan["origen_sub"] or "(raíz)"
    if estado == "ok":
      print(f"  OK        {nombre} -> {mostrar_ruta(plan['destino'])} ({plan['rama_activa']})")
    elif estado == "pendiente":
      print(f"  PENDIENTE {nombre} -> {mostrar_ruta(plan['destino'])} (revisar: conflictos o build de css; sin commit/push)")
      fallos += 1
    elif estado == "push_error":
      print(f"  SIN PUSH  {nombre} -> {mostrar_ruta(plan['destino'])} (commit creado; falló el pull/push)")
      fallos += 1
    else:
      print(f"  ERROR     {nombre} -> {mostrar_ruta(plan['destino'])}")
      fallos += 1
  return 1 if fallos else 0


if __name__ == "__main__":
  sys.exit(main())
