"""Optimiza imágenes (JPG, PNG, WebP, SVG) para web creando copias *-opt junto a la original.

La original nunca se modifica: el resultado lleva el mismo nombre con sufijo
-opt (foto.jpg → foto-opt.jpg). Con --2x/--1.5x se escala primero (retina) y
luego se optimiza (foto.jpg → foto-2x-opt.jpg). Con --width/--height se
redimensiona a un ancho/alto exacto y la otra medida se calcula sola
manteniendo la proporción (foto.jpg → foto-800w-opt.jpg).

Los SVG se rasterizan a PNG (o WebP con --to-webp) al tamaño pedido; sin
tamaño se usa el intrínseco (width/height o viewBox). Como un SVG escala a
cualquier tamaño, --info muestra su proporción y medidas sugeridas.
Se rasteriza con rsvg-convert (librsvg): el renderizador interno de
ImageMagick no soporta buena parte del SVG real (stroke-dasharray, CSS...).
Los SVG con <foreignObject> (ej. diagramas de Mermaid, cuyos textos son
HTML) se renderizan con Chrome/Chromium headless, el único que los dibuja.

Si faltan herramientas (imagemagick, jpegoptim, pngquant, oxipng, webp),
ofrece instalarlas con brew (o sudo apt como fallback).

Uso:
  xtool images <archivo|directorio>...    # archivos y directorios (recursivo)
  xtool images                            # busca imágenes en el directorio actual
  xtool images --2x assets/               # escalar 200% y optimizar
  xtool images --to-webp banner.png       # salida convertida a WebP
  xtool images --info logo.svg            # proporción y medidas sugeridas
  xtool images -w 512 logo.svg            # 512 de ancho, alto proporcional

Flags:
  --2x, --1.5x     Escalar 200% / 150% antes de optimizar
  --scale N        Escala arbitraria (ej. --scale 1.25)
  -w, --width N    Ancho final en px; el alto se calcula proporcional
  -H, --height N   Alto final en px; el ancho se calcula proporcional
                   (con ambos: encaja dentro de NxM sin deformar)
  --info           Solo mostrar dimensiones, proporción y medidas sugeridas
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
  xtool images -H 64 --to-webp icono.svg  # 64 de alto, ancho proporcional
"""

import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

INPUT_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".svg"}

# Directorios que se saltan al buscar imágenes (los ocultos ya se saltan solos).
EXCLUDED_DIRS = {"node_modules", "bower_components", "vendor", "venv",
                 "__pycache__", "dist", "build", "target"}

# binario → paquete; str si coincide en brew y apt, si no (brew, apt).
PACKAGES = {
    "magick": "imagemagick",
    "jpegoptim": "jpegoptim",
    "pngquant": "pngquant",
    "oxipng": "oxipng",
    "cwebp": "webp",
    "rsvg-convert": ("librsvg", "librsvg2-bin"),
}


def _pkg(binary, manager):
  pkg = PACKAGES[binary]
  if isinstance(pkg, tuple):
    return pkg[0] if manager == "brew" else pkg[1]
  return pkg

# Navegadores para SVG con <foreignObject>, en orden de preferencia.
BROWSERS = ("google-chrome", "google-chrome-stable", "chromium",
            "chromium-browser", "chrome", "microsoft-edge")

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
  opts = {"scale": None, "width": None, "height": None, "quality": 82,
          "lossless": False, "to_webp": False, "info": False,
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
    elif a in ("-w", "--width", "-H", "--height"):
      key = "width" if a in ("-w", "--width") else "height"
      i += 1
      if i >= len(argv):
        raise ValueError(f"{a} requiere un valor en px (ej. {a} 800)")
      try:
        n = int(argv[i])
      except ValueError:
        raise ValueError(f"Valor inválido para {a}: {argv[i]} (entero en px)")
      if n <= 0:
        raise ValueError(f"Valor inválido para {a}: {argv[i]}")
      opts[key] = n
    elif a == "--info":
      opts["info"] = True
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
  if opts["scale"] and (opts["width"] or opts["height"]):
    raise ValueError("--scale/--2x no se combina con --width/--height")
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
        errors.append(f"{arg}: formato no soportado (jpg, png, webp, svg)")
    else:
      errors.append(f"{arg}: no existe")
  uniq = {str(f.resolve()): f for f in files}
  return sorted(uniq.values(), key=lambda f: str(f)), errors


def _is_svg(p: Path):
  return p.suffix.lower() == ".svg"


def _size_tag(opts):
  w, h = opts["width"], opts["height"]
  if w and h:
    return f"-{w}x{h}"
  if w:
    return f"-{w}w"
  if h:
    return f"-{h}h"
  if opts["scale"]:
    return f"-{opts['scale']:g}x"
  return ""


def _dst_for(src: Path, opts):
  if opts["to_webp"]:
    ext = ".webp"
  elif _is_svg(src):
    ext = ".png"  # el SVG se rasteriza
  else:
    ext = src.suffix.lower()
  return src.with_name(f"{src.stem}{_size_tag(opts)}-opt{ext}")


# ── Dimensiones ──────────────────────────────────────────────────────────────

# Unidades CSS absolutas → px (96 dpi). em/ex con fuente base de 16px.
_UNITS = {"": 1.0, "px": 1.0, "pt": 96 / 72, "pc": 16.0, "in": 96.0,
          "cm": 96 / 2.54, "mm": 96 / 25.4, "q": 96 / 101.6,
          "em": 16.0, "ex": 8.0}
_LENGTH_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+(?:e[-+]?\d+)?)\s*([a-z%]*)\s*$", re.I)


def _svg_length(value):
  """Convierte un width/height de SVG a px. None si falta o es relativo (%)."""
  if not value:
    return None
  m = _LENGTH_RE.match(value)
  if not m or m.group(2).lower() not in _UNITS:
    return None
  n = float(m.group(1)) * _UNITS[m.group(2).lower()]
  return n if n > 0 else None


def _svg_size(path: Path):
  """Tamaño intrínseco (w, h) en px de un SVG, o None si no se puede deducir.

  Prioridad: width+height absolutos; si solo hay uno, el otro sale del
  viewBox; si no hay ninguno, el propio viewBox.
  """
  try:
    for _, el in ET.iterparse(path, events=("start",)):
      root = el
      break
    else:
      return None
  except (ET.ParseError, OSError):
    return None
  w, h = _svg_length(root.get("width")), _svg_length(root.get("height"))
  vb = None
  parts = re.split(r"[\s,]+", (root.get("viewBox") or "").strip())
  if len(parts) == 4:
    try:
      vw, vh = float(parts[2]), float(parts[3])
      if vw > 0 and vh > 0:
        vb = (vw, vh)
    except ValueError:
      pass
  if w and h:
    return w, h
  if vb:
    if w:
      return w, w * vb[1] / vb[0]
    if h:
      return h * vb[0] / vb[1], h
    return vb
  return None


def _svg_needs_browser(path: Path):
  """True si el SVG usa <foreignObject> (HTML embebido: solo lo pinta un navegador)."""
  try:
    return "<foreignObject" in path.read_text(encoding="utf-8", errors="ignore")
  except OSError:
    return False


def _find_browser():
  return next((b for b in map(shutil.which, BROWSERS) if b), None)


def _raster_size(path: Path):
  r = subprocess.run([_TOOLS.get("magick") or "magick", "identify", "-format",
                      "%w %h\n", str(path)], capture_output=True, text=True)
  try:
    w, h = r.stdout.split()[:2]  # primer frame
    return float(w), float(h)
  except ValueError:
    return None


def _image_size(path: Path):
  return _svg_size(path) if _is_svg(path) else _raster_size(path)


def _target_size(size, opts):
  """Tamaño final (w, h) en px enteros según --width/--height/--scale."""
  w0, h0 = size
  w, h = opts["width"], opts["height"]
  if w and h:  # encajar dentro de la caja sin deformar
    f = min(w / w0, h / h0)
  elif w:
    f = w / w0
  elif h:
    f = h / h0
  else:
    f = opts["scale"] or 1.0
  return max(1, round(w0 * f)), max(1, round(h0 * f))


def _ratio(w, h):
  """Proporción legible: '16:9' si es exacta en enteros chicos, si no decimal."""
  wi, hi = round(w), round(h)
  if abs(w - wi) < 1e-6 and abs(h - hi) < 1e-6 and wi and hi:
    g = math.gcd(wi, hi)
    a, b = wi // g, hi // g
    if a <= 64 and b <= 64:
      return f"{a}:{b}"
  return f"{w / h:.3f}:1"


def _fmt_px(n):
  return f"{n:g}" if abs(n - round(n)) < 0.01 else f"{n:.2f}"


def _print_info(path: Path, opts):
  rel = os.path.normpath(path)
  size = _image_size(path)
  if not size:
    print(f"✗ {rel}: no se pudieron leer las dimensiones"
          + (" (sin width/height ni viewBox)" if _is_svg(path) else ""))
    return False
  w, h = size
  kind = "SVG, escalable" if _is_svg(path) else _fmt_size(path.stat().st_size)
  print(f"{rel}  ({kind})")
  print(f"  Intrínseco: {_fmt_px(w)}×{_fmt_px(h)} px · proporción {_ratio(w, h)}"
        f" (ancho/alto = {w / h:.4f})")
  if _is_svg(path):
    mult = "  ".join(f"{k:g}x {round(w * k)}×{round(h * k)}" for k in (1, 1.5, 2, 3))
    print(f"  Retina:     {mult}")
    widths = [n for n in (64, 128, 256, 512, 1024, 2048)]
    print("  Por ancho:  " + "  ".join(f"{n}×{round(n * h / w)}" for n in widths))
    heights = [n for n in (16, 32, 48, 64, 128, 256)]
    print("  Por alto:   " + "  ".join(f"{round(n * w / h)}×{n}" for n in heights))
  if opts["width"] or opts["height"] or opts["scale"]:
    tw, th = _target_size(size, opts)
    print(f"  Con tus flags → {tw}×{th} px")
  print(f"  Fórmulas:   alto = ancho × {h / w:.4f}   ·   ancho = alto × {w / h:.4f}")
  return True


def _needed_binaries(files, opts):
  need = ["magick"]  # decodifica/redimensiona todo
  exts = {f.suffix.lower() for f in files}
  if any(_is_svg(f) and not _svg_needs_browser(f) for f in files):
    need.append("rsvg-convert")
  if opts["to_webp"] or ".webp" in exts:
    need.append("cwebp")
  if not opts["to_webp"]:
    if exts & {".jpg", ".jpeg"}:
      need.append("jpegoptim")
    if exts & {".png", ".svg"}:
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

  brew = shutil.which("brew")
  apt = shutil.which("apt-get") or shutil.which("apt")
  pkgs = [_pkg(b, "brew" if brew else "apt") for b in missing]
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


def _resize_geom(opts):
  """Geometría de ImageMagick para -resize, o None si no hay que escalar."""
  w, h = opts["width"], opts["height"]
  if w or h:
    return f"{w or ''}x{h or ''}"  # 800x · x600 · 800x600 (encaja, sin deformar)
  if opts["scale"]:
    return f"{opts['scale'] * 100:g}%"
  return None


def _no_resize(opts):
  return {**opts, "scale": None, "width": None, "height": None}


def _optimize_jpg(src, dst, opts):
  if _resize_geom(opts):
    q = 95 if opts["lossless"] else opts["quality"]
    _run_tool([_TOOLS["magick"], str(src), "-resize", _resize_geom(opts),
               "-strip", "-quality", str(q), str(dst)])
  else:
    shutil.copy2(src, dst)
  args = [_TOOLS["jpegoptim"], "--strip-all"]
  if not opts["lossless"]:
    args += ["-m", str(opts["quality"])]
  _run_tool([*args, str(dst)])  # jpegoptim optimiza in-place


def _optimize_png(src, dst, opts, tmp):
  if _resize_geom(opts):
    work = Path(tmp) / "resized.png"
    _run_tool([_TOOLS["magick"], str(src), "-resize", _resize_geom(opts),
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
  if _resize_geom(opts) or ext == ".webp":
    # PNG intermedio sin pérdida (cwebp no acepta webp de entrada).
    work = Path(tmp) / "resized.png"
    margs = [_TOOLS["magick"], str(src)]
    if _resize_geom(opts):
      margs += ["-resize", _resize_geom(opts)]
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


def _render_svg(src, out, opts):
  """Rasteriza un SVG a PNG (fondo transparente) al tamaño final pedido."""
  size = _svg_size(src)
  if size:
    tw, th = _target_size(size, opts)
  elif opts["width"] and opts["height"]:
    tw, th = opts["width"], opts["height"]
  else:
    raise RuntimeError("SVG sin width/height ni viewBox: indica --width y --height")
  if _svg_needs_browser(src):
    _render_svg_browser(src, out, tw, th)
  else:
    # Fondo transparente por defecto; -w/-h exactos (ya proporcionales).
    _run_tool([_TOOLS["rsvg-convert"], "-w", str(tw), "-h", str(th),
               "-f", "png", "-o", str(out), str(src)])


def _render_svg_browser(src, out, tw, th):
  """Captura el SVG con Chrome headless a tw×th exactos, fondo transparente."""
  browser = _find_browser()
  if not browser:
    raise RuntimeError("usa <foreignObject> (HTML embebido, ej. Mermaid) y solo "
                       "un navegador lo dibuja: instala Chrome o Chromium")
  work = out.parent / "svg-browser"
  work.mkdir(exist_ok=True)
  page = work / "page.html"
  page.write_text(
      "<!doctype html><html><head><style>"
      "html,body{margin:0;background:transparent;overflow:hidden}"
      f"img{{display:block;width:{tw}px;height:{th}px}}"
      f'</style></head><body><img src="{src.resolve().as_uri()}"></body></html>',
      encoding="utf-8")
  if out.exists():
    out.unlink()
  _run_tool([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--no-first-run", "--no-default-browser-check",
             f"--user-data-dir={work / 'profile'}", "--force-device-scale-factor=1",
             "--default-background-color=00000000", f"--window-size={tw},{th}",
             f"--screenshot={out}", page.as_uri()])
  if not out.is_file():
    raise RuntimeError(f"{Path(browser).name} no generó la captura")


def _optimize(src, dst, opts, tmp):
  ext = src.suffix.lower()
  if ext == ".svg":
    png = Path(tmp) / "svg-render.png"
    _render_svg(src, png, opts)
    plain = _no_resize(opts)  # ya está al tamaño final
    if opts["to_webp"]:
      _optimize_webp(png, dst, plain, tmp)
    else:
      _optimize_png(png, dst, plain, tmp)
  elif opts["to_webp"] or ext == ".webp":
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
    print("Uso: xtool images [--2x|--1.5x|--scale N|-w N|-H N] [-q N] [--lossless]")
    print("              [--to-webp] [--info] [--dry] [--force] [--yes] <archivo|directorio>...")
    return 1

  errors = []
  scan_mode = not paths
  if scan_mode:
    files = _scan_images(Path.cwd())
    if not files:
      print("No se encontraron imágenes (jpg, png, webp, svg) en el directorio actual.")
      return 1
    if not opts["info"]:
      print(f"Imágenes encontradas en {Path.cwd()}:")
      for f in files:
        print(f"  {os.path.normpath(f)} ({_fmt_size(f.stat().st_size)})")
  else:
    files, errors = _collect(paths)
    for e in errors:
      print(f"✗ {e}")

  if opts["info"]:
    if any(not _is_svg(f) for f in files) and not _ensure_tools(["magick"], opts["yes"]):
      return 1
    ok = True
    for i, f in enumerate(files):
      if i:
        print()
      ok = _print_info(f, opts) and ok
    return 0 if ok and not errors and files else 1

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
        dims = _raster_size(dst)
        dims = f"{dims[0]:g}×{dims[1]:g}, " if dims else ""
        if _is_svg(src):
          # Vector → raster: comparar pesos no tiene sentido, fuera del total.
          print(f"✓ {rel} → {os.path.normpath(dst)}  ({dims}{_fmt_size(size_out)})")
        else:
          total_in, total_out = total_in + size_in, total_out + size_out
          pct = (1 - size_out / size_in) * 100 if size_in else 0.0
          sign = "-" if pct >= 0 else "+"
          print(f"✓ {rel} → {os.path.normpath(dst)}  "
                f"({dims}{_fmt_size(size_in)} → {_fmt_size(size_out)}, {sign}{abs(pct):.0f}%)")
        done += 1
      except (RuntimeError, OSError) as e:
        print(f"✗ {rel}: {e}")
        failed.append(rel)

  summary = f"\n✓ {done} optimizada(s)"
  if total_in:
    summary += f" · {_fmt_size(total_in)} → {_fmt_size(total_out)}"
    pct = (1 - total_out / total_in) * 100
    summary += f" (-{abs(pct):.0f}%)" if pct >= 0 else f" (+{abs(pct):.0f}%)"
  print(summary)
  if failed:
    print(f"✗ {len(failed)} con error")
  return 1 if failed or errors else 0


if __name__ == "__main__":
  sys.exit(main())
