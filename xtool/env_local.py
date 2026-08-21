import os
from pathlib import Path
from typing import Literal, cast


def _parse_env_file(env_path):
  vars_loaded = {}
  with open(env_path, "r", encoding="utf-8") as f:
    for line in f:
      line = line.strip()

      if not line or line.startswith("#"):
        continue

      if "=" not in line:
        continue

      key, value = line.split("=", 1)
      key = key.strip()
      value = value.strip()

      if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]

      if key not in vars_loaded:
        vars_loaded[key] = value
      os.environ.setdefault(key, value)
  return vars_loaded


def load_env(filepath=None):
  """Carga variables desde archivos .env sin librerías externas.

  Carga TODOS los .env existentes en orden de prioridad (setdefault:
  el primero que define una variable gana):
  1. .env del directorio actual (proyecto invocante, ej. override local)
  2. .env del arsenal (subiendo desde este archivo hasta la raíz del repo)

  Así un proyecto Symfony con su propio .env (sin TOKEN_AI) no impide
  que se cargue el TOKEN_AI del arsenal."""
  if filepath:
    candidates = [Path(filepath)]
  else:
    candidates = [Path.cwd() / ".env"]
    here = Path(__file__).resolve().parent
    for d in [here, *here.parents[:3]]:
      candidates.append(d / ".env")

  found = [p for p in candidates if p.exists()]

  if not found:
    print("⚠️  No se encontró ningún .env (ni en el directorio actual ni en el arsenal)")
    return {}

  loaded = {}
  for p in found:
    loaded.update({k: v for k, v in _parse_env_file(p).items() if k not in loaded})
  return loaded


load_env()

BARIK_APP_DIR = os.environ.get("BARIK_APP_DIR", "/")
APPIUM_BARIK_DIR = os.environ.get("APPIUM_BARIK_DIR", "/")
NODE_ID = os.environ.get("NODE_ID", "NODE_ID")
JWT_SECRET = os.environ.get("JWT_SECRET", "JWT_SECRET")


def get_env():
  return cast(Literal["local", "docker"], os.environ.get("ENV", "local"))
