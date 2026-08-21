"""Termina el proceso que ocupa un puerto TCP (o el contenedor Docker que lo mapea).

Uso:
  xtool kill-port <puerto>

Ejemplo:
  xtool kill-port 7302
"""

import sys

from xtool.common.utils_command import kill_port_process


def main(argv=None):
  argv = sys.argv[1:] if argv is None else list(argv)

  if not argv:
    print(__doc__.strip())
    return 1

  port = argv[0]
  if not port.isdigit():
    print(f"Puerto inválido: {port}")
    return 1

  if kill_port_process(int(port)):
    print(f"✓ Proceso en el puerto {port} terminado")
    return 0

  print(f"No se encontró ningún proceso escuchando en el puerto {port}")
  return 1


if __name__ == "__main__":
  sys.exit(main())
