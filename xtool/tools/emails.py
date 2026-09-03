"""Servidor de preview de emails (xtool/emails) para solocruceros y odoo.

Uso:
  xtool emails                # server de preview con hot-reload (default)
  xtool emails build          # compila MJML -> HTML una sola vez
  xtool emails watch          # compila MJML y recompila al guardar
  xtool emails extract        # extrae datos del HTML de referencia a data.json
  xtool emails --port 3500    # server en otro puerto (default: 3466)

Flags:
  --port <n>    puerto del server (solo aplica al server)
  --no-install  no ejecutar npm install aunque falte node_modules

Requisito: node/npm en el PATH. La primera vez instala dependencias solo.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

EMAILS_DIR = Path(__file__).resolve().parents[1] / "emails"

COMMANDS = {
  "server": ["node", "server.js"],
  "build": ["node", "mjml-build.js"],
  "watch": ["node", "mjml-build.js", "--watch"],
  "extract": ["node", "extract.js"],
}


def _ensure_deps(install):
  if (EMAILS_DIR / "node_modules").is_dir():
    return True
  if not install:
    print("Faltan dependencias: node_modules no existe (quita --no-install o corre npm install)")
    return False
  if not shutil.which("npm"):
    print("npm no está disponible en el PATH; instala Node.js primero")
    return False
  print("[deps] node_modules no existe, ejecutando npm install ...")
  code = subprocess.call(["npm", "install"], cwd=EMAILS_DIR)
  if code != 0:
    print(f"npm install falló con código {code}")
    return False
  return True


def main(argv=None):
  argv = sys.argv[1:] if argv is None else list(argv)

  port = None
  no_install = False
  positional = []
  i = 0
  while i < len(argv):
    a = argv[i]
    if a in ("-h", "--help"):
      print((__doc__ or "").strip())
      return 0
    if a == "--no-install":
      no_install = True
    elif a == "--port":
      if i + 1 >= len(argv) or not argv[i + 1].isdigit():
        print("--port requiere un número de puerto")
        return 1
      port = argv[i + 1]
      i += 1
    else:
      positional.append(a)
    i += 1

  sub = positional[0] if positional else "server"
  if sub not in COMMANDS:
    print(f"xtool emails: subcomando desconocido: {sub}")
    print((__doc__ or "").strip())
    return 1

  if not EMAILS_DIR.is_dir():
    print(f"No se encuentra el proyecto de emails: {EMAILS_DIR}")
    return 1
  if not shutil.which("node"):
    print("node no está disponible en el PATH; instala Node.js primero")
    return 1
  if not _ensure_deps(not no_install):
    return 1

  env = os.environ.copy()
  if sub == "server" and port:
    env["PORT"] = port

  try:
    return subprocess.call(COMMANDS[sub], cwd=EMAILS_DIR, env=env)
  except KeyboardInterrupt:
    return 0


if __name__ == "__main__":
  sys.exit(main())
