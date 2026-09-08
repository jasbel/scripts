#!/usr/bin/env python3
"""Transporta un commit de otro repositorio local al repo actual, sin commitear.

Uso:
  xtool git-cherry <ruta_repo_origen> <hash_commit>

El repo destino es el del directorio actual (desde donde se ejecuta el comando).
<ruta_repo_origen> puede ser cualquier ruta DENTRO del repo origen (subdirectorio,
worktree): se resuelve a la raíz del repo. Los cambios quedan en staging sin
commitear, para revisar con 'git diff --cached'.

Qué hace:
  - Agrega un remote temporal apuntando a la raíz del repo origen.
  - Fetch mínimo por SHA del commit (si el SHA no es anunciado, fetch completo).
  - Ejecuta cherry-pick -n (sin commit).
  - En conflictos modify/delete típicos cross-repo (el archivo llegó con un
    prefijo de ruta extra), mapea la ruta al sufijo que exista en el destino
    (quitando 1..n componentes iniciales) y aplica el diff del origen.
  - Si el diff no aplica limpio, deja la versión del origen como
    <ruta>.desde_origen para revisión manual.
  - Los conflictos de contenido quedan listados para resolver a mano.
  - Siempre remueve el remote temporal y sale del estado cherry-pick
    conservando el staging.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

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
  for profundidad in range(1, len(partes)):
    sufijo = "/".join(partes[profundidad:])
    if run("git", "cat-file", "-e", f"HEAD:{sufijo}", cwd=repo_root, check=False).returncode == 0:
      return profundidad, sufijo
  return None, None


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
    diff = out("git", "diff", f"{commit}^", commit, "--", path, cwd=origen_repo)
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


def main(argv=None):
  argv = list(sys.argv[1:]) if argv is None else list(argv)

  if argv and argv[0] in ("-h", "--help"):
    print(__doc__)
    return 0
  if len(argv) != 2:
    print("Uso: xtool git-cherry <ruta_repo_origen> <hash_commit>")
    return 1
  ruta_origen, commit = argv

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
  commit_full = out("git", "rev-parse", "--verify", f"{commit}^{{commit}}", cwd=origen_repo).strip()
  if not commit_full:
    print(f"ERROR: el commit {commit} no existe en {origen_repo}")
    return 1

  patch_file = Path(tempfile.mkstemp(prefix="cherry_cross_", suffix=".patch")[1])
  try:
    # --- Remote temporal + fetch mínimo ---
    print(f"==> Agregando remote temporal: {origen_repo}")
    run("git", "remote", "remove", remote_tmp, cwd=repo_root, check=False)  # stale de corridas previas
    run("git", "remote", "add", remote_tmp, str(origen_repo), cwd=repo_root)
    if run("git", "fetch", "--quiet", remote_tmp, commit_full, cwd=repo_root, check=False).returncode != 0:
      run("git", "fetch", "--quiet", remote_tmp, cwd=repo_root)
    print(f"==> Commit a aplicar: {out('git', 'log', '-1', '--oneline', commit_full, cwd=origen_repo).strip()}")

    # --- Cherry-pick sin commit (-n = --no-commit) ---
    cp = run("git", "cherry-pick", "-n", commit_full, cwd=repo_root, check=False)
    if cp.returncode == 0:
      print("==> Cherry-pick aplicado limpio (sin commitear).")
    else:
      print("==> Conflictos detectados. Resolviendo modify/delete por prefijo de ruta...")
      resolver_conflictos(repo_root, origen_repo, commit_full, patch_file)
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
