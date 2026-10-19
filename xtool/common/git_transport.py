#!/usr/bin/env python3
"""Lógica de transporte de commits entre repos git locales (compartida).

Aquí viven los helpers que usan git-cherry y git-deploy: ejecución de git,
mapeo determinista de rutas origen_sub -> destino_sub (modo acotado),
escritura de blobs, marcado de conflictos y resolución modify/delete.

No debe importarse con side effects: solo funciones y constantes.
"""

import subprocess
import sys
from pathlib import Path

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

  Devuelve un resumen dict con contadores:
  {aplicados, agregados, eliminados, conflictos, atenciones, fuera}
  ('atenciones' = archivos que quedaron .desde_origen o ya existían:
  requieren revisión manual).
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
  resumen = {"aplicados": 0, "agregados": 0, "eliminados": 0, "conflictos": 0, "atenciones": 0, "fuera": fuera}

  for status, path in entradas:
    rel = path[len(origen_sub) + 1:]
    destino = prefijo_d + rel
    existe_head = run("git", "cat-file", "-e", f"HEAD:{destino}", cwd=repo_root, check=False).returncode == 0
    destino_abs = repo_root / destino

    if status == "D":
      if existe_head:
        run("git", "rm", "-q", "-f", "--", destino, cwd=repo_root)
        rmdir_vacios(destino_abs, repo_root)
        resumen["eliminados"] += 1
        print(f"    Eliminado: {path} -> {destino}")
      else:
        print(f"    Omiso (eliminado en el origen, no existía en destino): {destino}")
    elif status in ("A", "T"):
      if existe_head:
        guardar_desde_origen(origen_repo, repo_root, commit, path, destino)
        resumen["atenciones"] += 1
        print(f"    ATENCION: {path} -> {destino} ya existe en el destino.")
        print(f"      Versión del origen en {destino}.desde_origen; revísala a mano.")
      else:
        escribir_blob(origen_repo, repo_root, commit, path, destino)
        resumen["agregados"] += 1
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
        resumen["aplicados"] += 1
        print(f"    Aplicado: {path} -> {destino}")
      elif not existe_head:
        escribir_blob(origen_repo, repo_root, commit, path, destino)
        resumen["agregados"] += 1
        print(f"    Agregado (no existía en destino): {path} -> {destino}")
      elif destino_abs.exists() and es_conflicto(destino_abs):
        marcar_conflicto(repo_root, origen_repo, base, commit, path, destino)
        conflictos += 1
        print(f"    CONFLICTO de contenido: {destino} (quedó como merge conflict).")
      else:
        guardar_desde_origen(origen_repo, repo_root, commit, path, destino)
        resumen["atenciones"] += 1
        print(f"    ATENCION: {path} -> {destino} NO aplica limpio.")
        print(f"      Revisa {destino}.desde_origen y decide.")

  resumen["conflictos"] = conflictos
  if fuera:
    print(f"==> {fuera} archivo(s) del commit fuera de {origen_sub}/ fueron ignorados.")
  if conflictos:
    print(f"==> {conflictos} archivo(s) quedaron como merge conflict (sin resolver):")
    print("    Lista: git diff --name-only --diff-filter=U")
    print("    Al resolver cada uno: git add <archivo>")
  return resumen


if __name__ == "__main__":
  sys.exit("Este módulo es compartido; no se ejecuta directo (lo usan git-cherry y git-deploy).")
