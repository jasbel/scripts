#!/usr/bin/env python3
"""Replica un commit (o los cambios sin commitear) del app actual a otros apps.

Uso (desde el app origen, p.ej. .../Web/symfony_home):
  xtool replicate <alias...> [commit] [--stash] [-y] [--yes] [--no-force]

Automatiza el flujo "git-cherry-origin + git-cherry uno a uno": el origen es
el directorio actual (el repo Web y el subdirectorio symfony_* donde estás),
y el commit se transporta a cada destino con la misma maquinaria acotada de
git-cherry/git-deploy: <origen_sub>/ruta -> <destino_sub>/ruta, lectura
LOCAL de blobs (sin pushear ni fetchear el origen), 'git apply -3' archivo
por archivo, sin detección de renombres.

Destinos por alias (también se acepta el nombre completo, p.ej.
symfony_chile):

  cl  -> symfony_chile          co -> symfony_colombia
  cr  -> symfony_costarica      mx -> symfony_mexico
  sc / home -> symfony_home     is / islas -> symfony_islasgriegas
  lu  -> symfony_lujo           me -> symfony_mediterraneo
  all -> los destinos fijados con 'destinos' (menos el origen); sin
         'destinos', todos los symfony_* de las raíces configuradas

Los destinos se buscan como <raíz>/symfony_<app> en
~/.config/xtool/replicate.json (o la ruta de la variable de entorno
GIT_REPLICATE_CONFIG). Solo las raíces PRINCIPALES: los clones de
preproducción (sc_clone, sc_clone_2, ...) siguen siendo territorio de
'xtool git-deploy'.

La clave opcional 'destinos' FIJA la ruta exacta de cada app (la clave es
el nombre del app, p.ej. symfony_chile): el alias va siempre a esa ruta,
sin ambigüedad aunque el app exista en varias raíces (p.ej.
symfony_colombia en europa y latam), y 'all' replica exactamente esos
destinos (menos el origen) en vez de barrer ambas raíces:

  {
    "raices": [
      "~/projects/symfony-sites/sites/solocruceros.com/DDD/1_Presentation/Web",
      "~/projects/symfony-sites/sites/solocruceros_latam/solocruceros.com/DDD/1_Presentation/Web"
    ],
    "destinos": {
      "symfony_chile": "~/projects/symfony-sites/sites/solocruceros_latam/solocruceros.com/DDD/1_Presentation/Web/symfony_chile",
      "symfony_colombia": "~/projects/symfony-sites/sites/solocruceros_latam/solocruceros.com/DDD/1_Presentation/Web/symfony_colombia",
      "symfony_costarica": "~/projects/symfony-sites/sites/solocruceros_latam/solocruceros.com/DDD/1_Presentation/Web/symfony_costarica",
      "symfony_mexico": "~/projects/symfony-sites/sites/solocruceros_latam/solocruceros.com/DDD/1_Presentation/Web/symfony_mexico",
      "symfony_home": "~/projects/symfony-sites/sites/solocruceros.com/DDD/1_Presentation/Web/symfony_home",
      "symfony_islasgriegas": "~/projects/symfony-sites/sites/solocruceros.com/DDD/1_Presentation/Web/symfony_islasgriegas",
      "symfony_mediterraneo": "~/projects/symfony-sites/sites/solocruceros.com/DDD/1_Presentation/Web/symfony_mediterraneo",
      "symfony_lujo": "~/projects/symfony-sites/sites/solocruceros.com/DDD/1_Presentation/Web/symfony_lujo"
    }
  }

Fuente de los cambios:
  - default: HEAD del origen (el commit actual).
  - <commit>: cualquier rev del origen (hash, HEAD~1, stash@{2}, ...).
  - --stash: los cambios sin commitear del origen, INCLUYENDO untracked:
    se crea 'git stash push -u', se captura el SHA y se APLICA de vuelta al
    origen ('git stash apply' + drop: el origen nunca pierde sus cambios,
    ni siquiera transitoriamente), y luego se replica ese snapshot. Los
    cambios vuelven al worktree como no-staged (como un 'git stash pop'
    normal) y tus stashes previos quedan intactos. Si el worktree está
    limpio pero existe stash@{0}, se usa ese (aplicándolo también al origen
    y conservando tu entrada, con aviso). El apply ocurre ANTES de tocar
    destinos: los apps que comparten repo con el origen no interfieren.

Por defecto NO se commitea: cada destino queda con los cambios en staging
('git diff --cached'). Forzado por defecto: un destino sucio no aborta
(solo avisa) y los conflictos de contenido se resuelven con la versión del
ORIGEN (staged; la versión previa queda en HEAD mientras no se commitee).
Con --no-force el modo es conservador: los destinos sucios se EXCLUYEN y
los conflictos de contenido quedan como merge conflict (UU) para resolver
a mano.

  -y: además commitea y pushea cada destino ejecutando 'xtool git-diff -y'
      EN su repo (mensaje Conventional Commits con IA + commit + pull +
      push). Como toca remotos, pide confirmación con Enter antes de
      empezar; --yes la salta. Un destino con conflictos o sin cambios
      queda reportado y se continúa con los demás.

Ejemplos (parado en .../Web/symfony_home):
  xtool replicate cl me             # HEAD -> symfony_chile y symfony_mediterraneo
  xtool replicate all --stash       # cambios sin commitear -> los destinos fijados (y al origen)
  xtool replicate cl me abc1234 -y  # ese commit, commitea y pushea en cada destino

Código de salida: 0 si todos los destinos quedaron replicados, 1 si alguno
falló o quedó pendiente.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from xtool.common.git_transport import (
  aplicar_acotado,
  conflicted_files,
  escribir_blob,
  mapear_por_prefijo,
  out,
  run,
  subdir_relativo,
  transportar_untracked_stash,
)
from xtool.env_local import load_env

load_env()

ENV_CONFIG = "GIT_REPLICATE_CONFIG"
CONFIG_DEFAULT = Path.home() / ".config" / "xtool" / "replicate.json"

ALIAS = {
  "cl": "symfony_chile", "chile": "symfony_chile", "symfony_chile": "symfony_chile",
  "co": "symfony_colombia", "colombia": "symfony_colombia", "symfony_colombia": "symfony_colombia",
  "cr": "symfony_costarica", "costarica": "symfony_costarica", "symfony_costarica": "symfony_costarica",
  "mx": "symfony_mexico", "mexico": "symfony_mexico", "symfony_mexico": "symfony_mexico",
  "sc": "symfony_home", "home": "symfony_home", "symfony_home": "symfony_home",
  "is": "symfony_islasgriegas","ig": "symfony_islasgriegas", "islas": "symfony_islasgriegas", "symfony_islasgriegas": "symfony_islasgriegas",
  "lu": "symfony_lujo", "lujo": "symfony_lujo", "symfony_lujo": "symfony_lujo",
  "me": "symfony_mediterraneo", "mediterraneo": "symfony_mediterraneo", "symfony_mediterraneo": "symfony_mediterraneo",
}

EJEMPLO_CONFIG = """{
  "raices": [
    "~/projects/symfony-sites/sites/solocruceros.com/DDD/1_Presentation/Web",
    "~/projects/symfony-sites/sites/solocruceros_latam/solocruceros.com/DDD/1_Presentation/Web"
  ],
  "destinos": {
    "symfony_chile": "~/projects/symfony-sites/sites/solocruceros_latam/solocruceros.com/DDD/1_Presentation/Web/symfony_chile",
    "symfony_colombia": "~/projects/symfony-sites/sites/solocruceros_latam/solocruceros.com/DDD/1_Presentation/Web/symfony_colombia",
    "symfony_costarica": "~/projects/symfony-sites/sites/solocruceros_latam/solocruceros.com/DDD/1_Presentation/Web/symfony_costarica",
    "symfony_mexico": "~/projects/symfony-sites/sites/solocruceros_latam/solocruceros.com/DDD/1_Presentation/Web/symfony_mexico",
    "symfony_home": "~/projects/symfony-sites/sites/solocruceros.com/DDD/1_Presentation/Web/symfony_home",
    "symfony_islasgriegas": "~/projects/symfony-sites/sites/solocruceros.com/DDD/1_Presentation/Web/symfony_islasgriegas",
    "symfony_mediterraneo": "~/projects/symfony-sites/sites/solocruceros.com/DDD/1_Presentation/Web/symfony_mediterraneo",
    "symfony_lujo": "~/projects/symfony-sites/sites/solocruceros.com/DDD/1_Presentation/Web/symfony_lujo"
  }
}"""

USO = "Uso: xtool replicate <alias...> [commit] [--stash] [-y] [--yes] [--no-force]"


def mostrar_ruta(ruta: Path) -> str:
  """Ruta para mostrar, con ~ en lugar del home."""
  return str(ruta).replace(str(Path.home()), "~", 1)


def _porcelain(repo: Path):
  """Entradas no vacías de 'git status --porcelain' del repo dado."""
  return [l for l in out("git", "status", "--porcelain", cwd=repo).splitlines() if l.strip()]


def cargar_config():
  """Lee la configuración JSON. Devuelve (raíces, destinos) o (None, None).

  raíces: lista de Web principales donde buscar <raíz>/symfony_<app>.
  destinos: mapeo opcional app -> ruta exacta que fija cada alias y el
  alcance de 'all' (dict vacío si la clave no existe).
  """
  ruta = Path(os.environ.get(ENV_CONFIG, "") or CONFIG_DEFAULT)
  if not ruta.is_file():
    print(f"ERROR: no existe la configuración {mostrar_ruta(ruta)}")
    print("Crea el archivo con tus raíces (los Web principales; los clones de pre van con git-deploy):")
    print(EJEMPLO_CONFIG)
    return None, None
  try:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
  except (json.JSONDecodeError, OSError) as e:
    print(f"ERROR: no se pudo leer {ruta}: {e}")
    return None, None
  raices_raw = datos.get("raices") if isinstance(datos, dict) else None
  if not isinstance(raices_raw, list) or not raices_raw:
    print(f"ERROR: {ruta} debe tener una lista no vacía bajo la clave 'raices'")
    return None, None
  raices = []
  for r in raices_raw:
    if not isinstance(r, str) or not r.strip():
      print(f"ERROR: raíz inválida en {ruta}: {r!r}")
      return None, None
    raices.append(Path(r.strip()).expanduser().resolve())
  destinos_raw = datos.get("destinos", {}) if isinstance(datos, dict) else {}
  if not isinstance(destinos_raw, dict):
    print(f"ERROR: 'destinos' en {ruta} debe ser un objeto app -> ruta")
    return None, None
  destinos = {}
  for app, r in destinos_raw.items():
    if not isinstance(r, str) or not r.strip():
      print(f"ERROR: destino inválido para {app!r} en {ruta}: {r!r}")
      return None, None
    destinos[app] = Path(r.strip()).expanduser().resolve()
  return raices, destinos


def resolver_commit(origen_repo: Path, commit_arg, stash: bool):
  """Resuelve el commit a replicar. Devuelve (sha, fuente) o (None, None).

  - --stash: captura los cambios sin commitear (incl. untracked) como stash
    real, lo aplica de vuelta al origen y devuelve el SHA del snapshot. Si
    el worktree está limpio pero hay stash@{0}, se usa ese (aplicándolo
    también al origen y conservando la entrada del usuario).
  - commit_arg: se valida tal cual en el repo origen.
  - default: HEAD.
  """
  if stash:
    sucio = _porcelain(origen_repo)
    if sucio:
      print(f"==> Stash temporal en el origen ({len(sucio)} cambio(s) sin commitear, untracked incluido)...")
      push = run("git", "stash", "push", "-u", "-m", "xtool replicate (temporal)", cwd=origen_repo, check=False)
      if push.returncode != 0:
        print("ERROR: falló 'git stash push -u' en el origen:")
        print((push.stderr.strip() or push.stdout.strip())[:500])
        return None, None
    sha = out("git", "rev-parse", "--verify", "-q", "stash@{0}^{commit}", cwd=origen_repo).strip()
    if not sha:
      if sucio:
        print("ERROR: no se pudo capturar el stash del origen.")
      else:
        print("ERROR: no hay cambios sin commitear ni stash@{0} en el origen.")
        print("       Pasa un <commit>, commitea primero, o deja que se use el default (HEAD).")
      return None, None
    aplicar = run("git", "stash", "apply", "stash@{0}", cwd=origen_repo, check=False)
    if aplicar.returncode != 0:
      print("ERROR: falló 'git stash apply' al origen (la entrada del stash queda intacta):")
      print((aplicar.stderr.strip() or aplicar.stdout.strip())[:500])
      return None, None
    print("==> Stash aplicado de vuelta al origen: los cambios siguen en tu worktree.")
    if sucio:
      run("git", "stash", "drop", "stash@{0}", cwd=origen_repo, check=False)
      print("==> Entrada de stash temporal eliminada (tus stashes previos no se tocan).")
      return sha, "stash del origen (aplicado también al origen)"
    print("    AVISO: tu stash@{0} se conserva; ya quedó aplicado al origen.")
    print("    Elimínala cuando confirmes que todo está bien: git stash drop")
    return sha, "stash@{0} del origen (aplicado también al origen)"

  if commit_arg:
    sha = out("git", "rev-parse", "--verify", f"{commit_arg}^{{commit}}", cwd=origen_repo).strip()
    if not sha:
      print(f"ERROR: '{commit_arg}' no es un commit de {mostrar_ruta(origen_repo)}")
      print(f"       (ni un alias conocido: {', '.join(sorted(set(ALIAS.values()) | {'all'}))})")
      return None, None
    return sha, "parámetro"

  sha = out("git", "rev-parse", "--verify", "HEAD^{commit}", cwd=origen_repo).strip()
  return (sha, "HEAD (commit actual)") if sha else (None, None)


def resolver_targets(targets, raices, origen_dir: Path, destinos):
  """Resuelve los tokens de destino en directorios concretos.

  Devuelve (pedidos, errores): pedidos = [(alias, app, destino)] sin
  duplicados y sin el origen; errores = mensajes por token sin resolución.

  Con 'destinos' en la configuración cada alias y 'all' van SIEMPRE a la
  ruta fijada (no se barre ninguna raíz). Sin 'destinos', 'all' barre los
  symfony_* de las raíces y ante ambigüedad (el app existe en varias
  raíces) se prefiere el hermano del mismo Web del origen y se avisa.
  """
  pedidos, errores = [], []
  vistos = set()

  def agregar(alias, app, destino: Path):
    if destino == origen_dir:
      return  # el origen nunca es destino de sí mismo
    clave = str(destino)
    if clave in vistos:
      return
    vistos.add(clave)
    pedidos.append((alias, app, destino))

  for t in targets:
    if t == "all":
      if destinos:
        for app in sorted(destinos):
          destino = destinos[app]
          if destino == origen_dir:
            continue
          if not destino.is_dir():
            print(f"AVISO: {app} fijado en 'destinos' no existe: {mostrar_ruta(destino)}")
            continue
          agregar(t, app, destino)
      else:
        for raiz in raices:
          if not raiz.is_dir():
            continue
          for sub in sorted(raiz.iterdir()):
            if sub.is_dir() and sub.name.startswith("symfony_"):
              agregar(t, sub.name, sub)
    else:
      app = ALIAS[t]
      if app in destinos:
        destino = destinos[app]
        if destino == origen_dir:
          errores.append(f"{t}: {app} es el directorio de origen")
          continue
        if not destino.is_dir():
          errores.append(f"{t}: {app} fijado en 'destinos' no existe: {mostrar_ruta(destino)}")
          continue
        agregar(t, app, destino)
        continue
      candidatos = [raiz / app for raiz in raices if (raiz / app).is_dir()]
      candidatos = [c for c in candidatos if c != origen_dir]
      if not candidatos:
        errores.append(f"{t}: {app} no existe en las raíces configuradas (o es el origen)")
        continue
      hermanos = [c for c in candidatos if c.parent == origen_dir.parent]
      elegido = (hermanos or candidatos)[0]
      if len(candidatos) > 1:
        print(f"AVISO: {t} ({app}) existe en varias raíces; se elige {mostrar_ruta(elegido)}:")
        for c in candidatos:
          print(f"    {mostrar_ruta(c)}")
      agregar(t, app, elegido)

  return pedidos, errores


def validar_destino(alias, app, destino: Path, no_force: bool, push: bool):
  """Valida un destino. Devuelve (plan, errores, avisos).

  Lo 'sucio' que estorba al transporte es lo que cae bajo el app destino: si
  comparte repo con el origen, los cambios sin commitear del ORIGEN (p.ej.
  los restaurados por --stash) no cuentan. Con -y además se avisa si el
  repo ya tenía algo staged: 'git-diff -y' lo incluiría en el commit.
  """
  errores, avisos = [], []
  repo, sub, rama = None, "", ""
  repo_str = out("git", "rev-parse", "--show-toplevel", cwd=destino).strip()
  if not repo_str:
    errores.append(f"no es un repo git: {mostrar_ruta(destino)}")
  else:
    repo = Path(repo_str)
    sub = subdir_relativo(destino, repo)
    rama = out("git", "branch", "--show-current", cwd=repo).strip()
    if not rama:
      errores.append(f"HEAD detached en {mostrar_ruta(repo)}")
  entradas = _porcelain(repo) if repo else []
  prefijo = (sub + "/") if sub else ""
  relevantes = [e for e in entradas if e[3:].startswith(prefijo)]
  if relevantes:
    if no_force:
      errores.append(f"destino sucio ({len(relevantes)} entrada(s) bajo {sub or '(raíz)'}): con --no-force se EXCLUYE (commitea/stashea o quita --no-force)")
    else:
      avisos.append(f"destino sucio ({len(relevantes)} entrada(s) bajo {sub or '(raíz)'}); se continúa con el forzado por defecto")
  if push and repo:
    staged_previos = [e for e in entradas if e[0] not in (" ", "?")]
    if staged_previos:
      avisos.append(f"el repo ya tiene {len(staged_previos)} cambio(s) STAGED previos: git-diff -y los incluiría en el commit")
  plan = {"alias": alias, "app": app, "destino": destino, "repo": repo, "sub": sub, "rama": rama, "sucio": len(relevantes)}
  return plan, errores, avisos


def forzar_conflictos(plan, origen_repo: Path, origen_sub: str, commit: str):
  """Resuelve los conflictos de contenido del app destino con la versión del ORIGEN.

  Solo se tocan las rutas bajo el subdirectorio destino (las creadas por
  esta replicación); conflictos preexistentes fuera de él se dejan quietos.
  """
  repo = plan["repo"]
  prefijo_d = (plan["sub"] + "/") if plan["sub"] else ""
  for status, path in conflicted_files(repo):
    if "U" not in status or not path.startswith(prefijo_d):
      continue
    rel = path[len(prefijo_d):] if prefijo_d else path
    origen_path = (origen_sub + "/" + rel) if origen_sub else rel
    if run("git", "cat-file", "-e", f"{commit}:{origen_path}", cwd=origen_repo, check=False).returncode != 0:
      print(f"    SIN FORZAR: {path} (no existe en el commit del origen).")
      continue
    escribir_blob(origen_repo, repo, commit, origen_path, path)
    print(f"    Forzado: {path} (versión del origen, staged)")


def invocar_git_diff_y(repo: Path) -> bool:
  """Ejecuta 'xtool git-diff -y' en el repo destino. True si terminó bien."""
  xtool_bin = shutil.which("xtool")
  cmd = [xtool_bin, "git-diff", "-y"] if xtool_bin else [sys.executable, "-m", "xtool.tools.git_diff", "-y"]
  sys.stdout.flush()  # para que la salida propia no se intercale con la del subprocess al redirigir
  proc = subprocess.run(cmd, cwd=str(repo), check=False)
  return proc.returncode == 0


def ejecutar(plan, origen_repo: Path, origen_sub: str, commit: str, patch_file: Path, push: bool, no_force: bool):
  """Replica el commit en un destino y (con -y) commitea y pushea. Devuelve el estado."""
  print(f"\n==> {plan['alias']} ({plan['app']}) -> {mostrar_ruta(plan['destino'])}")
  aplicar_acotado(plan["repo"], origen_repo, commit, origen_sub, plan["sub"], patch_file)
  # Untracked de un stash (viven en el 3er padre): solo aplica si el commit es un stash
  transportar_untracked_stash(
    plan["repo"], origen_repo, commit,
    mapear=mapear_por_prefijo(origen_sub, plan["sub"]),
  )

  if not no_force:
    forzar_conflictos(plan, origen_repo, origen_sub, commit)

  pendientes = [p for s, p in conflicted_files(plan["repo"]) if "U" in s]
  if pendientes:
    print("==> PENDIENTE: conflictos sin resolver (NO se commitea ni pushea):")
    for p in pendientes:
      print(f"    {p}")
    print("    Resuelve a mano con 'git add <archivo>' (o repite sin --no-force para que el origen gane).")
    return "pendiente"

  if not push:
    return "ok"

  staged = run("git", "diff", "--cached", "--quiet", cwd=plan["repo"], check=False).returncode != 0
  if not staged:
    print("==> Sin cambios aplicables en este destino; no hay nada que commitear.")
    return "sin_cambios"

  print(f"==> Commiteando y pusheando con 'xtool git-diff -y' en {mostrar_ruta(plan['repo'])}...")
  if not invocar_git_diff_y(plan["repo"]):
    print("ERROR: falló 'xtool git-diff -y' en el destino (revisa la salida de arriba).")
    return "fallo"
  return "ok"


def main(argv=None):
  argv = list(sys.argv[1:]) if argv is None else list(argv)

  if argv and argv[0] in ("-h", "--help"):
    print(__doc__)
    return 0

  if any(a in ("-f", "--force") for a in argv):
    print("AVISO: -f/--force no existe aquí: el forzado es el DEFAULT (usa --no-force para el modo conservador).")
    argv = [a for a in argv if a not in ("-f", "--force")]

  stash = "--stash" in argv
  push = "-y" in argv
  yes = "--yes" in argv
  no_force = "--no-force" in argv
  resto = [a for a in argv if a not in ("--stash", "-y", "--yes", "--no-force")]

  desconocidas = [a for a in resto if a.startswith("-")]
  if desconocidas:
    print(f"ERROR: opción desconocida: {desconocidas[0]}")
    print(USO)
    return 1

  targets, commit_arg = [], None
  for tok in resto:
    if tok in ALIAS or tok == "all":
      targets.append(tok)
    elif commit_arg is None:
      commit_arg = tok
    else:
      print(f"ERROR: solo se admite un <commit>; ya llegó '{commit_arg}' y después '{tok}'")
      return 1
  if not targets:
    print("ERROR: indica al menos un destino.")
    if commit_arg:
      print(f"       ('{commit_arg}' se interpretó como <commit>, no como destino)")
    print(f"Aliases: {' '.join(sorted(set(ALIAS.values())))} | all")
    return 1
  if stash and commit_arg:
    print("ERROR: --stash no se combina con <commit> (elige una sola fuente de cambios).")
    return 1

  # --- Origen: repo y app del directorio actual ---
  top = run("git", "rev-parse", "--show-toplevel", check=False)
  if top.returncode != 0 or not top.stdout.strip():
    print("ERROR: el directorio actual no es un repo git (ejecuta desde el app origen).")
    return 1
  origen_repo = Path(top.stdout.strip())
  origen_dir = Path.cwd().resolve()
  origen_sub = subdir_relativo(origen_dir, origen_repo)
  if not origen_sub:
    print(f"ERROR: estás en la raíz del repo ({mostrar_ruta(origen_repo)}); ejecuta desde dentro de un app")
    print("p.ej. .../Web/symfony_home, para replicar su contenido a los demás apps.")
    return 1
  rama_origen = out("git", "branch", "--show-current", cwd=origen_repo).strip() or "(detached)"
  print(f"==> Origen: {origen_sub} en {mostrar_ruta(origen_repo)} (rama: {rama_origen})")

  raices, destinos = cargar_config()
  if raices is None:
    return 1
  for raiz in raices:
    if not raiz.is_dir():
      print(f"AVISO: raíz configurada inexistente: {mostrar_ruta(raiz)}")

  # --- Commit a replicar (HEAD / <commit> / --stash) ---
  commit, fuente = resolver_commit(origen_repo, commit_arg, stash)
  if not commit:
    return 1
  oneline = out("git", "log", "-1", "--oneline", commit, cwd=origen_repo).strip()
  print(f"==> Commit a replicar: {oneline} (fuente: {fuente})")

  # --- Destinos: resolver aliases y validar ---
  pedidos, errores_res = resolver_targets(targets, raices, origen_dir, destinos)
  for e in errores_res:
    print(f"ERROR: {e}")
  if not pedidos:
    return 1

  planes, excluidos = [], []
  for alias, app, destino in pedidos:
    plan, errores, avisos = validar_destino(alias, app, destino, no_force, push)
    plan["avisos"] = avisos
    if errores:
      excluidos.append((plan, errores))
    else:
      planes.append(plan)
  if not planes:
    print("\nERROR: ningún destino pasó la validación:")
    for plan, errores in excluidos:
      print(f"  {plan['alias']} {mostrar_ruta(plan['destino'])}:")
      for e in errores:
        print(f"    {e}")
    return 1

  # --- Plan + confirmación ---
  print(f"\n==> Replicando a {len(planes)} destino(s):")
  for i, p in enumerate(planes, 1):
    rama = p["rama"] or "(detached)"
    extra = f" | SUCIO ({p['sucio']} entrada(s))" if p["sucio"] else ""
    print(f"  [{i}] {p['alias']:<4} {p['app']:<22} -> {mostrar_ruta(p['destino'])} (rama: {rama}{extra})")
    for a in p["avisos"]:
      print(f"        AVISO: {a}")
  for plan, errores in excluidos:
    print(f"  [EXCLUIDO] {plan['alias']} {mostrar_ruta(plan['destino'])}:")
    for e in errores:
      print(f"    {e}")

  if push and not yes:
    try:
      input("\nEnter para replicar y commitear+pushear cada destino con 'xtool git-diff -y' (Ctrl+C para cancelar)... ")
    except EOFError:
      print("ERROR: no hay stdin para confirmar; usa --yes (p.ej. en scripts).")
      return 1
    except KeyboardInterrupt:
      print("\nCancelado.")
      return 130

  # --- Ejecución ---
  patch_file = Path(tempfile.mkstemp(prefix="git_replicate_", suffix=".patch")[1])
  resultados = []
  try:
    for plan in planes:
      resultados.append((plan, ejecutar(plan, origen_repo, origen_sub, commit, patch_file, push, no_force)))
  finally:
    patch_file.unlink(missing_ok=True)

  # --- Resumen final ---
  print("\n==> Resumen:")
  fallos = 0
  for plan, estado in resultados:
    destino = mostrar_ruta(plan["destino"])
    if estado == "ok":
      detalle = "commit+push (git-diff -y)" if push else "staged, sin commit"
      print(f"  OK          {plan['alias']:<4} -> {destino} ({detalle})")
    elif estado == "sin_cambios":
      print(f"  SIN CAMBIOS {plan['alias']:<4} -> {destino} (nada aplicable del commit)")
    elif estado == "pendiente":
      print(f"  PENDIENTE   {plan['alias']:<4} -> {destino} (conflictos para resolver a mano; sin commit/push)")
      fallos += 1
    else:
      print(f"  FALLO       {plan['alias']:<4} -> {destino} (falló git-diff -y; revisa la salida de arriba)")
      fallos += 1
  if not push and not fallos:
    print("==> Revisa cada destino con 'git diff --cached' y commitea cuando quieras.")
  return 1 if fallos else 0


if __name__ == "__main__":
  sys.exit(main())
