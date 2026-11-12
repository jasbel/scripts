"""Actualiza este arsenal ejecutando git pull en su repositorio.

Uso:
  xtool update

Trae los cambios remotos desde cualquier directorio del sistema, sin
necesidad de navegar hasta la carpeta del repositorio.

Después del pull verifica que los ejecutables declarados en
[project.scripts] de pyproject.toml (xtool y su alias x) existan en el
PATH; si falta alguno, reinstala el comando con `uv tool install
--editable . --force` para crearlos (un `uv tool upgrade` no crea
ejecutables nuevos). Si solo cambiaron dependencias (pyproject.toml /
uv.lock) y los ejecutables están completos, sugiere `uv tool upgrade
scripts`.
"""

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


def _repo_root() -> Path:
  # <root>/xtool/tools/update.py -> <root>
  return Path(__file__).resolve().parents[2]


def _declared_scripts(root: Path) -> list[str]:
  """Nombres de los entry points en [project.scripts] de pyproject.toml."""
  try:
    with (root / "pyproject.toml").open("rb") as fh:
      data = tomllib.load(fh)
  except Exception:
    return []
  return list(data.get("project", {}).get("scripts", {}))


def _missing_executables(root: Path) -> list[str]:
  """Entry points declarados que no están disponibles en el PATH."""
  return [s for s in _declared_scripts(root) if not shutil.which(s)]


def _reinstall(root: Path) -> int:
  """Reinstala el comando global para (re)crear sus ejecutables."""
  print("Reinstalando el comando (uv tool install --editable . --force) ...")
  proc = None
  try:
    proc = subprocess.run(
      ["uv", "tool", "install", "--editable", str(root), "--force"]
    )
  except FileNotFoundError:
    pass
  if proc is None or proc.returncode != 0:
    print("No se pudo reinstalar. Ejecuta manualmente:")
    print("  uv tool install --editable . --force")
    return 1
  return 0


def main(argv=None):
  argv = sys.argv[1:] if argv is None else list(argv)
  root = _repo_root()

  rev = subprocess.run(
    ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
    capture_output=True,
    text=True,
  )
  if rev.returncode != 0:
    print(f"Error: {root} no es un repositorio git")
    return 1

  print(f"Actualizando {root} ...")
  pull = subprocess.run(
    ["git", "-C", str(root), "pull"],
    capture_output=True,
    text=True,
  )
  output = (pull.stdout + pull.stderr).strip()
  if output:
    print(output)

  if pull.returncode != 0:
    return pull.returncode

  up_to_date = "Already up to date" in output or "Ya está actualizado" in output

  # Ejecutables declarados pero ausentes en el PATH (instalación vieja o pull
  # que trajo entry points nuevos): se reinstala para crearlos. La reinstalación
  # también refresca dependencias, así que cubre el caso de pyproject/uv.lock.
  missing = _missing_executables(root)
  if missing:
    print(f"\nFaltan ejecutables declarados: {', '.join(missing)}")
    if _reinstall(root) != 0:
      return 1
  elif not up_to_date:
    changed = subprocess.run(
      ["git", "-C", str(root), "diff", "--name-only", "HEAD@{1}", "HEAD"],
      capture_output=True,
      text=True,
    )
    if changed.returncode == 0 and any(
      f in ("pyproject.toml", "uv.lock") for f in changed.stdout.split()
    ):
      print("\nCambiaron dependencias (pyproject.toml / uv.lock).")
      print("Ejecuta: uv tool upgrade scripts")

  return 0


if __name__ == "__main__":
  sys.exit(main())
