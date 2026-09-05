#!/usr/bin/env python3
"""Genera un mensaje de commit Conventional Commits con IA a partir del diff staged.

Uso:
  xtool git-diff

Requisitos:
  - Estar en un repo git con cambios staged (git add)
  - TOKEN_AI en el .env del proyecto o del arsenal

El commit ganador se copia al portapapeles.
"""

import os
import platform
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional, cast

from zai import ZaiClient

from xtool.env_local import load_env

load_env()


class ChatCompletionChunk:
  id: Optional[str] = None
  # choices: List[Choice]
  choices: List[Any]
  created: Optional[int] = None
  model: Optional[str] = None
  usage: Optional[Any] = None
  extra_json: Dict[str, Any]


client = ZaiClient(api_key=os.getenv("TOKEN_AI"), base_url="https://api.z.ai/api/coding/paas/v4/")

MODELS = [
  # "glm-4.5-air",
  "glm-5.3-flash",
  # "glm-4.5-flash",
  # "glm-5.2",
  # "glm-5.1",
  # "glm-4.6",
  # "glm-5-turbo",
]

PRICING_USD_PER_1M = {
  # ── Free tier
  "glm-4.5-flash": {"input": 0, "output": 0},
  "glm-4.7-flash": {"input": 0, "output": 0},
  "glm-4.6v-flash": {"input": 0, "output": 0},
  # ── Premium / Flagship
  "glm-5.1": {"input": 1.4, "output": 4.4},
  "glm-5": {"input": 1.0, "output": 3.2},
  "glm-5-turbo": {"input": 1.2, "output": 4.0},
  "glm-5v-turbo": {"input": 1.2, "output": 4.0},
  "glm-4.5-x": {"input": 2.2, "output": 8.9},
  # ── Mid-tier
  "glm-4.7": {"input": 0.6, "output": 2.2},
  "glm-4.6": {"input": 0.6, "output": 2.2},
  "glm-4.5": {"input": 0.6, "output": 2.2},
  "glm-4.5-airx": {"input": 1.1, "output": 4.5},
  # ── Budget
  "glm-4.5-air": {"input": 0.2, "output": 1.1},
  "glm-4.7-flashx": {"input": 0.07, "output": 0.4},
  "glm-4-32b": {"input": 0.1, "output": 0.1},
  # ── Vision / OCR
  "glm-4.6v": {"input": 0.3, "output": 0.9},
  "glm-4.5v": {"input": 0.6, "output": 1.8},
  "glm-ocr": {"input": 0.03, "output": 0.03},
  # ── Next level
  "glm-5.3-flash": {"input": 0.15, "output": 0.5},
  "glm-5.2": {"input": 1.4, "output": 4.4},
}

VALID_TYPES = ["feat", "fix", "refactor", "style", "docs", "test", "chore", "perf", "ci", "build"]
VALID_SCOPES = ["template", "css", "api", "common", "db", "auth", "core", "test", "utils", "models", "scripts", "ci"]

SYSTEM_PROMPT = """
Genera un mensaje de commit Conventional Commits en español.

Responde únicamente con el commit, sin explicaciones ni bloques de código.

Formato:

[tipo]: <Título>.

* <Descripción>. (<alcance>)

---

Reglas:
- Tipos: feat|fix|refactor|style|docs|test|chore|perf|ci|build
- Título: español, inicia con mayúscula, voz pasiva ("Se + pretérito"), máximo 150 caracteres y termina con punto.
- Descripciones: una o más líneas con "* ", voz pasiva ("Se + pretérito"), terminan con ". (<alcance>)".
- Alcances: gui|api|common|db|auth|core|test
- Deja una línea en blanco entre el título y las descripciones.
- No inventes cambios; resume solo los detectados.
- Ignora cambios de archivos .json, .yml .gitignore.
"""


def _copy_windows(texto):
  ctypes = __import__("ctypes")
  from ctypes import wintypes

  CF_UNICODETEXT = 13
  GMEM_MOVEABLE = 0x0002

  kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
  user32 = ctypes.WinDLL("user32", use_last_error=True)

  kernel32.GlobalAlloc.restype = ctypes.c_void_p
  kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
  kernel32.GlobalLock.restype = ctypes.c_void_p
  kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
  kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
  kernel32.GlobalFree.restype = ctypes.c_void_p
  kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)
  user32.SetClipboardData.restype = ctypes.c_void_p
  user32.SetClipboardData.argtypes = (wintypes.UINT, ctypes.c_void_p)

  data = ctypes.create_unicode_buffer(texto + "\0")
  size = ctypes.sizeof(data)

  h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
  if not h_global:
    return False
  locked = kernel32.GlobalLock(h_global)
  if not locked:
    kernel32.GlobalFree(h_global)
    return False
  ctypes.memmove(locked, data, size)
  kernel32.GlobalUnlock(h_global)

  if not user32.OpenClipboard(None):
    kernel32.GlobalFree(h_global)
    return False
  try:
    user32.EmptyClipboard()
    if user32.SetClipboardData(CF_UNICODETEXT, h_global):
      return True
    kernel32.GlobalFree(h_global)
    return False
  finally:
    user32.CloseClipboard()


def copy_to_clipboard(texto):
  """Copia texto al portapapeles compatible con Ubuntu, macOS y Windows."""
  try:
    system = platform.system()
    submethod = ""

    if system == "Linux":
      if shutil.which("xclip"):
        subprocess.run(["xclip", "-selection", "clipboard"], input=texto.encode("utf-8"), check=True)
        submethod = "(xclip)"
      elif shutil.which("xsel"):
        subprocess.run(["xsel", "--clipboard", "--input"], input=texto.encode("utf-8"), check=True)
        submethod = "(xsel)"
      else:
        print("Error: No se encontró xclip ni xsel. Instala con: sudo apt install xclip")
    elif system == "Darwin":
      subprocess.run(["pbcopy"], input=texto.encode("utf-8"), check=True)
      submethod = "(pbcopy)"
    elif system == "Windows":
      if _copy_windows(texto):
        submethod = "(win32)"
      else:
        print("Error: No se pudo acceder al portapapeles de Windows")
    else:
      print(f"Error: Sistema operativo no soportado: {system}")

    if submethod:
      output = f"Copiado a portapapeles {submethod}\n===========\n\n{texto}\n\n===========\n"
      print(output)

    return submethod or False

  except subprocess.CalledProcessError as e:
    print(f"Error al copiar al portapapeles: {e}")
    return False
  except Exception as e:
    print(f"Error inesperado: {e}")
    return False


def get_git_diff():
  try:
    result = subprocess.run(
      [
        "git",
        "diff",
        "--cached",
        "-U1",
        "--",
        ".",
        ":(exclude)*.yaml",
        ":(exclude)*.yml",
        ":(exclude)*.json",
        ":(exclude).gitignore",
        ":(exclude)git_diff.ts",
        ":(exclude)git_diff.py",
        ":(exclude)test.py",
      ],
      capture_output=True,
      text=True,
    )
    if result.returncode != 0:
      return None
    return result.stdout
  except Exception:
    return None


def parse_response(respuesta):
  match = re.search(r"^\s*-{3}RESUMEN-{3}\s*$", respuesta, re.MULTILINE)
  if not match:
    return respuesta.strip(), ""
  commit = respuesta[: match.start()].strip()
  summary = respuesta[match.end() :].strip()
  return commit, summary


def score_quality(output):
  checks = []
  text = output.strip()
  if not text:
    return 0.0, [{"name": "output no vacío", "pass": False}]

  lines = [li.rstrip() for li in text.split("\n")]
  first_line = lines[0] if lines else ""

  type_regex = re.compile(rf"^({'|'.join(VALID_TYPES)}):")
  checks.append({"name": "tipo válido", "pass": bool(type_regex.search(first_line))})
  checks.append({"name": "título ≤ 150 chars", "pass": len(first_line) <= 150})
  checks.append({"name": "título termina con punto", "pass": first_line.strip().endswith(".")})
  checks.append({"name": "título en voz pasiva", "pass": bool(re.search(r"\b(?:Se|Fue|Fueron)\s+\w", first_line, re.I))})

  bullets = [li for li in lines if li.startswith("* ")]
  checks.append({"name": "tiene bullets", "pass": len(bullets) >= 1})
  checks.append({"name": "≤ 7 bullets", "pass": len(bullets) <= 7})

  scope_regex = re.compile(rf"\(({'|'.join(VALID_SCOPES)})\)\s*$")
  checks.append({"name": "bullets con alcance válido", "pass": len(bullets) > 0 and all(scope_regex.search(b) for b in bullets)})
  voz_regex = re.compile(r"\b(?:Se|Fue|Fueron)\s+\w", re.I)
  checks.append({"name": "bullets en voz pasiva", "pass": len(bullets) > 0 and all(voz_regex.search(b) for b in bullets)})

  blank_between = bool(re.search(r"\n\s*\n", text))
  checks.append({"name": "línea en blanco entre título y bullets", "pass": blank_between})
  checks.append({"name": "longitud total < 800 chars", "pass": len(text) < 800})
  checks.append({"name": "sin separadores ===", "pass": not re.search(r"={3,}", text)})

  passed = sum(1 for c in checks if c["pass"])
  return passed / len(checks), checks


def analizer_changes(diff, model):
  t_start = time.perf_counter()
  t_first_token = None
  prompt_tokens = 0
  completion_tokens = 0
  reasoning_tokens = 0

  try:
    stream = client.chat.completions.create(
      model=model,
      messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Analiza y Crea el git commit siguiendo **Conventional Commits**:\n\n{diff}"},
      ],
      stream=True,
      thinking={"type": "disabled"},
      extra_body={"stream_options": {"include_usage": True}},
    )

    respuesta = ""
    for chunk in stream:
      chunk = cast(ChatCompletionChunk, chunk)
      if chunk.choices and chunk.choices[0].delta.content:
        if t_first_token is None:
          t_first_token = time.perf_counter()
          print(f"   -> Primer token: {(t_first_token - t_start):.2f}s")
        content = chunk.choices[0].delta.content
        print(content, end="", flush=True)
        respuesta += content
      if chunk.usage:
        prompt_tokens = chunk.usage.prompt_tokens or 0
        completion_tokens = chunk.usage.completion_tokens or 0
        details = getattr(chunk.usage, "completion_tokens_details", None)
        if details:
          reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0

    total_ms = (time.perf_counter() - t_start) * 1000
    print(f"\n   -> Stream completo: {(total_ms / 1000):.2f}s")
    print(f"   -> Tokens: prompt={prompt_tokens}, completion={completion_tokens}, reasoning={reasoning_tokens}")

    return {
      "model": model,
      "first_token_ms": (t_first_token - t_start) * 1000 if t_first_token else None,
      "total_ms": total_ms,
      "output": respuesta,
      "prompt_tokens": prompt_tokens,
      "completion_tokens": completion_tokens,
      "reasoning_tokens": reasoning_tokens,
    }
  except Exception as e:
    total_ms = (time.perf_counter() - t_start) * 1000
    msg = str(e)
    print(f"   -> Error: {msg}")
    return {
      "model": model,
      "first_token_ms": None,
      "total_ms": total_ms,
      "output": "",
      "prompt_tokens": 0,
      "completion_tokens": 0,
      "reasoning_tokens": 0,
      "error": msg,
    }


def main(argv=None):
  start_time = time.perf_counter()

  t_diff = time.perf_counter()
  diff = get_git_diff()
  print(f"Tiempo obtención git diff: {(time.perf_counter() - t_diff):.4f}s")

  if not diff or diff.strip() == "":
    print("No hay cambios pendientes en git")
    return

  diff_bytes = len(diff.encode("utf-8"))
  print(f"Tamaño del diff: {(diff_bytes / 1024):.2f} KB ({len(diff)} chars)\n")

  results = []
  for model in MODELS:
    print(f"\n=== Probando modelo: {model} ===")
    result = analizer_changes(diff, model)
    results.append(result)

  print("\n\n========== RESUMEN COMPARATIVO ==========")

  scored = []
  for r in results:
    if r.get("error"):
      continue
    price = PRICING_USD_PER_1M.get(r["model"], {"input": 0, "output": 0})
    cost = (r["prompt_tokens"] * price["input"] + r["completion_tokens"] * price["output"]) / 1_000_000
    quality, checks = score_quality(r["output"])
    scored.append({**r, "cost": cost, "quality": quality, "checks": checks})

  header = "Modelo".ljust(16) + " | " + "1er token".rjust(9) + " | " + "Total".rjust(8) + " | " + "Tokens i/o".rjust(14) + " | " + "Costo".rjust(8) + " | " + "Calidad".rjust(7) + " | " + "Score".rjust(6)
  print(header)
  print("-" * 85)

  max_time = max((s["total_ms"] for s in scored), default=1) or 1
  max_cost = max((s["cost"] for s in scored), default=0.0001) or 0.0001

  for s in scored:
    t_score = 1 - s["total_ms"] / max_time
    c_score = 1 - s["cost"] / max_cost
    s["combined"] = t_score * 0.25 + c_score * 0.25 + s["quality"] * 0.5

  scored.sort(key=lambda s: s["combined"], reverse=True)

  for s in scored:
    first = "N/A" if s["first_token_ms"] is None else f"{s['first_token_ms'] / 1000:.2f}s"
    print(
      s["model"].ljust(16)
      + " | "
      + first.rjust(9)
      + " | "
      + f"{s['total_ms'] / 1000:.2f}s".rjust(8)
      + " | "
      + f"{s['prompt_tokens']}/{s['completion_tokens']}".rjust(14)
      + " | "
      + f"${s['cost']:.5f}".rjust(8)
      + " | "
      + f"{s['quality'] * 100:.0f}%".rjust(7)
      + " | "
      + f"{s['combined'] * 100:.0f}".rjust(6),
    )

  print("\n--- Detalle de calidad por modelo ---")
  for s in scored:
    failed = [c["name"] for c in s["checks"] if not c["pass"]]
    estado = f" (falla: {', '.join(failed)})" if failed else " (perfecto)"
    print(f"{s['model']}: {s['quality'] * 100:.0f}%{estado}")

  if not scored:
    pass
  elif len(results) == 1:
    best = scored[0]
    print(f"\nScore combinado: {best['combined'] * 100:.0f}/100")
    commit, summary = parse_response(best["output"])
    copy_to_clipboard(commit)
    if summary:
      print(f"\n{summary}\n")
  elif len(results) > 1:
    best = scored[0]
    print(f"\nGanador global: {best['model']} (score {best['combined']:.2f})")
    print("Pesos: tiempo 25% · costo 25% · calidad 50%")
    commit, summary = parse_response(best["output"])
    copy_to_clipboard(commit)
    if summary:
      print(f"\n{summary}\n")

  elapsed = time.perf_counter() - start_time
  print(f"\nTIEMPO TOTAL SCRIPT: {elapsed:.2f}s")


if __name__ == "__main__":
  main()

# python3 scripts/git_diff.py
