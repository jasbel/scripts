"""Actualiza este arsenal ejecutando git pull en su repositorio.

Uso:
  xtool update

Trae los cambios remotos desde cualquier directorio del sistema, sin
necesidad de navegar hasta la carpeta del repositorio. Si el pull trae
cambios en pyproject.toml o uv.lock, sugiere ejecutar `uv tool upgrade
scripts` para refrescar las dependencias del comando instalado.
"""

import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
  # <root>/xtool/tools/update.py -> <root>
  return Path(__file__).resolve().parents[2]


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

  if "Already up to date" in output or "Ya está actualizado" in output:
    return 0

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
