"""Recupera el <title> de una lista de páginas y detecta cambios entre corridas.

Uso:
  xtool titles <base_url> </ruta...>          # rutas por parámetro
  xtool titles --set <nombre>                 # lista definida en el YAML
  xtool titles --set ig https://sbox-...      # misma lista, otra base_url
  xtool titles                                # set 'default' del YAML
  xtool titles --pages <url...>               # lista custom de URLs completas

Ejemplos:
  xtool titles https://www.solocruceros.com /minicruceros /cruceros-desde-malaga
  xtool titles --pages https://www.solocruceros.com/minicruceros https://www.solocruceros.com/cruceros-desde-malaga
  xtool titles --pages "Málaga|https://www.solocruceros.com/cruceros-desde-malaga"
  xtool titles https://www.solocruceros.com "Málaga|/cruceros-desde-malaga"
  xtool titles --set desde --track            # compara con la corrida anterior
  xtool titles --set ig -o ~/Desktop/titles.json
  xtool titles --set ig --compare ~/Desktop/titles.json
  xtool titles --pages "Home|https://dominio.com/" https://otro.com/x --track

Argumentos posicionales:
  http(s)://...      base_url (sobrescribe la del set)
  /ruta              ruta relativa a base_url
  "Nombre|/ruta"     ruta con nombre; "Nombre|https://..." usa la URL tal cual
  Si se pasan rutas (o --pages), reemplazan a las del set (base_url se conserva).

Flags:
  -c, --config <f>   YAML de configuración (default: ~/.config/xtool/titles.yaml
                     o la variable de entorno XTOOL_TITLES_CONFIG)
  -s, --set <nombre> set del YAML a revisar (default: 'default' si existe)
  -p, --pages        todos los posicionales son páginas (no se toma el primero
                     como base_url). Admite URLs completas, "Nombre|URL" y
                     /rutas (estas usan la base_url de --set si se indica).
  --list             lista los sets configurados
  --init             crea el YAML de ejemplo si no existe
  -o, --out <f>      guarda el resultado JSON en <f>
  --compare <f>      compara con un JSON previo y muestra los títulos cambiados
  --track            compara con la última corrida guardada de ese set/base_url
                     (~/.local/state/xtool/titles/) y la actualiza
  --json             imprime JSON aunque haya comparación (por defecto: tabla)
  --timeout <seg>    timeout por petición (default: 15)

Con --compare/--track el código de salida es 1 si algún título cambió
(útil para scripts). Páginas sin <title> se avisan por stderr.

Formato del YAML:
  default: mediterraneo          # set por defecto (opcional)
  sets:
    desde:
      base_url: https://www.solocruceros.com
      rutas:
        - /minicruceros
        - Málaga|/cruceros-desde-malaga
        - {name: Miami, path: /cruceros-desde-miami}
"""

import contextlib
import html
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

ENV_CONFIG = "XTOOL_TITLES_CONFIG"
CONFIG_DEFAULT = Path.home() / ".config" / "xtool" / "titles.yaml"
STATE_DIR = Path.home() / ".local" / "state" / "xtool" / "titles"
USER_AGENT = "xtool-titles/1.0"

EJEMPLO_CONFIG = """\
# Configuración de `xtool titles`.
# Cada ruta puede ser:
#   - /ruta                       (el nombre se deriva de la ruta)
#   - Nombre|/ruta
#   - Nombre|https://url-completa (ignora base_url)
#   - {name: Nombre, path: /ruta}

default: desde

sets:
  desde:
    base_url: https://www.solocruceros.com
    rutas:
      - /minicruceros
      - /cruceros-desde-malaga
      - /cruceros-desde-espana
      - /cruceros-desde-estocolmo
      - /cruceros-desde-miami
      - /cruceros-desde-fort-lauderdale

  mediterraneo:
    base_url: http://scme.local
    rutas:
      - Cruceros Familias|/cruceros-familias
      - Cruceros Baratos|/cruceros-baratos
      - Cruceros Premium|/cruceros-premium
      - Cruceros de Lujo|/lujo
      - Cruceros Novios|/novios
      - Cruceros Todo Incluido|/cruceros-todo-incluido
      - Minicruceros|/minicruceros
      - Última hora|/cruceros-ultima-hora
      - Primavera|/cruceros-primavera
      - Verano|/cruceros-verano
      - Otoño|/cruceros-otono
      - Invierno|/cruceros-invierno
      - Navidad y Fin de Año|/cruceros-navidad-y-fin-de-ano
      - Cruceros Semana Santa|/cruceros-semana-santa

  ig:
    base_url: http://scme.local
    rutas:
      - Cruceros Familias|/cruceros-familias
      - Cruceros Baratos|/cruceros-baratos
      - Cruceros Premium|/cruceros-premium
      - Cruceros de Lujo|/cruceros-de-lujo
      - Cruceros Novios|/cruceros-novios
      - Cruceros Todo Incluido|/cruceros-todo-incluido
      - Minicruceros|/minicruceros
      - Última hora|/ultima-hora
      - Primavera|/primavera
      - Verano|/verano
      - Otoño|/otono
      - Invierno|/invierno
      - Navidad y Fin de Año|/cruceros-navidad-y-fin-de-ano
      - Cruceros Semana Santa|/semana-santa
      - Cruceros 2026|/cruceros-2026
      - Cruceros 2027|/cruceros-2027
      - Cruceros 2028|/cruceros-2028
"""

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def err(msg):
  print(msg, file=sys.stderr)


def mostrar_ruta(ruta: Path) -> str:
  return str(ruta).replace(str(Path.home()), "~", 1)


def ruta_config(arg):
  return Path(arg or os.environ.get(ENV_CONFIG, "") or CONFIG_DEFAULT).expanduser()


def cargar_yaml(ruta: Path):
  """Lee el YAML. Devuelve el dict o None si no existe / es inválido."""
  if not ruta.is_file():
    return None
  try:
    import yaml
  except ImportError:
    err("ERROR: falta PyYAML (ejecuta 'uv tool upgrade scripts')")
    return None
  try:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
  except (yaml.YAMLError, OSError) as e:
    err(f"ERROR: no se pudo leer {mostrar_ruta(ruta)}: {e}")
    return None
  if not isinstance(datos, dict) or not isinstance(datos.get("sets", {}), dict):
    err(f"ERROR: {mostrar_ruta(ruta)} debe tener un objeto 'sets'")
    return None
  return datos


def nombre_desde_ruta(path: str) -> str:
  u = urlparse(path)
  seg = u.path.strip("/").split("/")[-1] or u.netloc or path
  return seg.replace("-", " ").capitalize()


def parsear_entrada(e):
  """Convierte una entrada (str 'Nombre|/ruta', '/ruta' o dict) en (name, path)."""
  if isinstance(e, dict):
    path = str(e.get("path") or e.get("ruta") or e.get("url") or "").strip()
    name = str(e.get("name") or e.get("nombre") or "").strip()
  else:
    s = str(e).strip()
    name, _, path = s.rpartition("|") if "|" in s else ("", "", s)
    name, path = name.strip(), path.strip()
  if not path:
    return None
  return name or nombre_desde_ruta(path), path


def construir_url(base_url, path):
  if path.startswith(("http://", "https://")):
    return path
  if not base_url:
    return None
  if not path.startswith("/"):
    path = "/" + path
  return base_url + path


def obtener_title(url, timeout):
  """Devuelve (title, error). title vacío si no hay <title>."""
  import requests
  try:
    r = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
  except requests.RequestException as e:
    return "", f"{type(e).__name__}"
  if not r.encoding or r.encoding.lower() == "iso-8859-1":
    r.encoding = r.apparent_encoding or "utf-8"
  m = TITLE_RE.search(r.text)
  title = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""
  return title, (None if r.ok else f"HTTP {r.status_code}")


def clave_track(set_name, base_url):
  host = urlparse(base_url or "").netloc or "sin-base"
  nombre = f"{set_name or 'cli'}__{host}"
  return STATE_DIR / (re.sub(r"[^A-Za-z0-9._-]+", "_", nombre) + ".json")


def leer_previo(ruta: Path):
  try:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
  except FileNotFoundError:
    return None
  except (json.JSONDecodeError, OSError) as e:
    err(f"AVISO: no se pudo leer {mostrar_ruta(ruta)}: {e}")
    return None
  return {d.get("url"): d.get("title", "") for d in datos if isinstance(d, dict)}


def comparar(resultados, previo):
  """Imprime los cambios. Devuelve True si hubo alguno."""
  cambios = 0
  for r in resultados:
    antes = previo.get(r["url"])
    if antes is None:
      print(f"  NUEVA     {r['name']}  ({r['url']})\n            {r['title'] or '(sin title)'}")
      cambios += 1
    elif antes != r["title"]:
      print(f"  CAMBIÓ    {r['name']}  ({r['url']})\n    antes:  {antes or '(sin title)'}\n    ahora:  {r['title'] or '(sin title)'}")
      cambios += 1
  actuales = {r["url"] for r in resultados}
  for url in previo:
    if url not in actuales:
      print(f"  QUITADA   {url}")
  if cambios:
    print(f"\n{cambios} cambio(s) de {len(resultados)} página(s).")
  else:
    print(f"Sin cambios en {len(resultados)} página(s).")
  return cambios > 0


def imprimir_tabla(resultados):
  ancho = max((len(r["name"]) for r in resultados), default=0)
  for r in resultados:
    print(f"  {r['name'].ljust(ancho)}  {r['title'] or '(sin title)'}")


def _reportar(compare, referencia, previo, resultados):
  """Muestra la comparación. True/False según cambios; None si falta --compare."""
  if previo is None:
    if compare:
      err(f"ERROR: no existe {mostrar_ruta(compare)}")
      return None
    print(f"Primera corrida para este set; se guarda la referencia en {mostrar_ruta(referencia)}")
    imprimir_tabla(resultados)
    return False
  print(f"Comparando con {mostrar_ruta(referencia)}")
  return comparar(resultados, previo)


def main(argv=None):
  argv = sys.argv[1:] if argv is None else list(argv)

  config_arg = set_name = out = compare = None
  track = as_json = listar = init = False
  pages_mode = "-p" in argv or "--pages" in argv
  timeout = 15.0
  base_cli = None
  rutas_cli = []

  con_valor = {"-c", "--config", "-s", "--set", "-o", "--out", "--compare", "--timeout"}
  i = 0
  while i < len(argv):
    a = argv[i]
    if a in ("-h", "--help"):
      print((__doc__ or "").strip())
      return 0
    if "=" in a and a.split("=", 1)[0] in con_valor:
      a, valor = a.split("=", 1)
    elif a in con_valor:
      if i + 1 >= len(argv):
        err(f"ERROR: {a} necesita un valor")
        return 1
      valor = argv[i + 1]
      i += 1
    else:
      valor = None

    if a in ("-c", "--config"):
      config_arg = valor
    elif a in ("-s", "--set"):
      set_name = valor
    elif a in ("-o", "--out"):
      out = Path(valor).expanduser()
    elif a == "--compare":
      compare = Path(valor).expanduser()
    elif a == "--timeout":
      try:
        timeout = float(valor)
      except ValueError:
        err("ERROR: --timeout requiere un número")
        return 1
    elif a == "--track":
      track = True
    elif a == "--json":
      as_json = True
    elif a == "--list":
      listar = True
    elif a == "--init":
      init = True
    elif a in ("-p", "--pages"):
      pass  # ya resuelto antes del bucle
    elif a.startswith("-") and a != "-":
      err(f"ERROR: opción desconocida: {a}")
      return 1
    elif (not pages_mode and a.startswith(("http://", "https://")) and "|" not in a
          and base_cli is None and not rutas_cli):
      base_cli = a
    else:
      rutas_cli.append(a)
    i += 1

  cfg_path = ruta_config(config_arg)

  if init:
    if cfg_path.exists():
      err(f"Ya existe {mostrar_ruta(cfg_path)} (no se sobrescribe)")
      return 1
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(EJEMPLO_CONFIG, encoding="utf-8")
    print(f"Creado {mostrar_ruta(cfg_path)}")
    return 0

  cfg = cargar_yaml(cfg_path)
  sets = (cfg or {}).get("sets", {}) or {}

  if listar:
    if not sets:
      err(f"No hay sets en {mostrar_ruta(cfg_path)} (crea uno con 'xtool titles --init')")
      return 1
    por_defecto = (cfg or {}).get("default")
    for nombre, s in sets.items():
      s = s or {}
      marca = " (default)" if nombre == por_defecto else ""
      print(f"  {nombre}{marca}: {s.get('base_url', '-')}  [{len(s.get('rutas') or [])} rutas]")
    return 0

  # ─── Resolver set / base_url / rutas ─────────────────────────────────
  if set_name is None and not rutas_cli and cfg:
    set_name = cfg.get("default") or (next(iter(sets)) if len(sets) == 1 else None)
  conf_set = {}
  if set_name is not None:
    if set_name not in sets:
      err(f"ERROR: set '{set_name}' no existe en {mostrar_ruta(cfg_path)} "
          f"(disponibles: {', '.join(sets) or 'ninguno'})")
      return 1
    conf_set = sets[set_name] or {}

  base_url = (base_cli or conf_set.get("base_url") or "").rstrip("/")
  entradas = rutas_cli or conf_set.get("rutas") or []
  if not entradas:
    err("ERROR: no hay rutas que revisar. Pásalas como argumentos o usa --set "
        f"(config: {mostrar_ruta(cfg_path)}; créala con 'xtool titles --init').")
    return 1

  paginas = []
  for e in entradas:
    p = parsear_entrada(e)
    if p is None:
      err(f"AVISO: entrada inválida ignorada: {e!r}")
      continue
    name, path = p
    url = construir_url(base_url, path)
    if url is None:
      err(f"ERROR: '{path}' es relativa y no hay base_url")
      return 1
    paginas.append({"name": name, "url": url})

  # ─── Peticiones en paralelo ──────────────────────────────────────────
  with ThreadPoolExecutor(max_workers=8) as pool:
    respuestas = list(pool.map(lambda p: obtener_title(p["url"], timeout), paginas))

  resultados = []
  for p, (title, error) in zip(paginas, respuestas):
    if error or not title:
      err(f"AVISO: sin <title> en {p['url']}" + (f" ({error})" if error else ""))
    resultados.append({**p, "title": title})

  salida_json = json.dumps(resultados, ensure_ascii=False, indent=2) + "\n"
  if out:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(salida_json, encoding="utf-8")
    err(f"Guardado en {mostrar_ruta(out)}")

  # ─── Comparación ─────────────────────────────────────────────────────
  hubo_cambios = False
  base_track = base_url or (paginas[0]["url"] if paginas else "")
  referencia = compare or (clave_track(set_name, base_track) if track else None)
  if referencia is not None:
    previo = leer_previo(referencia)
    if as_json:
      sys.stdout.write(salida_json)
      sys.stdout.flush()
    with contextlib.redirect_stdout(sys.stderr if as_json else sys.stdout):
      hubo_cambios = _reportar(compare, referencia, previo, resultados)
    if hubo_cambios is None:
      return 1
    if track:
      referencia.parent.mkdir(parents=True, exist_ok=True)
      referencia.write_text(salida_json, encoding="utf-8")
    return 1 if hubo_cambios else 0

  if out and not as_json:
    imprimir_tabla(resultados)
  else:
    sys.stdout.write(salida_json)
  return 0


if __name__ == "__main__":
  sys.exit(main())
