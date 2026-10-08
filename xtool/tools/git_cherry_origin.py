#!/usr/bin/env python3
"""Cambia temporalmente el origen por defecto de xtool git-cherry.

Uso:
  xtool git-cherry-origin <ruta_origen> [--min N]   # activa el override
  xtool git-cherry-origin                           # muestra el estado
  xtool git-cherry-origin --reset                   # cancela ya

Durante N minutos (default 30) <ruta_origen> pasa a ser el origen por
defecto de git-cherry, por encima de GIT_CHERRY_ORIGEN (que nunca se
modifica: se conserva como valor original al que se vuelve al expirar).
Puede ser cualquier subdirectorio del repo origen (modo acotado).

El vencimiento es perezoso: no hay proceso de fondo. Al expirar,
git-cherry vuelve solo al valor original (entorno o .env) aunque la
máquina se haya apagado entremedias. El override es GLOBAL: afecta a
git-cherry ejecutado desde cualquier directorio.

Ejemplo:
  xtool git-cherry-origin \
    ~/projects/symfony-sites/sites/solocruceros_latam/solocruceros.com/DDD/1_Presentation/Web/symfony_colombia
  xtool git-cherry-origin ~/.../symfony_mexico --min 60
"""

import subprocess
import sys
from pathlib import Path

from xtool.common import git_cherry_state as estado


def _parsear(argv):
  """Parsea argv. Devuelve (ruta, minutos, error)."""
  ruta = None
  minutos = 30

  def _min_valor(valor):
    try:
      n = int(valor)
    except ValueError:
      return None, f"--min debe ser un entero, recibí: {valor}"
    if n <= 0:
      return None, f"--min debe ser >= 1, recibí: {n}"
    return n, None

  i = 0
  while i < len(argv):
    arg = argv[i]
    if arg == "--min":
      if i + 1 >= len(argv):
        return None, None, "--min requiere un número de minutos (ej. --min 60)"
      minutos, err = _min_valor(argv[i + 1])
      if err:
        return None, None, err
      i += 1
    elif arg.startswith("--min="):
      minutos, err = _min_valor(arg.split("=", 1)[1])
      if err:
        return None, None, err
    elif arg.startswith("-"):
      return None, None, f"opción desconocida: {arg}"
    elif ruta is None:
      ruta = arg
    else:
      return None, None, f"argumento inesperado: {arg} (solo se espera una ruta)"
    i += 1
  return ruta, minutos, None


def _mostrar_estado():
  override, expirado = estado.leer_override()
  if expirado:
    print(
      f"==> Override EXPIRADO (era: {expirado['origen']}, "
      f"{expirado['minutos']} min desde {expirado['desde']})."
    )
  if override:
    print(f"==> Override ACTIVO: {override['origen']}")
    print(
      f"    Faltan {estado.minutos_restantes(override)} min "
      f"(expira ~{estado.hora_expiracion(override)})."
    )
    print(f"    Original conservado: {override.get('original') or '(sin GIT_CHERRY_ORIGEN)'}")
    print("    Cancelar ya: xtool git-cherry-origin --reset")
  else:
    efectivo = estado.origen_original()
    print(f"==> Sin override vigente. Origen efectivo de git-cherry: {efectivo or '(ninguno: pasa la ruta como argumento o define GIT_CHERRY_ORIGEN)'}")
  return 0


def main(argv=None):
  argv = list(sys.argv[1:]) if argv is None else list(argv)

  if argv and argv[0] in ("-h", "--help"):
    print(__doc__)
    return 0

  if any(a in ("--reset", "--off") for a in argv):
    override, _ = estado.leer_override()
    estado.borrar_override()
    if override:
      print(f"==> Override cancelado. git-cherry vuelve a: {override.get('original') or '(sin GIT_CHERRY_ORIGEN)'}")
    else:
      print("==> No había override vigente (nada que cancelar).")
    return 0

  if not argv:
    return _mostrar_estado()

  ruta, minutos, error = _parsear(argv)
  if error:
    print(f"ERROR: {error}")
    print("Uso: xtool git-cherry-origin <ruta_origen> [--min N] | --reset | (sin args: estado)")
    return 1

  if ruta is None:
    return _mostrar_estado()

  origen = Path(ruta).expanduser().resolve()
  if not origen.is_dir():
    print(f"ERROR: '{origen}' no existe o no es un directorio")
    return 1
  top = subprocess.run(
    ("git", "-C", str(origen), "rev-parse", "--show-toplevel"),
    capture_output=True, text=True, check=False,
  )
  if top.returncode != 0 or not top.stdout.strip():
    print(f"ERROR: '{origen}' no está dentro de un repo git")
    return 1

  datos = estado.escribir_override(str(origen), minutos)
  print(f"==> Origen temporal ACTIVADO: {origen}")
  print(f"    Vigente por {minutos} min (hasta ~{estado.hora_expiracion(datos)}).")
  print(f"    Repo origen: {top.stdout.strip()}")
  print(f"    Original conservado: {datos['original'] or '(sin GIT_CHERRY_ORIGEN)'}")
  print("    Cancelar ya: xtool git-cherry-origin --reset")
  return 0


if __name__ == "__main__":
  sys.exit(main())
