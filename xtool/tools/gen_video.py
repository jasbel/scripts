#!/usr/bin/env python3
"""Genera videos con IA (CogVideoX de Z.ai) a partir de un prompt o una imagen.

Uso:
  xtool gen-video "un gato astronauta flotando en el espacio"
  xtool gen-video "prompt..." --quality quality --size 1280x720
  xtool gen-video "prompt..."                        # descarga el mp4 en ~/Downloads
  xtool gen-video "prompt..." --out video.mp4        # lo descarga en otra ruta
  xtool gen-video --image foto.png "anima esta foto" # imagen -> video
  xtool gen-video --task <id>                        # retoma una tarea previa
  xtool gen-video "prompt..." --no-wait              # solo crea la tarea y sale

Crea la tarea asíncrona (zai-sdk con TOKEN_AI), muestra los cambios de estado
y al terminar imprime las URLs del video y la portada y descarga el mp4
(requests) en ~/Downloads; con --out se indica otra ruta (directorio o
archivo .mp4) y con --no-download no se descarga.

Opciones:
  --model <nombre>     default cogvideox-3
  --quality <modo>     speed (default) | quality
  --size <WxH>         default 1920x1080 (hasta 3840x2160)
  --fps <30|60>        default 30
  --duration <5|10>    segundos de video, default 5
  --no-audio           desactiva el audio generado por IA
  --image <ruta|url>   imagen inicial (image-to-video); una ruta local se
                       lee y se envía como base64
  --out <ruta>         dónde descargar el mp4 (directorio o archivo .mp4);
                       default: ~/Downloads
  --no-download        no descarga el video, solo imprime las URLs
  --task <id>          no crea tarea nueva: espera y descarga la de ese ID
  --no-wait            crea la tarea, imprime su ID y termina sin esperar
  --timeout <seg>      máximo de espera, default 900

Requiere TOKEN_AI en el .env del proyecto o del arsenal.
"""

import base64
import mimetypes
import os
import re
import sys
import time
from pathlib import Path

import requests
from zai import ZaiClient

from xtool.env_local import load_env

load_env()

USAGE = 'Uso: xtool gen-video "prompt" [--quality speed|quality] [--size WxH] [--fps 30|60] [--duration 5|10] [--image <ruta|url>] [--out <ruta> | --no-download] [--task <id>] [--no-wait] [--no-audio] [--timeout <seg>]'

POLL_SECONDS = 5
DEFAULT_TIMEOUT = 900

VALID_QUALITY = ("speed", "quality")
VALID_FPS = (30, 60)
VALID_DURATION = (5, 10)
SIZE_RE = re.compile(r"^\d{3,4}x\d{3,4}$")


def parse_args(args):
  """Parsea argv. Devuelve (opts, error); opts=None para --help."""
  opts = {
    "prompt": None,
    "model": "cogvideox-3",
    "quality": "speed",
    "size": "1920x1080",
    "fps": 30,
    "duration": 5,
    "audio": True,
    "image": None,
    "out": None,
    "task": None,
    "no_wait": False,
    "no_download": False,
    "timeout": DEFAULT_TIMEOUT,
  }
  flags = {
    "--no-audio": "audio",
    "--no-wait": "no_wait",
    "--no-download": "no_download",
  }
  valores = {
    "--model": "model",
    "--quality": "quality",
    "--size": "size",
    "--fps": "fps",
    "--duration": "duration",
    "--image": "image",
    "--out": "out",
    "--task": "task",
    "--timeout": "timeout",
  }
  i = 0
  while i < len(args):
    a = args[i]
    if a in ("-h", "--help"):
      return None, None
    if a in flags:
      opts[flags[a]] = False if flags[a] == "audio" else True
      i += 1
      continue
    if a in valores or a.startswith("--") and a.split("=", 1)[0] in valores:
      clave = a.split("=", 1)[0]
      if "=" in a:
        valor = a.split("=", 1)[1]
        i += 1
      else:
        if i + 1 >= len(args):
          return None, f"{clave} requiere un valor"
        valor = args[i + 1]
        i += 2
      opts[valores[clave]] = valor
      continue
    if a.startswith("-"):
      return None, f"opción no reconocida: {a}"
    if opts["prompt"] is not None:
      return None, "solo se admite un prompt (entre comillas)"
    opts["prompt"] = a
    i += 1

  # --out sin valor (o con valor que es otra cosa) no aplica: exige valor arriba.
  if opts["quality"] not in VALID_QUALITY:
    return None, f"--quality debe ser {' o '.join(VALID_QUALITY)}, no '{opts['quality']}'"
  if not SIZE_RE.match(str(opts["size"])):
    return None, f"--size debe tener formato WxH (ej. 1920x1080), no '{opts['size']}'"
  try:
    opts["fps"] = int(opts["fps"])
    opts["duration"] = int(opts["duration"])
    opts["timeout"] = int(opts["timeout"])
  except ValueError:
    return None, "--fps, --duration y --timeout requieren un número entero"
  if opts["fps"] not in VALID_FPS:
    return None, f"--fps debe ser {' o '.join(map(str, VALID_FPS))}, no {opts['fps']}"
  if opts["duration"] not in VALID_DURATION:
    return None, f"--duration debe ser {' o '.join(map(str, VALID_DURATION))} segundos, no {opts['duration']}"
  if opts["timeout"] < 30:
    return None, "--timeout mínimo: 30 segundos"
  if not opts["task"] and not opts["prompt"] and not opts["image"]:
    return None, "falta el prompt (o usa --image / --task <id>)"
  return opts, None


def build_client():
  token = os.getenv("TOKEN_AI")
  if not token:
    return None
  return ZaiClient(api_key=token)


def load_image(image):
  """Ruta local -> data URI base64; cualquier otra cosa se pasa tal cual (URL)."""
  p = Path(image).expanduser()
  if not p.is_file():
    return image
  mime = mimetypes.guess_type(p.name)[0] or "image/png"
  b64 = base64.b64encode(p.read_bytes()).decode("ascii")
  return f"data:{mime};base64,{b64}"


def wait_task(client, task_id, timeout_s):
  """Sondea la tarea hasta SUCCESS/FAIL. Devuelve el resultado o None (timeout)."""
  inicio = time.perf_counter()
  ultimo = None
  while True:
    resultado = client.videos.retrieve_videos_result(id=task_id)
    estado = getattr(resultado, "task_status", None) or "?"
    transcurrido = time.perf_counter() - inicio
    if estado != ultimo:
      marca = f"[{transcurrido:5.0f}s] " if transcurrido >= 1 else ""
      print(f"{marca}estado: {estado}")
      ultimo = estado
    if estado == "SUCCESS":
      return resultado
    if estado == "FAIL":
      detalle = getattr(resultado, "task_status_ecp", None)
      print(f"Error: la generación falló{f' — {detalle}' if detalle else ''}")
      return resultado
    if transcurrido > timeout_s:
      print(f"Error: se agotó el tiempo ({int(transcurrido)}s) esperando la tarea {task_id}")
      print(f"  Puedes retomarla luego con: xtool gen-video --task {task_id}")
      return None
    time.sleep(POLL_SECONDS)


def resultado_urls(resultado):
  videos = getattr(resultado, "video_result", None) or []
  if not videos:
    return None, None
  return getattr(videos[0], "url", None), getattr(videos[0], "cover_image_url", None)


def download(url, out, task_id):
  """Descarga el mp4 en `out` (directorio o archivo .mp4); default ~/Downloads."""
  destino = Path(out).expanduser() if out else Path.home() / "Downloads"
  if not str(destino).endswith(".mp4"):
    destino = destino / f"video-{str(task_id)[:8]}.mp4"
  destino.parent.mkdir(parents=True, exist_ok=True)
  print(f"Descargando: {url}")
  with requests.get(url, stream=True, timeout=300) as r:
    r.raise_for_status()
    total = int(r.headers.get("content-length") or 0)
    bajado = 0
    with open(destino, "wb") as f:
      for chunk in r.iter_content(chunk_size=1 << 16):
        f.write(chunk)
        bajado += len(chunk)
        if total:
          sys.stdout.write(f"\r  {bajado / total * 100:5.1f}%  ({bajado / 1_048_576:.1f} MB)")
          sys.stdout.flush()
  if total:
    sys.stdout.write("\n")
  print(f"Guardado en: {destino} ({bajado / 1_048_576:.1f} MB)")
  return destino


def main(argv=None):
  args = list(sys.argv[1:] if argv is None else argv)
  opts, err = parse_args(args)
  if err:
    print(f"Error: {err}")
    print(USAGE)
    return 1
  if opts is None:
    print(__doc__.strip())
    return 0

  client = build_client()
  if client is None:
    print("Error: falta TOKEN_AI (defínelo en el .env del proyecto o del arsenal)")
    return 1

  try:
    if opts["task"]:
      task_id = opts["task"]
      print(f"Retomando tarea: {task_id}")
    else:
      resumen = (
        f"{opts['model']} · {opts['quality']} · {opts['size']} · {opts['fps']}fps"
        f" · {opts['duration']}s · audio {'sí' if opts['audio'] else 'no'}"
      )
      print(f"Creando tarea: {resumen}")
      respuesta = client.videos.generations(
        model=opts["model"],
        prompt=opts["prompt"],
        image_url=load_image(opts["image"]) if opts["image"] else None,
        quality=opts["quality"],
        with_audio=opts["audio"],
        size=opts["size"],
        fps=opts["fps"],
        duration=opts["duration"],
      )
      task_id = getattr(respuesta, "id", None)
      if not task_id:
        print("Error: la API no devolvió ID de tarea")
        print(respuesta)
        return 1
      print(f"Tarea creada. ID: {task_id}")
      if opts["no_wait"]:
        print(f"  Retómala luego con: xtool gen-video --task {task_id}")
        return 0

    resultado = wait_task(client, task_id, opts["timeout"])
    if resultado is None or getattr(resultado, "task_status", None) != "SUCCESS":
      return 1

    video_url, portada_url = resultado_urls(resultado)
    print(f"Video:   {video_url}")
    if portada_url:
      print(f"Portada: {portada_url}")
    if opts["no_download"]:
      print("(--no-download: no se descarga)")
    elif video_url:
      download(video_url, opts["out"], task_id)
    return 0
  except KeyboardInterrupt:
    print("\nCancelado.")
    return 130
  except Exception as e:
    print(f"Error: {e}")
    if "1113" in str(e) or "Insufficient balance" in str(e):
      print("\nLa cuenta Z.ai no tiene saldo ni paquete de recursos para este modelo")
      print("(la generación de video NO está incluida en el plan coding).")
      print("Recarga en https://z.ai o compra un paquete de recursos de CogVideoX.")
    return 1


if __name__ == "__main__":
  main()
