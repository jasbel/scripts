"""Estado del override temporal de GIT_CHERRY_ORIGEN (tools git-cherry).

El override vive en un JSON bajo el directorio de estado del usuario
(XDG_STATE_HOME, default ~/.local/state) con marca de expiración. El
vencimiento es PEREZOSO: no hay proceso de fondo; quien lee el archivo
(git-cherry, git-cherry-origin) detecta que expiró, lo borra y sigue con
el valor original (entorno o .env).
"""

import json
import math
import os
import time
from pathlib import Path

from xtool.env_local import load_env

ENV_ORIGEN = "GIT_CHERRY_ORIGEN"


def _state_file() -> Path:
  base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
  return Path(base) / "xtool" / "git-cherry-origin.json"


def origen_original():
  """Valor efectivo de GIT_CHERRY_ORIGEN (entorno o .env), o None."""
  load_env()
  val = os.environ.get(ENV_ORIGEN, "").strip()
  return val or None


def leer_override():
  """Lee el override. Devuelve (datos, expirado).

  - No existe / corrupto -> (None, None)
  - Vigente              -> (datos, None)
  - Expiró               -> borra el archivo y devuelve (None, datos_expirado)
  """
  path = _state_file()
  try:
    datos = json.loads(path.read_text(encoding="utf-8"))
  except (OSError, ValueError):
    return None, None
  if not isinstance(datos, dict) or not datos.get("origen") or not datos.get("expira_epoch"):
    return None, None
  try:
    expira = float(datos["expira_epoch"])
  except (TypeError, ValueError):
    return None, None
  if time.time() >= expira:
    borrar_override()
    return None, datos
  return datos, None


def escribir_override(origen: str, minutos: int):
  """Activa el override y devuelve los datos guardados.

  Conserva el valor original de GIT_CHERRY_ORIGEN al momento del cambio
  (solo informativo: al expirar el valor efectivo vuelve a ser el del
  entorno/.env, que no se toca nunca).
  """
  datos = {
    "origen": origen,
    "original": origen_original(),
    "minutos": minutos,
    "expira_epoch": time.time() + minutos * 60,
    "desde": time.strftime("%Y-%m-%d %H:%M"),
  }
  path = _state_file()
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  return datos


def borrar_override():
  """Cancela el override (no falla si no existe)."""
  _state_file().unlink(missing_ok=True)


def minutos_restantes(datos) -> int:
  """Minutos que faltan para la expiración (techo, mínimo 0)."""
  seg = float(datos["expira_epoch"]) - time.time()
  return max(0, math.ceil(seg / 60))


def hora_expiracion(datos) -> str:
  """Hora local (HH:MM) en la que expira el override."""
  return time.strftime("%H:%M", time.localtime(float(datos["expira_epoch"])))
