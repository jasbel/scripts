import os
from pathlib import Path
from typing import Literal, cast


def load_env(filepath=".env"):
  """Carga variables desde un archivo .env sin librerías externas"""
  env_path = Path(filepath)

  if not env_path.exists():
    print(f"⚠️  Archivo {filepath} no encontrado")
    return

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

      os.environ.setdefault(key, value)


load_env()

BARIK_APP_DIR = os.environ.get("BARIK_APP_DIR", "/")
APPIUM_BARIK_DIR = os.environ.get("APPIUM_BARIK_DIR", "/")
NODE_ID = os.environ.get("NODE_ID", "NODE_ID")
JWT_SECRET = os.environ.get("JWT_SECRET", "JWT_SECRET")


def get_env():
  return cast(Literal["local", "docker"], os.environ.get("ENV", "local"))
