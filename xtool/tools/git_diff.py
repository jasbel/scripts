#!/usr/bin/env python3
"""Genera un mensaje de commit Conventional Commits con IA a partir del diff staged.

Uso:
  xtool git-diff

Requisitos:
  - Estar en un repo git con cambios staged (git add)
  - TOKEN_AI en el .env del proyecto o del arsenal

El diff se limita a 1M de caracteres: se excluyen lockfiles, binarios y
generados y, si aun así supera el límite, se trunca por archivo dejando un
resumen de lo omitido.

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

# Nivel de razonamiento del modelo: low | high | max (la API usa max por defecto)
MODEL_VARIANT = "low"

MAX_DIFF_CHARS = 1_000_000
MIN_CHUNK_CHARS = 5_000
TAIL_MAX_LINES = 40
MARKER_RESERVE = 256

GIT_DIFF_FLAGS = [
  "-U1",
  "--diff-algorithm=histogram",
  "--indent-heuristic",
  "--ignore-cr-at-eol",
  "--ignore-blank-lines",
  "--find-renames=50%",
  "--ignore-submodules=all",
  "--no-ext-diff",
  "--no-color",
]

ORIGINAL_EXCLUDES = [
  ":(exclude)*.yaml",
  ":(exclude)*.yml",
  ":(exclude)*.json",
  ":(exclude).gitignore",
  # ":(exclude)git_diff.ts",
  # ":(exclude)*/git_diff.ts",
  # ":(exclude)git_diff.py",
  # ":(exclude)*/git_diff.py",
  ":(exclude)test.py",
  ":(exclude)*/test.py",
]

BASE_EXCLUDE_PATTERNS = [
  r"\.lock$",
  r"\.sum$",
  r"(^|/)vendor/",
  r"(^|/)target/",
  r"(^|/)out/",
  r"(^|/)\.next/",
  r"(^|/)\.nuxt/",
  r"(^|/)\.output/",
  r"(^|/)node_modules/",
  r"(^|/)__pycache__/",
  r"\.pyc$",
  r"\.min\.js$",
  r"\.min\.css$",
  r"\.map$",
  r"\.snap$",
  r"(^|/)__snapshots__/",
  r"_pb2\.py$",
  r"\.pb\.go$",
  r"\.generated\.",
  r"\.(png|jpe?g|gif|webp|ico|pdf|zip|woff2?|ttf|mp4)$",
  r"\.(csv|tsv|xlsx)$",
  r"(^|/)\.idea/",
  r"(^|/)\.vscode/",
  r"(^|/)\.DS_Store$",
  r"\.swp$",
]

ROUND1_EXCLUDE_PATTERNS = [r"\.md$", r"^package[^/]*\.json$", r"(^|/)build/", r"(^|/)dist/"]
CSS_EXCLUDE_PATTERN = r"\.css$"
SCSS_PATTERN = r"\.scss$"

BASE_EXCLUDE_RE = [re.compile(p) for p in BASE_EXCLUDE_PATTERNS]
ROUND1_EXCLUDE_RE = [re.compile(p) for p in ROUND1_EXCLUDE_PATTERNS]
CSS_EXCLUDE_RE = [re.compile(CSS_EXCLUDE_PATTERN)]
SCSS_RE = re.compile(SCSS_PATTERN)


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
      # output = f"Copiado a portapapeles {submethod}\n===========\n\n{texto}\n\n===========\n"
      output = f"Copiado a portapapeles {submethod}"
      print(output)

    return submethod or False

  except subprocess.CalledProcessError as e:
    print(f"Error al copiar al portapapeles: {e}")
    return False
  except Exception as e:
    print(f"Error inesperado: {e}")
    return False


def _clean_path(raw):
  p = raw.strip().strip('"')
  if p.startswith(("a/", "b/")):
    return p[2:]
  return p


def _chunk_path(lines):
  fallback = None
  for line in lines[:12]:
    s = line.rstrip("\n")
    if s.startswith("+++ "):
      p = _clean_path(s[4:])
      if p != "/dev/null":
        return p
    elif s.startswith("--- "):
      p = _clean_path(s[4:])
      if p != "/dev/null":
        fallback = p
    elif s.startswith("rename to "):
      fallback = s[10:].strip().strip('"')
  if fallback is None and lines:
    header = lines[0].rstrip("\n")
    if header.startswith("diff --git "):
      rest = header[11:]
      m = re.match(r'^"a/(.+)"\s+"b/(.+)"$', rest)
      if not m:
        m = re.match(r"^a/(.+) b/(.+)$", rest)
      if m:
        return m.group(2)
  return fallback


def _split_chunks(diff_text):
  chunks = []
  current = None
  for line in diff_text.splitlines(keepends=True):
    if line.startswith("diff --git "):
      if current:
        chunks.append(current)
      current = {"lines": [line], "text": "", "path": None}
    elif current is not None:
      current["lines"].append(line)
  if current:
    chunks.append(current)
  for c in chunks:
    c["text"] = "".join(c["lines"])
    c["path"] = _chunk_path(c["lines"])
  return chunks


def _match_any(path, regexes):
  return any(r.search(path) for r in regexes)


def _partition(chunks, regexes):
  keep, dropped = [], []
  for c in chunks:
    if c["path"] and _match_any(c["path"], regexes):
      dropped.append(c)
    else:
      keep.append(c)
  return keep, dropped


def _truncate_chunk(chunk, budget):
  used = 0
  out = []
  for i, line in enumerate(chunk["lines"]):
    if i > 0 and used + len(line) > budget:
      break
    out.append(line)
    used += len(line)
  omitted = len(chunk["text"]) - used
  if omitted > 0:
    out.append(f"\n[... diff truncado: {omitted} de {len(chunk['text'])} chars omitidos en {chunk['path'] or 'archivo'} ...]\n")
  return "".join(out), omitted


def _fit_chunks(chunks, budget):
  full, big = [], []
  total = 0
  for c in chunks:
    if total + len(c["text"]) <= budget:
      full.append(c)
      total += len(c["text"])
    else:
      big.append(c)
  truncated, omitted = [], []
  for c in big:
    avail = budget - total
    if avail < MIN_CHUNK_CHARS:
      omitted.append(c)
      continue
    text, om = _truncate_chunk(c, avail - MARKER_RESERVE)
    truncated.append({"path": c["path"], "omitted": om, "text": text, "kept": len(text), "total": len(c["text"])})
    total += len(text)
  return full, truncated, omitted


def _compact_stats(paths):
  if not paths:
    return []
  try:
    proc = subprocess.run(
      ["git", "diff", "--cached", "--compact-summary", "--", ".", *ORIGINAL_EXCLUDES],
      capture_output=True,
      text=True,
      encoding="utf-8",
      errors="replace",
    )
  except Exception:
    return []
  if proc.returncode != 0:
    return []
  stats = {}
  for line in proc.stdout.splitlines():
    if " | " not in line:
      continue
    raw = line.split(" | ")[0].strip()
    p = re.sub(r"\s*\([^)]*\)$", "", raw)
    stats[p] = line
  return [stats[p] for p in paths if p in stats]


def _build_tail(paths):
  lines = _compact_stats([p for p in paths if p])
  if not lines:
    return ""
  shown = lines[:TAIL_MAX_LINES]
  tail = "[Resumen de archivos excluidos o truncados del diff:]\n" + "\n".join(shown)
  if len(lines) > TAIL_MAX_LINES:
    tail += f"\n[+ {len(lines) - TAIL_MAX_LINES} archivos más]"
  return "\n" + tail + "\n"


def _fmt_size(n):
  if n >= 1_048_576:
    return f"{n / 1_048_576:.2f} MB"
  if n >= 1024:
    return f"{n / 1024:.1f} KB"
  return f"{n} B"


def _fmt_thousands(n):
  return f"{n:,}".replace(",", ".")


def _add_stage(stages, label, before, after, files_before, files_after, dropped, truncated=None):
  stages.append({
    "label": label,
    "before": before,
    "after": after,
    "files_before": files_before,
    "files_after": files_after,
    "dropped": [(c["path"], len(c["text"])) for c in dropped],
    "truncated": truncated or [],
  })


def get_git_diff():
  meta = {
    "error": None,
    "empty_reason": None,
    "original_chars": 0,
    "command": "",
    "raw_files": 0,
    "rounds": [],
    "retry": False,
    "excluded_files": [],
    "truncated_files": [],
    "omitted_files": [],
    "stages": [],
    "tail_chars": 0,
  }
  cmd = ["git", "diff", "--cached", *GIT_DIFF_FLAGS, "--", ".", *ORIGINAL_EXCLUDES]
  meta["command"] = " ".join(cmd)
  try:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
  except Exception as e:
    meta["error"] = f"No se pudo ejecutar git: {e}"
    return None, meta

  if proc.returncode != 0:
    meta["error"] = f"git diff falló ({proc.returncode}): {proc.stderr.strip()}"
    return None, meta

  raw = proc.stdout
  meta["original_chars"] = len(raw)

  if not raw.strip():
    check = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    meta["empty_reason"] = "all_excluded" if (check.returncode == 0 and check.stdout.strip()) else "no_staged"
    return None, meta

  chunks = _split_chunks(raw)
  meta["raw_files"] = len(chunks)
  stages = []

  keep, dropped = _partition(chunks, BASE_EXCLUDE_RE)
  meta["excluded_files"] = [c["path"] for c in dropped]
  total = sum(len(c["text"]) for c in keep)
  _add_stage(stages, "base: lockfiles, binarios, generados, build, IDE/OS", meta["original_chars"], total, len(chunks), len(keep), dropped)
  rounds = []

  if keep and total > MAX_DIFF_CHARS:
    kept1, drop1 = _partition(keep, ROUND1_EXCLUDE_RE)
    if kept1:
      rounds.append(1)
      after1 = sum(len(c["text"]) for c in kept1)
      _add_stage(stages, "ronda 1: *.md, package*.json, build/, dist/", total, after1, len(keep), len(kept1), drop1)
      meta["excluded_files"] += [c["path"] for c in drop1]
      keep = kept1
      total = after1
      if total > MAX_DIFF_CHARS and any(c["path"] and SCSS_RE.search(c["path"]) for c in keep):
        kept2, drop2 = _partition(keep, CSS_EXCLUDE_RE)
        if kept2:
          rounds.append(2)
          after2 = sum(len(c["text"]) for c in kept2)
          _add_stage(stages, "ronda 2: *.css (cambios .scss detectados)", total, after2, len(keep), len(kept2), drop2)
          meta["excluded_files"] += [c["path"] for c in drop2]
          keep = kept2
          total = after2

  if not keep:
    meta["retry"] = True
    meta["excluded_files"] = []
    keep = chunks
    total = sum(len(c["text"]) for c in chunks)
    _add_stage(stages, "reintento: exclusiones desactivadas (el filtrado eliminó todos los archivos)", meta["original_chars"], total, len(chunks), len(chunks), [])

  if total > MAX_DIFF_CHARS:
    rounds.append(3)
    pre_tail = _build_tail(meta["excluded_files"])
    full, truncated, omitted = _fit_chunks(keep, MAX_DIFF_CHARS - len(pre_tail) - MARKER_RESERVE)
    body = sum(len(c["text"]) for c in full) + sum(len(t["text"]) for t in truncated)
    _add_stage(
      stages,
      "ronda 3: truncado por archivo",
      total,
      body,
      len(keep),
      len(full) + len(truncated),
      omitted,
      truncated=[{"path": t["path"], "kept": t["kept"], "total": t["total"], "omitted": t["omitted"]} for t in truncated],
    )
  else:
    full, truncated, omitted = keep, [], []

  meta["rounds"] = rounds
  meta["truncated_files"] = [{"path": t["path"], "omitted": t["omitted"], "kept": t["kept"], "total": t["total"]} for t in truncated]
  meta["omitted_files"] = [c["path"] for c in omitted]

  tail = ""
  tail_paths = list(meta["excluded_files"]) + list(meta["omitted_files"]) + [t["path"] for t in truncated]
  if tail_paths:
    tail = _build_tail(tail_paths)

  final = "".join([c["text"] for c in full] + [t["text"] for t in truncated]) + tail
  while len(final) > MAX_DIFF_CHARS and "\n" in tail:
    tail = tail[: tail.rfind("\n")]
    final = "".join([c["text"] for c in full] + [t["text"] for t in truncated]) + tail
  meta["tail_chars"] = len(tail)
  meta["stages"] = stages

  return final, meta


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
      extra_body={"stream_options": {"include_usage": True}, "variant": MODEL_VARIANT},
    )

    respuesta = ""
    for chunk in stream:
      chunk = cast(ChatCompletionChunk, chunk)
      if chunk.choices and chunk.choices[0].delta.content:
        if t_first_token is None:
          t_first_token = time.perf_counter()
          print(f"   -> Primer token: {(t_first_token - t_start):.2f}s \n")
          print(f"=============================================\n")
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
    print(f"\n=============================================")
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
  diff, meta = get_git_diff()
  print(f"Tiempo obtención git diff: {(time.perf_counter() - t_diff):.4f}s")

  if diff is None:
    if meta["error"]:
      print(f"Error al obtener git diff: {meta['error']}")
    elif meta["empty_reason"] == "all_excluded":
      print("Solo hay cambios en archivos excluidos (json, lockfiles, generados). No hay nada para analizar")
    else:
      print("No hay cambios pendientes en git")
    return

  print("\n========== CAPTURA DEL DIFF ==========")
  print(f"Comando: {meta['command']}")
  print(f"Archivos en diff: {meta['raw_files']} · original: {_fmt_thousands(meta['original_chars'])} chars ({_fmt_size(meta['original_chars'])})")

  for i, st in enumerate(meta["stages"], 1):
    print(f"\n[{i}] {st['label']}")
    print(f"    {_fmt_thousands(st['before'])} → {_fmt_thousands(st['after'])} chars · archivos: {st['files_before']} → {st['files_after']}")
    for p, ch in st["dropped"][:15]:
      print(f"    - {p} ({_fmt_size(ch)})")
    if len(st["dropped"]) > 15:
      print(f"    - ... y {len(st['dropped']) - 15} archivos más")
    for t in st["truncated"]:
      pct = (t["kept"] / t["total"] * 100) if t["total"] else 0
      print(f"    ~ {t['path']}: {_fmt_size(t['kept'])} de {_fmt_size(t['total'])} ({pct:.0f}% · {_fmt_thousands(t['omitted'])} chars omitidos)")

  pct_final = len(diff) / MAX_DIFF_CHARS * 100
  print(f"\nFINAL: {_fmt_thousands(len(diff))} / {_fmt_thousands(MAX_DIFF_CHARS)} chars ({_fmt_size(len(diff))} · {pct_final:.1f}% del presupuesto · cola: {_fmt_thousands(meta['tail_chars'])} chars)\n")

  results = []
  for model in MODELS:
    print(f"\n=== Probando modelo: {model} ===")
    result = analizer_changes(diff, model)
    results.append(result)



  # print("\n\n========== RESUMEN COMPARATIVO ==========")

  scored = []
  for r in results:
    if r.get("error"):
      continue
    price = PRICING_USD_PER_1M.get(r["model"], {"input": 0, "output": 0})
    cost = (r["prompt_tokens"] * price["input"] + r["completion_tokens"] * price["output"]) / 1_000_000
    quality, checks = score_quality(r["output"])
    scored.append({**r, "cost": cost, "quality": quality, "checks": checks})

  # header = "Modelo".ljust(16) + " | " + "1er token".rjust(9) + " | " + "Total".rjust(8) + " | " + "Tokens i/o".rjust(14) + " | " + "Costo".rjust(8) + " | " + "Calidad".rjust(7) + " | " + "Score".rjust(6)
  # print(header)
  # print("-" * 85)

  # max_time = max((s["total_ms"] for s in scored), default=1) or 1
  # max_cost = max((s["cost"] for s in scored), default=0.0001) or 0.0001

  # for s in scored:
  #   t_score = 1 - s["total_ms"] / max_time
  #   c_score = 1 - s["cost"] / max_cost
  #   s["combined"] = t_score * 0.25 + c_score * 0.25 + s["quality"] * 0.5

  # scored.sort(key=lambda s: s["combined"], reverse=True)

  # for s in scored:
  #   first = "N/A" if s["first_token_ms"] is None else f"{s['first_token_ms'] / 1000:.2f}s"
  #   print(
  #     s["model"].ljust(16)
  #     + " | "
  #     + first.rjust(9)
  #     + " | "
  #     + f"{s['total_ms'] / 1000:.2f}s".rjust(8)
  #     + " | "
  #     + f"{s['prompt_tokens']}/{s['completion_tokens']}".rjust(14)
  #     + " | "
  #     + f"${s['cost']:.5f}".rjust(8)
  #     + " | "
  #     + f"{s['quality'] * 100:.0f}%".rjust(7)
  #     + " | "
  #     + f"{s['combined'] * 100:.0f}".rjust(6),
  #   )




  print("\n--- Detalle de calidad por modelo ---")
  for s in scored:
    failed = [c["name"] for c in s["checks"] if not c["pass"]]
    estado = f" (falla: {', '.join(failed)})" if failed else " (perfecto)"
    print(f"{s['model']}: {s['quality'] * 100:.0f}%{estado}")

  if not scored:
    pass
  elif len(results) == 1:
    best = scored[0]
    # print(f"\nScore combinado: {best['combined'] * 100:.0f}/100")
    commit, summary = parse_response(best["output"])
    copy_to_clipboard(commit)
    # if summary:
    #   print(f"\n{summary}\n")
  elif len(results) > 1:
    best = scored[0]
    # print(f"\nGanador global: {best['model']} (score {best['combined']:.2f})")
    # print("Pesos: tiempo 25% · costo 25% · calidad 50%")
    commit, summary = parse_response(best["output"])
    copy_to_clipboard(commit)
    # if summary:
    #   print(f"\n{summary}\n")

  elapsed = time.perf_counter() - start_time
  print(f"\nTIEMPO TOTAL SCRIPT: {elapsed:.2f}s")


if __name__ == "__main__":
  main()

# python3 scripts/git_diff.py
