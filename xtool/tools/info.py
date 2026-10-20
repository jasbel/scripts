"""Muestra información del arsenal xtool: rutas, ejecutable en uso y PATH.

Uso:
  xtool info

Qué muestra:
  - Ruta del proyecto (este arsenal), versión y rama git.
  - Qué ejecutable xtool está en uso (venv local o instalación global de uv).
  - Si ~/.local/bin está en el PATH y cómo agregarlo si falta.
  - Entorno: Python, .env y cantidad de comandos disponibles.
"""

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GLOBAL_BIN = (Path.home() / ".local" / "bin").resolve()


def _version():
  try:
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]
  except Exception:
    return "?"


def _clasificar(exe: Path) -> str:
  """Describe el origen del ejecutable xtool en uso."""
  real = exe.resolve()
  if real == Path(__file__).resolve():
    return "módulo directo (python -m)"
  if real.is_relative_to(PROJECT_ROOT / ".venv"):
    return "venv del proyecto (uv run o activado)"
  uv_tools = Path.home() / ".local" / "share" / "uv" / "tools"
  if real.is_relative_to(uv_tools):
    return "instalación global editable (uv tool install --editable .)"
  return "instalación externa"


def _global_bin_en_path() -> bool:
  entries = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
  return any(Path(p).resolve() == GLOBAL_BIN for p in entries)


def _rama() -> str:
  try:
    r = subprocess.run(
      ["git", "-C", str(PROJECT_ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
      capture_output=True, text=True, timeout=5,
    )
    return r.stdout.strip() if r.returncode == 0 else "?"
  except Exception:
    return "?"


def main(argv=None):
  argv = sys.argv[1:] if argv is None else list(argv)

  if argv:
    print(__doc__.strip())
    return 1

  exe_crudo = Path(sys.argv[0]) if sys.argv[0] else None
  exe = exe_crudo.expanduser().absolute() if exe_crudo else None
  tipo = _clasificar(exe) if exe else "?"
  which = shutil.which("xtool")
  tools_dir = PROJECT_ROOT / "xtool" / "tools"
  n_tools = len([p for p in tools_dir.glob("*.py") if p.name != "__init__.py"])

  print("xtool — Arsenal de herramientas globales")
  print()
  print("Proyecto:")
  print(f"  Ruta:       {PROJECT_ROOT}")
  print(f"  Versión:    {_version()}  (rama: {_rama()})")
  print(f"  Comandos:   {n_tools}  (en xtool/tools/)")
  print()
  print("Ejecutable:")
  if exe:
    print(f"  En uso:     {exe}")
    print(f"  Origen:     {tipo}")
    if tipo.startswith("instalación global"):
      print("  Actualizar: uv tool upgrade scripts  (tras cambiar dependencias)")
  if which:
    print(f"  En el PATH: {which}")
  print()
  print("PATH:")
  if _global_bin_en_path():
    print(f"  ✓ {GLOBAL_BIN} está en el PATH → xtool disponible en cualquier terminal")
  else:
    print(f"  ✗ {GLOBAL_BIN} NO está en el PATH. Para agregarlo:")
    print('      echo \'export PATH="$HOME/.local/bin:$PATH"\' >> ~/.bashrc && source ~/.bashrc')
  print()
  print("Entorno:")
  print(f"  Python:     {sys.version.split()[0]}  ({sys.prefix})")
  env_file = PROJECT_ROOT / ".env"
  print(f"  .env:       {'presente (valores ocultos)' if env_file.exists() else 'no existe'}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
