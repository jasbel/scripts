"""Ejecuta `npm run css` en todos los proyectos symfony_* de solocruceros.

Busca los directorios que coinciden con `symfony_*` del origen elegido y
ejecuta `npm run css` en cada uno (compila SASS vía gulp).

Orígenes:
  es  solocruceros.com (default)
  la  solocruceros_latam/solocruceros.com

Uso:
  xtool run-css                     # origen es
  xtool run-css --origin la         # origen la
  xtool run-css --base <dir>        # otro directorio base arbitrario

Al terminar muestra un resumen con los directorios donde el comando no se
pudo ejecutar (sin package.json/script css o con error de npm) y devuelve
código de salida 1 si alguno no se ejecutó.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ORIGINS = {
  "es": Path("/home/asbel/projects/symfony-sites/sites/solocruceros.com/DDD/1_Presentation/Web"),
  "la": Path("/home/asbel/projects/symfony-sites/sites/solocruceros_latam/solocruceros.com/DDD/1_Presentation/Web"),
}
DEFAULT_ORIGIN = "es"
PATTERN = "symfony_*"
TIMEOUT_SEG = 300  # por directorio


def _tiene_script_css(pkg_path: Path) -> bool:
  """True si el package.json existe y define un script `css`."""
  try:
    with pkg_path.open(encoding="utf-8") as f:
      return "css" in (json.load(f).get("scripts") or {})
  except (OSError, ValueError):
    return False


def main(argv=None):
  argv = sys.argv[1:] if argv is None else list(argv)

  base = None
  i = 0
  while i < len(argv):
    a = argv[i]
    if a in ("-h", "--help"):
      print((__doc__ or "").strip())
      return 0
    if a == "--origin":
      if i + 1 >= len(argv) or argv[i + 1] not in ORIGINS:
        validos = ", ".join(sorted(ORIGINS))
        print(f"--origin requiere uno de: {validos}")
        return 1
      base = ORIGINS[argv[i + 1]]
      i += 1
    elif a == "--base":
      if i + 1 >= len(argv):
        print("--base requiere una ruta")
        return 1
      base = Path(argv[i + 1]).expanduser()
      i += 1
    else:
      print(f"xtool run-css: argumento desconocido: {a}\n")
      print((__doc__ or "").strip())
      return 1
    i += 1

  if base is None:
    base = ORIGINS[DEFAULT_ORIGIN]

  if not shutil.which("npm"):
    print("npm no está disponible en el PATH; instala Node.js primero")
    return 1

  dirs = sorted(d for d in base.glob(PATTERN) if d.is_dir())
  if not dirs:
    print(f"No se encontraron directorios {PATTERN} en {base}")
    return 1

  print(f"Ejecutando npm run css en {len(dirs)} directorios de {base}\n")

  fallidos = []  # (nombre, motivo) — npm devolvió error o timeout
  omitidos = []  # sin package.json o sin script css

  for d in dirs:
    if not _tiene_script_css(d / "package.json"):
      print(f"--- {d.name}: sin script css, se omite\n")
      omitidos.append(d.name)
      continue
    print(f"--- {d.name}", flush=True)
    try:
      code = subprocess.call(["npm", "run", "css"], cwd=str(d), timeout=TIMEOUT_SEG)
    except subprocess.TimeoutExpired:
      code = -1
      print(f"(timeout tras {TIMEOUT_SEG}s)")
    if code != 0:
      fallidos.append((d.name, f"código {code}"))
    print()

  print("=" * 60)
  if fallidos or omitidos:
    if fallidos:
      print("✗ npm run css FALLÓ en:")
      for name, motivo in fallidos:
        print(f"    {name} ({motivo})")
    if omitidos:
      print("! No se ejecutó (sin script css):")
      for name in omitidos:
        print(f"    {name}")
    ejecutados_ok = len(dirs) - len(fallidos) - len(omitidos)
    print(f"\nResumen: {ejecutados_ok}/{len(dirs)} directorios OK")
    return 1

  print(f"✓ npm run css OK en los {len(dirs)} directorios")
  return 0


if __name__ == "__main__":
  sys.exit(main())
