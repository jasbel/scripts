"""Optimiza imágenes (JPG, PNG, WebP) para web creando copias *-opt junto a la original.

La original nunca se modifica: el resultado lleva el mismo nombre con sufijo
-opt (foto.jpg → foto-opt.jpg). Con --2x/--1.5x se escala primero (retina) y
luego se optimiza (foto.jpg → foto-2x-opt.jpg). Si faltan herramientas
(imagemagick, jpegoptim, pngquant, oxipng, webp), ofrece instalarlas con
brew (o sudo apt como fallback).

Uso:
  xtool images <archivo|directorio>...    # archivos y directorios (recursivo)
  xtool images                            # busca imágenes en el directorio actual
  xtool images --2x assets/               # escalar 200% y optimizar
  xtool images --to-webp banner.png       # salida convertida a WebP

Flags:
  --2x, --1.5x     Escalar 200% / 150% antes de optimizar
  --scale N        Escala arbitraria (ej. --scale 1.25)
  -q, --quality N  Calidad JPG/WebP, default 82 (en PNG acota pngquant)
  --lossless       Sin pérdida: JPG/PNG solo strip + optimizadores lossless
  --to-webp        Convertir la salida a WebP (foto.jpg → foto-opt.webp)
  --force          Sobrescribir salidas -opt existentes
  --dry            Solo listar qué se haría, sin escribir nada
  --yes            No pedir confirmaciones (ni para instalar herramientas)
  --               Trata el resto de argumentos como rutas

Ejemplos:
  xtool images foto.jpg assets/ otra.png  # varias rutas a la vez
  xtool images --2x --force header.png
  xtool images --to-webp -q 80 banner.png
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

INPUT_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Directorios que se saltan al buscar imágenes (los ocultos ya se saltan solos).
EXCLUDED_DIRS = {"node_modules", "bower_components", "vendor", "venv",
                 "__pycache__", "dist", "build", "target"}

# binario → paquete (mismo nombre en brew y apt, salvo webp).
PACKAGES = {
    "magick": "imagemagick",
    "jpegoptim": "jpegoptim",
    "pngquant": "pngquant",
    "oxipng": "oxipng",
    "cwebp": "webp",
}

_TOOLS = {}  # binario → ruta absoluta; se llena en _ensure_tools()


def _fmt_size(n):
  for unit in ("B", "KB", "MB", "GB"):
    if n < 1024 or unit == "GB":
      return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
    n /= 1024


def _ask(msg):
  try:
    return input(f"{msg} [s/N] ").strip().lower() in ("s", "si", "sí", "y", "yes")
  except (EOFError, KeyboardInterrupt):
    print()
    return False


def _parse(argv):
  """Separa flags de rutas. Devuelve (opts, paths)."""
  opts = {"scale": None, "quality": 82, "lossless": False, "to_webp": False,
          "dry": False, "force": False, "yes": False}
  paths = []
  only_paths = False
  i = 0
  while i < len(argv):
    a = argv[i]
    if only_paths or a == "-" or not a.startswith("-"):
      paths.append(a)
    elif a == "--":
      only_paths = True
    elif a == "--2x":
      opts["scale"] = 2.0
    elif a == "--1.5x":
      opts["scale"] = 1.5
    elif a == "--scale":
      i += 1
      if i >= len(argv):
        raise ValueError("--scale requiere un valor (ej. --scale 1.25)")
      try:
        scale = float(argv[i])
      except ValueError:
        raise ValueError(f"Escala inválida: {argv[i]}")
      if scale <= 0:
        raise ValueError(f"Escala inválida: {argv[i]}")
      opts["scale"] = scale if scale != 1.0 else None
    elif a in ("-q", "--quality"):
      i += 1
      if i >= len(argv):
        raise ValueError("-q requiere un valor (ej. -q 80)")
      try:
        q = int(argv[i])
      except ValueError:
        raise ValueError(f"Calidad inválida: {argv[i]}")
      if not 1 <= q <= 100:
        raise ValueError("La calidad debe estar entre 1 y 100")
      opts["quality"] = q
    elif a == "--lossless":
      opts["lossless"] = True
    elif a == "--to-webp":
      opts["to_webp"] = True
    elif a == "--dry":
      opts["dry"] = True
    elif a == "--force":
      opts["force"] = True
    elif a == "--yes":
      opts["yes"] = True
    else:
      raise ValueError(f"Flag desconocido: {a}")
    i += 1
  return opts, paths


def _scan_images(root: Path):
  """Imágenes recursivas bajo root, sin *-opt.* ni directorios excluidos."""
  found = []
  for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = sorted(d for d in dirnames
                         if not d.startswith(".") and d not in EXCLUDED_DIRS)
    for name in sorted(filenames):
      p = Path(dirpath) / name
      if p.suffix.lower() in INPUT_EXTS and not p.stem.endswith("-opt"):
        found.append(p)
  return sorted(found)


def _collect(paths):
  """Resuelve rutas explícitas (archivos y directorios) a archivos válidos."""
  files, errors = [], []
  for arg in paths:
    p = Path(arg).expanduser()
    if p.is_dir():
      files += _scan_images(p)
    elif p.is_file():
      if p.suffix.lower() in INPUT_EXTS:
        files.append(p)
      else:
        errors.append(f"{arg}: formato no soportado (jpg, png, webp)")
    else:
      errors.append(f"{arg}: no existe")
  uniq = {str(f.resolve()): f for f in files}
  return sorted(uniq.values(), key=lambda f: str(f)), errors


def _dst_for(src: Path, opts):
  ext = ".webp" if opts["to_webp"] else src.suffix.lower()
  tag = f"-{opts['scale']:g}x" if opts["scale"] else ""
  return src.with_name(f"{src.stem}{tag}-opt{ext}")


def _needed_binaries(files, opts):
  need = ["magick"]  # decodifica/redimensiona todo
  exts = {f.suffix.lower() for f in files}
  if opts["to_webp"] or ".webp" in exts:
    need.append("cwebp")
  if not opts["to_webp"]:
    if exts & {".jpg", ".jpeg"}:
      need.append("jpegoptim")
    if ".png" in exts:
      need.append("oxipng")
      if not opts["lossless"]:
        need.append("pngquant")
  return need


def _ensure_tools(need, auto_yes):
  """Verifica los binarios; si faltan, ofrece instalarlos (brew, o sudo apt)."""
  missing = [b for b in need if not shutil.which(b)]
  if not missing:
    _TOOLS.update({b: shutil.which(b) for b in need})
    return True

  pkgs = [PACKAGES[b] for b in missing]
  brew = shutil.which("brew")
  apt = shutil.which("apt-get") or shutil.which("apt")
  if brew:
    cmd = [brew, "install", *pkgs]
    hint = "brew install " + " ".join(pkgs)
  elif apt:
    cmd = ["sudo", apt, "install", "-y", *pkgs]
    hint = "sudo apt install " + " ".join(pkgs)
  else:
    print(f"✗ Faltan herramientas y no hay brew ni apt: {', '.join(missing)}")
    print(f"  Instala a mano: {', '.join(pkgs)}")
    return False

  print(f"✗ Faltan herramientas: {', '.join(missing)}")
  print(f"  {hint}")
  if not auto_yes and not _ask("¿Instalar ahora?"):
    print("Instálalas a mano y vuelve a ejecutar.")
    return False

  print(f"→ Instalando ({' '.join(cmd)})...", flush=True)
  if subprocess.run(cmd).returncode != 0:
    print("✗ Falló la instalación")
    return False

  still = [b for b in missing if not shutil.which(b)]
  if still:
    print(f"✗ Se instaló pero siguen sin encontrarse: {', '.join(still)}")
    print("  Revisa el PATH (ej. ~/.linuxbrew/bin) y vuelve a ejecutar.")
    return False
  _TOOLS.update({b: shutil.which(b) for b in need})
  return True


def _run_tool(cmd):
  r = subprocess.run(cmd, capture_output=True, text=True)
  if r.returncode != 0:
    detail = (r.stderr or r.stdout or "").strip().splitlines()
    raise RuntimeError(detail[-1] if detail else f"exit {r.returncode}")


def _pct(scale):
  return f"{scale * 100:g}%"


def _optimize_jpg(src, dst, opts):
  if opts["scale"]:
    q = 95 if opts["lossless"] else opts["quality"]
    _run_tool([_TOOLS["magick"], str(src), "-resize", _pct(opts["scale"]),
               "-strip", "-quality", str(q), str(dst)])
  else:
    shutil.copy2(src, dst)
  args = [_TOOLS["jpegoptim"], "--strip-all"]
  if not opts["lossless"]:
    args += ["-m", str(opts["quality"])]
  _run_tool([*args, str(dst)])  # jpegoptim optimiza in-place


def _optimize_png(src, dst, opts, tmp):
  if opts["scale"]:
    work = Path(tmp) / "resized.png"
    _run_tool([_TOOLS["magick"], str(src), "-resize", _pct(opts["scale"]),
               "-strip", str(work)])
    base = work
  else:
    base = src
  if opts["lossless"]:
    shutil.copy2(base, dst)
  else:
    q = opts["quality"]
    lo = max(10, min(60, q - 20))
    r = subprocess.run([_TOOLS["pngquant"], f"--quality={lo}-{q}", "--strip",
                        "--force", "--output", str(dst), str(base)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not dst.is_file():
      shutil.copy2(base, dst)  # no cumplió el rango: seguir sin cuantizar
  _run_tool([_TOOLS["oxipng"], "-o", "2", "--strip", "safe", str(dst)])


def _optimize_webp(src, dst, opts, tmp):
  ext = src.suffix.lower()
  if opts["scale"] or ext == ".webp":
    # PNG intermedio sin pérdida (cwebp no acepta webp de entrada).
    work = Path(tmp) / "resized.png"
    margs = [_TOOLS["magick"], str(src)]
    if opts["scale"]:
      margs += ["-resize", _pct(opts["scale"])]
    _run_tool([*margs, "-strip", str(work)])
    base = work
  else:
    base = src  # cwebp acepta png/jpg directamente
  cmd = [_TOOLS["cwebp"], "-quiet"]
  if opts["lossless"]:
    cmd.append("-lossless")
  else:
    cmd += ["-q", str(opts["quality"])]
  _run_tool([*cmd, str(base), "-o", str(dst)])


def _optimize(src, dst, opts, tmp):
  ext = src.suffix.lower()
  if opts["to_webp"] or ext == ".webp":
    _optimize_webp(src, dst, opts, tmp)
  elif ext in (".jpg", ".jpeg"):
    _optimize_jpg(src, dst, opts)
  else:
    _optimize_png(src, dst, opts, tmp)


def main(argv=None):
  argv = sys.argv[1:] if argv is None else list(argv)

  try:
    opts, paths = _parse(argv)
  except ValueError as e:
    print(f"✗ {e}")
    print("Uso: xtool images [--2x|--1.5x|--scale N] [-q N] [--lossless] [--to-webp]")
    print("              [--dry] [--force] [--yes] <archivo|directorio>...")
    return 1

  errors = []
  scan_mode = not paths
  if scan_mode:
    files = _scan_images(Path.cwd())
    if not files:
      print("No se encontraron imágenes (jpg, png, webp) en el directorio actual.")
      return 1
    print(f"Imágenes encontradas en {Path.cwd()}:")
    for f in files:
      print(f"  {os.path.normpath(f)} ({_fmt_size(f.stat().st_size)})")
  else:
    files, errors = _collect(paths)
    for e in errors:
      print(f"✗ {e}")

  work, seen_dst = [], set()
  for src in files:
    dst = _dst_for(src, opts)
    key = str(dst.resolve())
    if key in seen_dst:
      print(f"✗ {os.path.normpath(src)}: colisión de destino con otra imagen ({dst.name})")
      errors.append(dst.name)
    elif dst.exists() and not opts["force"]:
      print(f"– {os.path.normpath(src)} → {dst.name}: ya existe (usar --force)")
    else:
      seen_dst.add(key)
      work.append((src, dst))

  if opts["dry"]:
    if work:
      print("\n--dry: se crearían:")
      for src, dst in work:
        print(f"  {os.path.normpath(src)} → {os.path.normpath(dst)}")
    else:
      print("Nada que hacer.")
    return 1 if errors else 0

  if not work:
    print("Nada que hacer.")
    return 1 if errors else 0

  if scan_mode and not opts["yes"] and not _ask(f"\n¿Optimizar {len(work)} imágenes?"):
    print("Cancelado.")
    return 1

  if not _ensure_tools(_needed_binaries([s for s, _ in work], opts), opts["yes"]):
    return 1

  done, failed = 0, []
  total_in = total_out = 0
  with tempfile.TemporaryDirectory(prefix="xtool-images-") as tmp:
    for src, dst in work:
      rel = os.path.normpath(src)
      try:
        _optimize(src, dst, opts, tmp)
        size_in, size_out = src.stat().st_size, dst.stat().st_size
        total_in, total_out = total_in + size_in, total_out + size_out
        pct = (1 - size_out / size_in) * 100 if size_in else 0.0
        sign = "-" if pct >= 0 else "+"
        print(f"✓ {rel} → {os.path.normpath(dst)}  "
              f"({_fmt_size(size_in)} → {_fmt_size(size_out)}, {sign}{abs(pct):.0f}%)")
        done += 1
      except (RuntimeError, OSError) as e:
        print(f"✗ {rel}: {e}")
        failed.append(rel)

  summary = f"\n✓ {done} optimizada(s) · {_fmt_size(total_in)} → {_fmt_size(total_out)}"
  if total_in:
    pct = (1 - total_out / total_in) * 100
    summary += f" (-{abs(pct):.0f}%)" if pct >= 0 else f" (+{abs(pct):.0f}%)"
  print(summary)
  if failed:
    print(f"✗ {len(failed)} con error")
  return 1 if failed or errors else 0


if __name__ == "__main__":
  sys.exit(main())
