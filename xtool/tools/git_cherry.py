#!/usr/bin/env python3
"""Transporta un commit de otro repositorio local al repo actual, sin commitear.

Uso:
  xtool git-cherry [ruta_repo_origen] [hash_commit]

El repo destino es el del directorio actual (desde donde se ejecuta el comando).

Argumentos opcionales:
  - ruta_repo_origen: si no se envía, se toma del origen por defecto, con esta
    prioridad: override temporal de 'xtool git-cherry-origin' (vigente) >
    variable de entorno GIT_CHERRY_ORIGEN (también puede vivir en un .env).
    Puede ser cualquier ruta DENTRO del repo origen (subdirectorio,
    worktree): se resuelve a la raíz del repo.
  - hash_commit: si no se envía, se toma del origen en este orden:
      1. stash@{0} del repo origen (si hay stash). Los untracked guardados
         con 'git stash -u' también se transportan (viven en el 3er padre).
      2. Los cambios sin commitear del origen (se crea un commit temporal con
         'git stash create', que NO modifica el repo origen). Los untracked
         del worktree no se transportan (el tool avisa cuáles son).
      3. Si no hay nada: error "no hay información de cambios".
    También acepta revs tipo 'stash@{2}' pasada como hash_commit.

Los cambios quedan en staging sin commitear, para revisar con 'git diff --cached'.

Modo acotado (default cuando la ruta origen es un SUBDIRECTORIO del repo
origen, p.ej. .../Web/symfony_home):
  - Solo se transportan los cambios bajo ese subdirectorio.
  - Se mapean de forma determinista al subdirectorio del repo destino donde
    se ejecuta el comando (p.ej. .../Web/symfony_chile):
        <origen_sub>/ruta  ->  <destino_sub>/ruta
  - Los archivos fuera del subdirectorio origen se ignoran (se informa el total).
  - Se aplica con 'git apply -3' archivo por archivo (sin detección de
    renombres): git no puede "adivinar" apps parecidas del monorepo y esparcir
    cambios en sitios no deseados.
  - Si un diff no aplica limpio: si el archivo no existe en el destino se
    agrega completo; si queda con marcadores de conflicto se marca como merge
    conflict (unmerged, visible en 'git status' y con
    'git diff --diff-filter=U') para resolver a mano; si no, la versión del
    origen queda como <ruta>.desde_origen para revisión manual.

Modo repo completo (la ruta origen ES la raíz del repo origen):
  - Agrega un remote temporal apuntando a la raíz del repo origen.
  - Fetch mínimo por SHA del commit (si el SHA no es anunciado, fetch completo).
  - Ejecuta cherry-pick -n -Xno-renames (sin commit; con -m 1 si es un commit
    de stash). Sin renombres, git no puede reubicar cambios por similitud
    con archivos de otras apps.
  - En conflictos modify/delete típicos cross-repo (el archivo llegó con un
    prefijo de ruta extra), mapea la ruta al sufijo que exista en el destino
    (quitando 1..n componentes iniciales) y aplica el diff del origen.
  - Si el diff no aplica limpio, deja la versión del origen como
    <ruta>.desde_origen para revisión manual.
  - Los conflictos de contenido quedan listados para resolver a mano.
  - Siempre remueve el remote temporal y sale del estado cherry-pick
    conservando el staging.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from xtool.common.git_cherry_state import leer_override, minutos_restantes
from xtool.env_local import load_env

load_env()

ENV_ORIGEN = "GIT_CHERRY_ORIGEN"

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

CONFLICT_MODIFY_DELETE = {"DU", "UD", "DD", "AU", "UA"}
CONFLICT_CONTENT = {"UU", "AA"}


def run(*args, cwd=None, check=True):
  """Ejecuta un comando git (con salida capturada) y devuelve el resultado."""
  result = subprocess.run(
    args,
    cwd=cwd,
    check=False,
    text=True,
    capture_output=True,
  )
  if check and result.returncode != 0:
    sys.exit(f"ERROR ejecutando: {' '.join(args)}\n{result.stderr.strip()}")
  return result


def out(*args, **kwargs):
  return run(*args, check=False, **kwargs).stdout


def conflicted_files(repo_root: Path):
  """Devuelve [(status, ruta)] de los archivos en conflicto usando porcelain -z."""
  raw = out("git", "status", "--porcelain=v1", "-z", cwd=repo_root)
  entries = [e for e in raw.split("\0") if e]
  results = []
  i = 0
  while i < len(entries):
    entry = entries[i]
    status, path = entry[:2], entry[3:]
    # En renames (R/C) el formato es: XY nuevo \0 viejo \0
    if status[0] in "RC" and i + 1 < len(entries):
      i += 1
    results.append((status, path))
    i += 1
  return results


def rmdir_vacios(ruta: Path, repo_root: Path):
  """Elimina directorios vacíos hacia arriba, sin pasar del root del repo."""
  actual = ruta.parent
  while actual != repo_root and actual.is_dir():
    try:
      actual.rmdir()
    except OSError:
      break
    actual = actual.parent


def mapear_sufijo(repo_root: Path, path: str):
  """Busca el sufijo de 'path' (quitando 1..n componentes iniciales) que exista en HEAD del destino.

  Devuelve (profundidad, sufijo) o (None, None) si no hay coincidencia.
  """
  partes = path.split("/")
  for profundidad in range(0, len(partes)):
    sufijo = "/".join(partes[profundidad:])
    if run("git", "cat-file", "-e", f"HEAD:{sufijo}", cwd=repo_root, check=False).returncode == 0:
      return profundidad, sufijo
  return None, None


def mapear_sufijo_dir(repo_root: Path, path: str):
  """Como mapear_sufijo pero para archivos NUEVOS: matchea por directorio padre.

  Busca el sufijo cuyo directorio padre exista en HEAD del destino (el archivo
  en sí no existe todavía). Devuelve (profundidad, sufijo) o (None, None).
  """
  partes = path.split("/")
  for profundidad in range(0, len(partes)):
    sufijo = "/".join(partes[profundidad:])
    padre = sufijo.rsplit("/", 1)[0] if "/" in sufijo else None
    if padre is None or run("git", "cat-file", "-e", f"HEAD:{padre}", cwd=repo_root, check=False).returncode == 0:
      return profundidad, sufijo
  return None, None


def subdir_relativo(ruta: Path, repo_root: Path) -> str:
  """Subdirectorio de 'ruta' respecto a repo_root ('' si es la raíz del repo)."""
  try:
    sub = ruta.resolve().relative_to(repo_root)
  except ValueError:
    return ""
  return "" if str(sub) == "." else str(sub)


def bytes_blob(origen_repo: Path, rev: str, path: str) -> bytes:
  """Contenido (bytes) de un archivo en una revisión del repo origen."""
  return subprocess.run(
    ("git", "show", f"{rev}:{path}"),
    cwd=origen_repo, check=False, capture_output=True,
  ).stdout


def escribir_blob(origen_repo: Path, repo_root: Path, rev: str, path: str, destino: str):
  """Escribe el blob 'rev:path' del origen en 'destino' (relativo al repo destino) y lo agrega a staging."""
  destino_abs = repo_root / destino
  destino_abs.parent.mkdir(parents=True, exist_ok=True)
  destino_abs.write_bytes(bytes_blob(origen_repo, rev, path))
  run("git", "add", "--", destino, cwd=repo_root)


def guardar_desde_origen(origen_repo: Path, repo_root: Path, rev: str, path: str, destino: str):
  """Deja la versión del origen como <destino>.desde_origen para revisión manual."""
  (repo_root / f"{destino}.desde_origen").write_bytes(bytes_blob(origen_repo, rev, path))


def es_conflicto(archivo: Path) -> bool:
  """True si el archivo quedó con marcadores de conflicto (<<<<<<< / >>>>>>>)."""
  try:
    contenido = archivo.read_text(errors="replace")
  except OSError:
    return False
  return "<<<<<<<" in contenido and ">>>>>>>" in contenido


def entrada_indice(cwd: Path, rev: str, ruta: str, stage: int):
  """Línea 'modo sha stage' para 'update-index --index-info', o None si no existe en rev."""
  raw = out("git", "ls-tree", "-z", rev, "--", ruta, cwd=cwd)
  entrada = raw.split("\0")[0] if raw else ""
  if not entrada:
    return None
  meta = entrada.split("\t", 1)[0]
  partes = meta.split()
  if len(partes) != 3:
    return None
  modo, _, sha = partes
  return f"{modo} {sha} {stage}"


def marcar_conflicto(repo_root: Path, origen_repo: Path, base: str, commit: str, path: str, destino: str):
  """Deja 'destino' en estado unmerged (merge conflict UU) con stages base/ours/theirs.

  Así 'git status' lo muestra como conflicto, se ve con
  'git diff --name-only --diff-filter=U' y se resuelve con
  'git checkout --ours/--theirs' o editando + 'git add'.
  """
  stages = [
    entrada_indice(origen_repo, base, path, 1),
    entrada_indice(repo_root, "HEAD", destino, 2),
    entrada_indice(origen_repo, commit, path, 3),
  ]
  info = "".join(f"{s}\t{destino}\n" for s in stages if s)
  subprocess.run(
    ("git", "update-index", "--index-info"),
    cwd=repo_root, input=info, text=True, check=False, capture_output=True,
  )


def mapear_por_prefijo(origen_sub: str, destino_sub: str):
  """Devuelve un mapeo determinista path_origen -> path_destino por prefijo.

  Los path fuera de <origen_sub>/ mapean a None (fuera del alcance).
  """
  prefijo_o = origen_sub + "/"
  prefijo_d = (destino_sub + "/") if destino_sub else ""

  def mapear(path: str):
    if not path.startswith(prefijo_o):
      return None
    return prefijo_d + path[len(prefijo_o):]

  return mapear


def transportar_untracked_stash(repo_root: Path, origen_repo: Path, commit: str, mapear=None):
  """Transporta los archivos untracked de un stash -u (viven en el 3er padre del commit de stash).

  Si se pasa 'mapear' (callable path -> destino o None), se usa ese mapeo;
  si no, el mapeo heurístico por sufijo de directorio.
  """
  if run("git", "rev-parse", "--verify", "-q", f"{commit}^3", cwd=origen_repo, check=False).returncode != 0:
    return
  archivos = [l for l in out("git", "ls-tree", "-r", "--name-only", f"{commit}^3", cwd=origen_repo).splitlines() if l]
  if not archivos:
    return
  print("==> Archivos untracked del stash:")
  for path in archivos:
    if mapear is not None:
      destino = mapear(path)
      if destino is None:
        print(f"    FUERA DEL ALCANCE: {path} (ignorado)")
        continue
    else:
      _, destino = mapear_sufijo_dir(repo_root, path)
      if destino is None:
        print(f"    SIN TRANSPORTAR: {path} (no se encuentra su directorio en el destino). Revísalo a mano.")
        continue
    if run("git", "cat-file", "-e", f"HEAD:{destino}", cwd=repo_root, check=False).returncode == 0:
      print(f"    SIN TRANSPORTAR: {path} -> {destino} ya existe en el destino. Revísalo a mano.")
      continue
    destino_abs = repo_root / destino
    destino_abs.parent.mkdir(parents=True, exist_ok=True)
    destino_abs.write_bytes(bytes_blob(origen_repo, f"{commit}^3", path))
    run("git", "add", "--", destino, cwd=repo_root)
    print(f"    Agregado: {path} -> {destino}")


def resolver_conflictos(repo_root: Path, origen_repo: Path, commit: str, patch_file: Path):
  for status, path in conflicted_files(repo_root):
    if status not in CONFLICT_MODIFY_DELETE:
      continue
    # Conflicto típico cross-repo: git dejó el archivo en la ruta del origen
    # (con prefijo extra). Se mapea al sufijo que exista en el destino.
    profundidad, sin_prefijo = mapear_sufijo(repo_root, path)
    if sin_prefijo is None:
      print(f"    SIN RESOLVER: {path} (ningún sufijo existe en el destino). Revísalo a mano.")
      continue

    run("git", "rm", "-f", "-q", "--", path, cwd=repo_root)
    rmdir_vacios(repo_root / path, repo_root)

    # Diff del archivo entre el commit y su padre, en el repo origen
    diff = out("git", "diff", f"{commit}^1", commit, "--", path, cwd=origen_repo)
    patch_file.write_text(diff)
    apply = run("git", "apply", f"-p{profundidad + 1}", str(patch_file), cwd=repo_root, check=False)
    if apply.returncode == 0:
      run("git", "add", "--", sin_prefijo, cwd=repo_root)
      print(f"    Resuelto: {path} -> {sin_prefijo} (diff aplicado)")
    else:
      # No aplica limpio (ej. artefacto compilado con formato distinto).
      version_origen = out("git", "show", f"{commit}:{path}", cwd=origen_repo)
      destino_revision = repo_root / f"{sin_prefijo}.desde_origen"
      destino_revision.write_text(version_origen)
      print(f"    ATENCION: {path} -> {sin_prefijo} NO aplica limpio.")
      print(f"      Revisa {destino_revision.name} y decide (si es compilado, regenera con tu build).")

  # Conflictos de contenido clásicos: quedan para resolver a mano
  pendientes = [
    p for s, p in conflicted_files(repo_root)
    if s in CONFLICT_CONTENT or "U" in s
  ]
  if pendientes:
    print("==> Conflictos de contenido sin resolver:")
    for p in pendientes:
      print(f"    {p}")


def aplicar_acotado(repo_root: Path, origen_repo: Path, commit: str, origen_sub: str, destino_sub: str, patch_file: Path):
  """Aplica SOLO los cambios bajo origen_sub, mapeándolos bajo destino_sub de forma determinista.

  <origen_sub>/ruta/archivo  ->  <destino_sub>/ruta/archivo

  Sin cherry-pick (sin detección de renombres): nada puede salir del
  subdirectorio destino. Archivo por archivo con 'git apply -3'.
  """
  print("==> Modo acotado al subdirectorio:")
  print(f"    origen : {origen_sub}/")
  print(f"    destino: {destino_sub + '/' if destino_sub else '(raíz del repo destino)'}")

  base = f"{commit}^1"
  if run("git", "rev-parse", "--verify", "-q", f"{commit}^1", cwd=origen_repo, check=False).returncode != 0:
    base = EMPTY_TREE

  prefijo_d = (destino_sub + "/") if destino_sub else ""
  strip_n = len(origen_sub.split("/")) + 1  # componentes del prefijo + el "a/" del patch

  raw = out("git", "diff", "--name-status", "-z", "--no-renames", base, commit, "--", origen_sub, cwd=origen_repo)
  tokens = [t for t in raw.split("\0") if t]
  entradas = [(tokens[i], tokens[i + 1]) for i in range(0, len(tokens) - 1, 2)]

  total = len([l for l in out("git", "diff", "--name-only", "--no-renames", base, commit, cwd=origen_repo).splitlines() if l])
  fuera = total - len(entradas)
  conflictos = 0

  for status, path in entradas:
    rel = path[len(origen_sub) + 1:]
    destino = prefijo_d + rel
    existe_head = run("git", "cat-file", "-e", f"HEAD:{destino}", cwd=repo_root, check=False).returncode == 0
    destino_abs = repo_root / destino

    if status == "D":
      if existe_head:
        run("git", "rm", "-q", "-f", "--", destino, cwd=repo_root)
        rmdir_vacios(destino_abs, repo_root)
        print(f"    Eliminado: {path} -> {destino}")
      else:
        print(f"    Omiso (eliminado en el origen, no existía en destino): {destino}")
    elif status in ("A", "T"):
      if existe_head:
        guardar_desde_origen(origen_repo, repo_root, commit, path, destino)
        print(f"    ATENCION: {path} -> {destino} ya existe en el destino.")
        print(f"      Versión del origen en {destino}.desde_origen; revísala a mano.")
      else:
        escribir_blob(origen_repo, repo_root, commit, path, destino)
        print(f"    Agregado: {path} -> {destino}")
    else:  # M
      diff = out("git", "diff", "--binary", base, commit, "--", path, cwd=origen_repo)
      patch_file.write_text(diff)
      args = ["git", "apply", "-3", f"-p{strip_n}"]
      if destino_sub:
        args.append(f"--directory={destino_sub}")
      args.append(str(patch_file))
      if run(*args, cwd=repo_root, check=False).returncode == 0:
        run("git", "add", "--", destino, cwd=repo_root)
        print(f"    Aplicado: {path} -> {destino}")
      elif not existe_head:
        escribir_blob(origen_repo, repo_root, commit, path, destino)
        print(f"    Agregado (no existía en destino): {path} -> {destino}")
      elif destino_abs.exists() and es_conflicto(destino_abs):
        marcar_conflicto(repo_root, origen_repo, base, commit, path, destino)
        conflictos += 1
        print(f"    CONFLICTO de contenido: {destino} (quedó como merge conflict).")
      else:
        guardar_desde_origen(origen_repo, repo_root, commit, path, destino)
        print(f"    ATENCION: {path} -> {destino} NO aplica limpio.")
        print(f"      Revisa {destino}.desde_origen y decide.")

  if fuera:
    print(f"==> {fuera} archivo(s) del commit fuera de {origen_sub}/ fueron ignorados.")
  if conflictos:
    print(f"==> {conflictos} archivo(s) quedaron como merge conflict (sin resolver):")
    print("    Lista: git diff --name-only --diff-filter=U")
    print("    Al resolver cada uno: git add <archivo>")


def resolver_commit(origen_repo: Path, commit_arg):
  """Resuelve el commit a transportar.

  Si viene por parámetro se verifica tal cual; si no: stash@{0} del origen y,
  como último recurso, un commit temporal con los cambios sin commitear
  ('git stash create', no modifica el repo origen).

  Devuelve (sha_completo, descripcion_fuente) o (None, None).
  """
  if commit_arg:
    sha = out("git", "rev-parse", "--verify", f"{commit_arg}^{{commit}}", cwd=origen_repo).strip()
    return (sha, "parámetro") if sha else (None, None)

  sha = out("git", "rev-parse", "--verify", "-q", "stash@{0}^{commit}", cwd=origen_repo).strip()
  if sha:
    return sha, "stash@{0} del origen"

  creado = out("git", "stash", "create", "xtool git-cherry (temporal)", cwd=origen_repo).strip()
  if creado:
    return creado, "cambios sin commitear del origen (commit temporal)"

  return None, None


def main(argv=None):
  argv = list(sys.argv[1:]) if argv is None else list(argv)

  if argv and argv[0] in ("-h", "--help"):
    print(__doc__)
    return 0
  if len(argv) > 2:
    print(f"Uso: xtool git-cherry [ruta_repo_origen] [hash_commit]")
    return 1

  env_origen = os.environ.get(ENV_ORIGEN, "").strip() or None

  # Override temporal (xtool git-cherry-origin): vigente gana a la env (un
  # argumento explícito sigue ganando a ambos). Si expiró, leer_override ya
  # borró el archivo: se avisa una vez y se vuelve al valor de la env/.env.
  override, override_expirado = leer_override()
  if override:
    env_origen = override["origen"]
    print(f"==> Origen temporal activo (faltan {minutos_restantes(override)} min): {override['origen']}")
  elif override_expirado:
    print(
      f"==> Override de origen expirado ({override_expirado['minutos']} min); "
      f"volviendo a {ENV_ORIGEN}: {override_expirado.get('original') or '(ninguno)'}"
    )

  # Parseo flexible: [origen] [commit]. Un único argumento se interpreta como
  # commit si no es un directorio existente (y hay origen por env), o como
  # origen en caso contrario.
  if len(argv) == 2:
    ruta_origen, commit_arg = argv
  elif len(argv) == 1 and Path(argv[0]).is_dir():
    ruta_origen, commit_arg = argv[0], None
  elif len(argv) == 1 and env_origen:
    ruta_origen, commit_arg = env_origen, argv[0]
  elif len(argv) == 1:
    print(f"ERROR: falta el origen: pasa la ruta como argumento o define {ENV_ORIGEN}")
    return 1
  elif env_origen:
    ruta_origen, commit_arg = env_origen, None
  else:
    print(f"ERROR: falta la ruta del repo origen: pásala como argumento o define {ENV_ORIGEN} (entorno o .env)")
    return 1

  origen = Path(ruta_origen).resolve()
  if not origen.is_dir():
    print(f"ERROR: '{origen}' no existe o no es un directorio")
    return 1

  destino = run("git", "rev-parse", "--show-toplevel", check=False)
  if destino.returncode != 0 or not destino.stdout.strip():
    print("ERROR: el directorio actual no es un repo git (destino).")
    return 1
  repo_root = Path(destino.stdout.strip())
  remote_tmp = "tmp_cherry_cross_xtool"

  # --- Validaciones ---
  if out("git", "status", "--porcelain", cwd=repo_root).strip():
    print("ERROR: el repo destino tiene cambios sin commitear. Haz stash o commit primero.")
    return 1
  # La ruta origen puede ser un subdirectorio: se resuelve a la raíz de su repo
  origen_repo_str = out("git", "rev-parse", "--show-toplevel", cwd=origen).strip()
  if not origen_repo_str:
    print(f"ERROR: '{origen}' no está dentro de un repo git")
    return 1
  origen_repo = Path(origen_repo_str)
  origen_sub = subdir_relativo(origen, origen_repo)
  destino_sub = subdir_relativo(Path.cwd(), repo_root)

  commit_full, fuente = resolver_commit(origen_repo, commit_arg)
  if not commit_full:
    if commit_arg:
      print(f"ERROR: el commit {commit_arg} no existe en {origen_repo}")
    else:
      print(f"ERROR: no hay información de cambios: el origen no tiene stash ni cambios sin commitear.")
    return 1

  if fuente == "cambios sin commitear del origen (commit temporal)":
    untracked = [l[3:] for l in out("git", "status", "--porcelain", cwd=origen_repo).splitlines() if l.startswith("??")]
    if origen_sub:
      dentro = [u for u in untracked if u.startswith(origen_sub + "/")]
      fuera = [u for u in untracked if not u.startswith(origen_sub + "/")]
    else:
      dentro, fuera = untracked, []
    if dentro:
      print("AVISO: estos archivos untracked del origen NO se transportan:")
      for u in dentro:
        print(f"    {u}")
    if fuera:
      print(f"AVISO: {len(fuera)} untracked del origen fuera de {origen_sub}/ serán ignorados.")

  # Los commits de stash tienen 2+ padres: cherry-pick necesita -m 1
  es_stash = run("git", "rev-parse", "--verify", "-q", f"{commit_full}^2", cwd=origen_repo, check=False).returncode == 0
  # -Xno-renames: sin detección de renombres, git no puede reubicar cambios
  # por similitud en archivos de otras apps del monorepo destino
  cp_args = ["cherry-pick", "-n", "-Xno-renames"] + (["-m", "1"] if es_stash else []) + [commit_full]

  patch_file = Path(tempfile.mkstemp(prefix="cherry_cross_", suffix=".patch")[1])
  try:
    # --- Remote temporal + fetch mínimo ---
    print(f"==> Agregando remote temporal: {origen_repo}")
    run("git", "remote", "remove", remote_tmp, cwd=repo_root, check=False)  # stale de corridas previas
    run("git", "remote", "add", remote_tmp, str(origen_repo), cwd=repo_root)
    if run("git", "fetch", "--quiet", remote_tmp, commit_full, cwd=repo_root, check=False).returncode != 0:
      run("git", "fetch", "--quiet", remote_tmp, cwd=repo_root)
    oneliner = out("git", "log", "-1", "--oneline", commit_full, cwd=origen_repo).strip()
    print(f"==> Commit a aplicar: {oneliner} (fuente: {fuente})")

    if origen_sub:
      # Modo acotado: transporte determinista subdir_origen -> subdir_destino
      aplicar_acotado(repo_root, origen_repo, commit_full, origen_sub, destino_sub, patch_file)
    else:
      # --- Cherry-pick sin commit (-n = --no-commit) ---
      cp = run("git", *cp_args, cwd=repo_root, check=False)
      if cp.returncode == 0:
        print("==> Cherry-pick aplicado limpio (sin commitear).")
      else:
        print("==> Conflictos detectados. Resolviendo modify/delete por prefijo de ruta...")
        resolver_conflictos(repo_root, origen_repo, commit_full, patch_file)
    # Untracked de un stash -u: viven en el 3er padre, cherry-pick no los trae
    mapear = mapear_por_prefijo(origen_sub, destino_sub) if origen_sub else None
    transportar_untracked_stash(repo_root, origen_repo, commit_full, mapear=mapear)
  finally:
    # --- Salir del estado cherry-pick conservando los cambios staged ---
    run("git", "cherry-pick", "--quit", cwd=repo_root, check=False)
    run("git", "remote", "remove", remote_tmp, cwd=repo_root, check=False)
    patch_file.unlink(missing_ok=True)

  print("==> Listo. Cambios aplicados en staging SIN commitear:")
  print(out("git", "status", "--short", cwd=repo_root).rstrip())
  print("==> Revisa con 'git diff --cached' y commitea cuando quieras.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
