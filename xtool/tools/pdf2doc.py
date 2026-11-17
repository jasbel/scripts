"""Convierte archivos PDF a DOCX (mismo nombre, misma carpeta) con pdf2docx.

Si pdf2docx no está en la máquina, se instala solo con `uv tool install`
(la primera vez). Funciona desde cualquier directorio.

Uso:
  xtool pdf2doc <archivo.pdf> [<otro.pdf> ...]

Ejemplo:
  xtool pdf2doc informe.pdf   # genera informe.docx junto al original
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _find_binary():
  """Ruta al binario pdf2docx, también en ~/.local/bin si no está en el PATH.

  `uv tool install` deja el ejecutable en ~/.local/bin; ese directorio puede
  faltar en el PATH de la sesión actual, así que se comprueba a mano."""
  found = shutil.which("pdf2docx")
  if found:
    return found
  for name in ("pdf2docx", "pdf2docx.exe"):
    candidate = Path.home() / ".local" / "bin" / name
    if candidate.is_file():
      return str(candidate)
  return None


def _ensure_binary():
  """Devuelve la ruta al binario pdf2docx, instalándolo con uv si falta."""
  binary = _find_binary()
  if binary:
    return binary

  uv = shutil.which("uv")
  if not uv:
    print("✗ pdf2docx no está instalado y no hay uv para instalarlo.")
    print("  Instala uv: https://docs.astral.sh/uv/")
    return None

  # flush=True: la salida de uv (subprocess) no se mezcle con estos prints.
  print("→ Instalando pdf2docx con uv (solo la primera vez)...", flush=True)
  if subprocess.run([uv, "tool", "install", "pdf2docx"]).returncode != 0:
    print("✗ Falló la instalación de pdf2docx")
    return None

  binary = _find_binary()
  if not binary:
    print("✗ Se instaló pero no se encontró el ejecutable de pdf2docx")
    return None

  print("✓ pdf2docx instalado", flush=True)
  return binary


def _convert(binary, pdf: Path) -> bool:
  docx = pdf.with_suffix(".docx")
  # Silencia el FutureWarning de `fitz` (pdf2docx aún importa el nombre viejo).
  env = dict(os.environ, PYTHONWARNINGS="ignore::FutureWarning")
  cmd = [binary, "convert", str(pdf.resolve()), "-d", str(docx.resolve())]
  if subprocess.run(cmd, env=env).returncode == 0 and docx.is_file():
    print(f"✓ {pdf} → {docx}")
    return True
  print(f"✗ No se pudo convertir {pdf.name}")
  return False


def main(argv=None):
  argv = sys.argv[1:] if argv is None else list(argv)

  if not argv:
    print(__doc__.strip())
    return 1

  binary = _ensure_binary()
  if not binary:
    return 1

  exit_code = 0
  for arg in argv:
    pdf = Path(arg).expanduser()
    if not pdf.is_file():
      print(f"✗ No existe: {pdf}")
      exit_code = 1
    elif pdf.suffix.lower() != ".pdf":
      print(f"✗ No es un PDF: {pdf.name}")
      exit_code = 1
    elif not _convert(binary, pdf):
      exit_code = 1

  return exit_code


if __name__ == "__main__":
  sys.exit(main())
