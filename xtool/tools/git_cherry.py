#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""cherry-pick-cross.py — Transporta un commit de otro repositorio local SIN commitear.

Uso:
    uv run cherry-pick-cross.py <ruta_repo_origen> <hash_commit>
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

CONFLICT_MODIFY_DELETE = {"DU", "UD", "DD", "AU", "UA"}
CONFLICT_CONTENT = {"UU", "AA"}


def run(*args, cwd=None, check=True, capture=False):
    """Ejecuta un comando git y devuelve stdout (o None si capture=False)."""
    result = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=capture,
    )
    if check and result.returncode != 0:
        sys.exit(f"ERROR ejecutando: {' '.join(args)}\n{result.stderr.strip()}")
    return result


def out(*args, **kwargs):
    return run(*args, capture=True, check=False, **kwargs).stdout


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


def resolver_conflictos(repo_root: Path, origen: Path, commit: str, patch_file: Path):
    for status, path in conflicted_files(repo_root):
        if status not in CONFLICT_MODIFY_DELETE:
            continue
        # Conflicto típico cross-repo: git dejó el archivo en la ruta del origen
        # (con prefijo extra). Se intenta mapear quitando el primer componente.
        partes = path.split("/", 1)
        if len(partes) < 2:
            print(f"    SIN RESOLVER: {path} (sin prefijo que quitar). Revísalo a mano.")
            continue
        sin_prefijo = partes[1]
        if run("git", "cat-file", "-e", f"HEAD:{sin_prefijo}", cwd=repo_root, check=False).returncode != 0:
            print(f"    SIN RESOLVER: {path} (no existe {sin_prefijo} en el destino). Revísalo a mano.")
            continue

        run("git", "rm", "-f", "-q", "--", path, cwd=repo_root)
        rmdir_vacios(repo_root / path, repo_root)

        # Diff del archivo entre el commit y su padre, en el repo origen
        diff = out("git", "diff", f"{commit}^", commit, "--", path, cwd=origen)
        patch_file.write_text(diff)
        apply = run("git", "apply", "-p2", str(patch_file), cwd=repo_root, check=False)
        if apply.returncode == 0:
            run("git", "add", "--", sin_prefijo, cwd=repo_root)
            print(f"    Resuelto: {path} -> {sin_prefijo} (diff aplicado)")
        else:
            # No aplica limpio (ej. artefacto compilado con formato distinto).
            version_origen = out("git", "show", f"{commit}:{path}", cwd=origen)
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


def main():
    parser = argparse.ArgumentParser(
        description="Cherry-pick cross-repo sin commitear (resuelve conflictos modify/delete por prefijo de ruta)."
    )
    parser.add_argument("origen", help="Ruta del repositorio origen")
    parser.add_argument("commit", help="Hash del commit a transportar")
    args = parser.parse_args()

    origen = Path(args.origen).resolve()
    commit = args.commit
    repo_root = Path(out("git", "rev-parse", "--show-toplevel").strip())
    remote_tmp = "tmp_cherry_cross_py"

    # --- Validaciones ---
    if out("git", "status", "--porcelain", cwd=repo_root).strip():
        sys.exit("ERROR: el repo destino tiene cambios sin commitear. Haz stash o commit primero.")
    if not out("git", "rev-parse", "--show-toplevel", cwd=origen).strip():
        sys.exit(f"ERROR: '{origen}' no es un repo git")
    if run("git", "cat-file", "-e", f"{commit}^{{commit}}", cwd=origen, check=False).returncode != 0:
        sys.exit(f"ERROR: el commit {commit} no existe en {origen}")

    patch_file = Path(tempfile.mkstemp(prefix="cherry_cross_", suffix=".patch")[1])
    try:
        # --- Remote temporal + fetch ---
        print(f"==> Agregando remote temporal: {origen}")
        run("git", "remote", "add", remote_tmp, str(origen), cwd=repo_root)
        run("git", "fetch", "--quiet", remote_tmp, cwd=repo_root)
        print(f"==> Commit a aplicar: {out('git', 'log', '-1', '--oneline', commit, cwd=origen).strip()}")

        # --- Cherry-pick sin commit (-n = --no-commit) ---
        cp = run("git", "cherry-pick", "-n", commit, cwd=repo_root, check=False, capture=True)
        if cp.returncode == 0:
            print("==> Cherry-pick aplicado limpio (sin commitear).")
        else:
            print("==> Conflictos detectados. Resolviendo modify/delete por prefijo de ruta...")
            resolver_conflictos(repo_root, origen, commit, patch_file)
    finally:
        # --- Salir del estado cherry-pick conservando los cambios staged ---
        run("git", "cherry-pick", "--quit", cwd=repo_root, check=False)
        run("git", "remote", "remove", remote_tmp, cwd=repo_root, check=False)
        patch_file.unlink(missing_ok=True)

    print("==> Listo. Cambios aplicados en staging SIN commitear:")
    print(out("git", "status", "--short", cwd=repo_root).rstrip())
    print("==> Revisa con 'git diff --cached' y commitea cuando quieras.")


if __name__ == "__main__":
    main()
