#!/usr/bin/env python3
"""Separa los cambios de una rama en ramas satélite por servidor web (slices).

Uso (desde el monorepo, idealmente sobre la rama que tiene TODOS los cambios):
  xtool git-separe

Flujo interactivo:

  1. destino: rama actual por defecto (cámbiala con --destino). Es la rama
     que contiene todos los cambios de la tarea.
  2. origen: autodetección de la rama base. Candidatas: las bases del repo
     (master, o main si no existe master) y, si el destino coincide con el
     patrón <prefijo-id>/<nombre> (p.ej. feat-44913/replicate-home-layout-
     search), las ramas con el MISMO prefijo feat-44913/* (excluyendo el
     propio destino, sus slices y las que terminan en un alias de satélite,
     que serían slices viejos). Se priorizan las ancestros del destino cuyo
     nombre tenga un hint (origin/main/master/base); la mejor es el default
     del prompt — p.ej. sin más ramas feat-44913/* el origen será master y
     los slices nacen de él (el diff capturado es destino..master).
  3. Plan: detecta en qué monorepo estás (p.ej. europa/latam) localizando
     los satélites de ~/.config/xtool/git-separe.json en el checkout: la
     ruta tal cual o, si el layout difiere (en latam el sitio cuelga de
     solocruceros.com/), buscándola por nombre con git ls-files (--repo
     fuerza la sección). Calcula cambios por satélite (alias -> ruta real
     relativa a la raíz del repo) y avisa de los archivos que quedan FUERA
     de todos los satélites (no entrarían en ningún slice).
  4. Crea una rama slice por satélite desde <origen> aplicando SOLO los
     cambios de su ruta: git diff --binary origen..destino -- ruta |
     git apply --index. Nombre del slice: con destino <prefijo-id>/<nombre>
     el alias se mete tras el id (feat-44913/<alias>/<nombre>); sin patrón,
     <destino>-sat/<alias>. NO puede ser <destino>/<alias>: git no permite
     que coexistan las ramas 'X' y 'X/algo' (y el destino vive hasta que se
     fusionan todos los slices). Tras commitear VERIFICA que el contenido
     de la ruta en el slice sea idéntico al del destino; si difiere lo
     avoca ruidosamente. Con --force, ANTES se borran las slices previas
     de este destino generadas por este script (las reconoce por el
     marcador en su commit; las ramas ajenas con nombre coincidente no se
     tocan): las que siguen teniendo cambios se recrean y se republican
     con --force-with-lease; las que quedaron sin cambios (todo fusionado
     en el origen) se borran también del remote.
  5. Vuelve a la rama original y pushea las slices creadas al remote
     (default "origin", configurable como "remote" en el JSON). Con
     --no-push las deja solo locales e imprime el comando para publicarlas.
     Al final, en cualquier caso, lista las ramas creadas.

Opciones:
  --destino <rama>   rama con todos los cambios (default: rama actual)
  --origen <rama>    rama base limpia (default: autodetección interactiva)
  --repo <id>        fuerza la sección 'repos' de la config (p.ej. latam);
                     default: autodetección por rutas de satélite existentes
  --sat a=ruta       agrega/sobrescribe un satélite (repetible),
                     p.ej. --sat ltp=DDD/1_Presentation/Web/latampass
  --dry-run          solo muestra el plan, no crea nada
  --force            re-slice: borra las slices previas de este destino
                     (local y remote) y las recrea con el diff actual —
                     el flujo ante cambios posteriores
  --no-push          NO publica las slices tras crearlas (default: pushea)
  -y/--yes           no pregunta (falla si no puede autodetectar el origen)

Requiere git ≥ 2.5 (usa un worktree temporal aislado para no tocar tu
working tree: puedes tener cambios sin commitear, se ignoran — los slices
solo capturan lo COMMITEADO entre origen y destino).

Configuración en ~/.config/xtool/git-separe.json (o la ruta de la variable
de entorno GIT_SEPARE_CONFIG); se crea con defaults la primera vez:

  {
    "remote": "origin",
    "repos": {
      "europa": {
        "satelites": {
          "me":    "DDD/1_Presentation/Web/symfony_mediterraneo",
          "sc":    "DDD/1_Presentation/Web/symfony_home",
          "islas": "DDD/1_Presentation/Web/symfony_islasgriegas",
          "lujo":  "DDD/1_Presentation/Web/symfony_lujo"
        }
      },
      "latam": {
        "satelites": {
          "cl":    "DDD/1_Presentation/Web/symfony_chile",
          "cr":    "DDD/1_Presentation/Web/symfony_costarica",
          "mx":    "DDD/1_Presentation/Web/symfony_mexico",
          "co":    "DDD/1_Presentation/Web/symfony_colombia"
        }
      }
    }
  }

- remote: a dónde se publican las slices (default "origin").
- repos: una sección por monorepo; se usa la que tenga MÁS rutas de
  satélite presentes en el checkout actual (--repo fuerza una concreta;
  si no existe ninguna ruta, error). El formato antiguo ('satelites'
  plano) sigue funcionando como repo único.

Cada rama slice se llama <prefijo-id>/<alias>/<nombre> (p.ej.
feat-44913/me/replicate-home-layout-search) o, si el destino no tiene el
patrón, <destino>-sat/<alias>; no se configura (ver flujo paso 4). La
clave antigua "sufijo_slice" se ignora si aún figura en el JSON.

Después de fusionar TODOS los slices a master, borra la rama destino:
jamás la fusiones después de sus slices (son los mismos cambios con
commits distintos => conflictos duplicados).
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from xtool.common.git_transport import out, run

ENV_CONFIG = "GIT_SEPARE_CONFIG"
CONFIG_DEFAULT = Path.home() / ".config" / "xtool" / "git-separe.json"

SAT_DEFECTO_EUROPA = {
  "me": "DDD/1_Presentation/Web/symfony_mediterraneo",
  "sc": "DDD/1_Presentation/Web/symfony_home",
  "islas": "DDD/1_Presentation/Web/symfony_islasgriegas",
  "lujo": "DDD/1_Presentation/Web/symfony_lujo",
}

SAT_DEFECTO_LATAM = {
  "cl": "DDD/1_Presentation/Web/symfony_chile",
  "cr": "DDD/1_Presentation/Web/symfony_costarica",
  "mx": "DDD/1_Presentation/Web/symfony_mexico",
  "co": "DDD/1_Presentation/Web/symfony_colombia",
}

# Una sección por monorepo; el tool elige según qué rutas de satélite
# existen en el checkout (ver elegir_repo).
REPOS_DEFECTO = {
  "europa": {"satelites": SAT_DEFECTO_EUROPA},
  "latam": {"satelites": SAT_DEFECTO_LATAM},
}

# <prefijo-con-id>/<nombre>: feat-44913/replicate-home-layout-search
PATRON_PREFIJO = re.compile(r"^([A-Za-z][A-Za-z0-9._-]*-\d+)/(.+)$")
HINTS_ORIGEN = ("origin", "main", "master", "base")
# Bases del repo consideradas siempre como candidatas a origen (en orden).
BASES_ORIGEN = ("master", "main")
REMOTO_DEFECTO = "origin"
# Marca en el mensaje del commit de cada slice: identifica las ramas que
# generó este script (único criterio para borrarlas en el re-slice).
MARCADOR_SLICE = "(generado con xtool git-separe)"


def nombre_slice(destino: str, alias: str) -> str:
  """Rama slice de un satélite. Con destino <prefijo-id>/<nombre> el alias
  se mete tras el id (feat-44913/<alias>/<nombre>); sin patrón queda
  <destino>-sat/<alias>. No puede ser <destino>/<alias>: git no permite
  que coexistan las ramas 'X' y 'X/algo' (y el destino vive hasta fusionar
  todos los slices)."""
  m = PATRON_PREFIJO.match(destino)
  if m:
    return f"{m.group(1)}/{alias}/{m.group(2)}"
  return f"{destino}-sat/{alias}"


def bloqueado_por_prefijo(rama: str):
  """Primer prefijo de 'rama' que existe como rama (bloquearía crearla:
  git no permite coexistir 'X' y 'X/algo'). None si el camino está libre."""
  partes = rama.split("/")
  for i in range(1, len(partes)):
    prefijo = "/".join(partes[:i])
    if run("git", "show-ref", "--verify", "--quiet", f"refs/heads/{prefijo}", check=False).returncode == 0:
      return prefijo
  return None


def es_slice_generada(rama: str) -> bool:
  """True si el commit punta de 'rama' lo generó este script (su mensaje
  lleva el marcador). Ramas ajenas que casualmente coinciden en nombre con
  una slice NO se consideran y por tanto no se borran ni sobreescriben."""
  return MARCADOR_SLICE in out("git", "log", "-1", "--format=%B", rama)


def slices_previas(destino: str, aliases):
  """Slices previas de este destino GENERADAS POR ESTE SCRIPT (marcador en
  el commit punta, formato actual <prefijo-id>/<alias>/<nombre>, o el
  fallback <destino>-sat/<alias> si el destino no tiene patrón). Devuelve
  la lista de nombres."""
  ramas = set(ramas_locales())
  previas = []
  m = PATRON_PREFIJO.match(destino)
  for alias in aliases:
    nombre = f"{m.group(1)}/{alias}/{m.group(2)}" if m else f"{destino}-sat/{alias}"
    if nombre in ramas and nombre not in previas and es_slice_generada(nombre):
      previas.append(nombre)
  return previas


def mostrar_ruta(ruta: Path) -> str:
  """Ruta para mostrar, con ~ en lugar del home."""
  return str(ruta).replace(str(Path.home()), "~", 1)


def limpiar_satelites(sats, ruta):
  """Valida/normaliza el dict alias->ruta de una sección; None si inválido."""
  if not isinstance(sats, dict) or not sats:
    print(f"ERROR: {ruta} debe tener un objeto no vacío bajo la clave 'satelites'")
    return None
  limpio = {}
  for alias, ruta_sat in sats.items():
    alias, ruta_sat = str(alias).strip().lower(), str(ruta_sat).strip().strip("/")
    if alias and ruta_sat and not alias.startswith("-") and "/" not in alias:
      limpio[alias] = ruta_sat
  if not limpio:
    print(f"ERROR: {ruta} no define satélites válidos (alias=ruta relativa, alias sin '/')")
    return None
  return limpio


def cargar_config():
  """Lee (creándola si no existe) la configuración JSON de satélites.

  Devuelve (dict repo_id -> dict alias -> ruta, remote) o (None, None).
  Admite el formato antiguo con 'satelites' plano (un solo repo).
  """
  ruta = Path(os.environ.get(ENV_CONFIG, "") or CONFIG_DEFAULT)
  if not ruta.is_file():
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(
      {"remote": REMOTO_DEFECTO, "repos": REPOS_DEFECTO},
      indent=2) + "\n", encoding="utf-8")
    print(f"[config] se creó {mostrar_ruta(ruta)} con los satélites por defecto")
  try:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
  except (json.JSONDecodeError, OSError) as e:
    print(f"ERROR: no se pudo leer {ruta}: {e}")
    return None, None
  if not isinstance(datos, dict):
    print(f"ERROR: {ruta} debe ser un objeto JSON")
    return None, None
  if "sufijo_slice" in datos:
    print("[config] 'sufijo_slice' ya no se usa: los slices se llaman <alias>/<destino>")
  secciones = datos.get("repos")
  if isinstance(secciones, dict) and secciones:
    repos = {}
    for repo_id, bloque in secciones.items():
      sats = limpiar_satelites(bloque.get("satelites") if isinstance(bloque, dict) else None, ruta)
      if sats is None:
        return None, None
      repos[str(repo_id).strip()] = sats
  else:
    if "satelites" in datos:
      print("[config] 'satelites' plano (formato antiguo): se trata como repo único; "
            "mueve 'satelites' dentro de 'repos' para soportar varios monorepos")
    sats = limpiar_satelites(datos.get("satelites"), ruta)
    if sats is None:
      return None, None
    repos = {"default": sats}
  remote = str(datos.get("remote") or REMOTO_DEFECTO).strip() or REMOTO_DEFECTO
  return repos, remote


def resolver_ruta_satelite(ruta: str) -> str:
  """Devuelve la ruta REAL del satélite respecto a la raíz git.

  Si la ruta configurada existe tal cual, se devuelve; si no, se localiza
  por el nombre de su último componente con git ls-files (los monorepos no
  comparten layout: en latam el sitio cuelga de solocruceros.com/ y en
  europa no). '' si no se encuentra nada.
  """
  if Path(ruta).is_dir():
    return ruta
  nombre = ruta.rstrip("/").rsplit("/", 1)[-1]
  for linea in out("git", "ls-files", "--", f"*{nombre}*").splitlines():
    partes = linea.strip().split("/")
    if nombre in partes:
      return "/".join(partes[: partes.index(nombre) + 1])
  return ""


def elegir_repo(repos, repo_opt, con_extra=False):
  """Detecta en qué monorepo estás: gana la sección con más satélites
  localizables (ruta exacta o encontrada por nombre en el index).

  Devuelve (repo_id, satelites alias -> ruta REAL) o (None, None).
  --repo fuerza la sección; con_extra (=--sat) relaja el error si no se
  localiza ninguno (los overrides aportan las rutas).
  """
  if repo_opt:
    if repo_opt not in repos:
      print(f"ERROR: no hay ningún repo '{repo_opt}' en la config (repos: {', '.join(repos)})")
      return None, None
    elegido, mejor_n = repo_opt, None
  else:
    puntuados = [(sum(1 for r in sats.values() if resolver_ruta_satelite(r)), rid)
                 for rid, sats in repos.items()]
    mejor_n, elegido = max(puntuados, key=lambda p: p[0])
    detalle = ", ".join(f"{rid} {n}/{len(repos[rid])}" for n, rid in puntuados)
    if mejor_n == 0 and not con_extra:
      print(f"ERROR: ningún satélite de la config se localiza en este checkout ({detalle}).")
      print("  ¿Estás en otro monorepo? Usa --repo <id> o revisa 'repos' en la config.")
      return None, None
    if mejor_n == 0:
      print(f"  ⚠ ningún satélite localizado aquí ({detalle}); uso '{elegido}' por los --sat dados")
    else:
      if sum(1 for n, _ in puntuados if n == mejor_n) > 1:
        print(f"  ⚠ empate entre repos ({detalle}); elijo '{elegido}' (usa --repo para forzar)")
      print(f"→ repo: {elegido}  ({mejor_n}/{len(repos[elegido])} satélites localizados)")
  sats = {}
  for alias, ruta in repos[elegido].items():
    real = resolver_ruta_satelite(ruta)
    if real and real != ruta:
      print(f"  ↳ [{alias}] {ruta} -> {real}")
    elif not real:
      print(f"  ⚠ [{alias}] no localizo '{ruta}' en este checkout; lo dejo tal cual (sin cambios)")
      real = ruta
    sats[alias] = real
  return elegido, sats


def existe_commit(ref: str) -> bool:
  return run("git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False).returncode == 0


def es_ancestra(a: str, b: str) -> bool:
  return run("git", "merge-base", "--is-ancestor", a, b, check=False).returncode == 0


def ramas_locales():
  return [r for r in out("git", "for-each-ref", "--format=%(refname:short)", "refs/heads/").splitlines() if r]


def prefijo_rama(rama: str):
  """'feat-44913/lo-que-sea' -> 'feat-44913' (None si no hay <id>/<nombre>)."""
  m = PATRON_PREFIJO.match(rama)
  return m.group(1) if m else None


def candidatos_origen(destino: str, aliases):
  """Candidatas a origen: bases del repo (master/main) + ramas con el mismo
  prefijo-id, aptas para ser origen.

  Excluye el destino y ramas con algún componente igual a un alias
  (slices: feat-44913/<alias>/<nombre> o <destino>-sat/<alias> viejos).
  Orden: ancestra+hint > ancestra.
  """
  prefijo = prefijo_rama(destino)
  posibles = list(BASES_ORIGEN)
  if prefijo:
    for rama in ramas_locales():
      if rama == destino or rama.startswith(destino + "/"):
        continue
      if not rama.startswith(prefijo + "/"):
        continue
      if any(p in aliases for p in rama.split("/")):
        continue
      posibles.append(rama)
  cands, vistas = [], set()
  for rama in posibles:
    if rama == destino or rama in vistas or not existe_commit(rama):
      continue
    vistas.add(rama)
    ancestra = es_ancestra(rama, destino)
    hint = any(h in rama for h in HINTS_ORIGEN)
    cands.append((rama, ancestra, hint))
  cands.sort(key=lambda c: (not (c[1] and c[2]), not c[1], c[0]))
  return cands


def elegir_origen(destino: str, aliases, yes: bool):
  """Autodetecta/pregunta el origen. Devuelve el nombre o None."""
  cands = candidatos_origen(destino, aliases)
  if cands:
    pref = prefijo_rama(destino)
    alcance = f"bases (master/main) y ramas {pref}/*" if pref else "bases (master/main)"
    print(f"\n→ buscando origen ({alcance}):")
    for i, (rama, ancestra, hint) in enumerate(cands):
      marca = "✓" if i == 0 else "·"
      nota = []
      if rama in BASES_ORIGEN:
        nota.append("base del repo")
      if ancestra and hint:
        nota.append("ancestra de destino — sugerida")
      elif ancestra:
        nota.append("ancestra de destino")
      else:
        nota.append("no es ancestra")
      print(f"    {marca} {rama} ({', '.join(nota)})")
    default = cands[0][0]
    if yes:
      return default
    try:
      resp = input(f"  origen [{default}]: ").strip()
    except EOFError:
      return None
    if not resp or resp == default:
      return default
    if existe_commit(resp):
      return resp
    print(f"ERROR: '{resp}' no existe")
    return None
  print("\n→ sin candidatas de origen (ni master/main ni ramas del prefijo-id)")
  if yes:
    print("ERROR: no se pudo autodetectar el origen; usa --origen <rama>")
    return None
  try:
    resp = input("  origen (rama base limpia): ").strip()
  except EOFError:
    return None
  if resp and existe_commit(resp):
    return resp
  if resp:
    print(f"ERROR: '{resp}' no existe")
  return None


def archivos_cambiados(origen: str, destino: str, ruta: str = None):
  args = ["git", "diff", "--name-only", origen, destino]
  if ruta:
    args += ["--", ruta]
  res = out(*args)
  return [f for f in res.splitlines() if f]


def parsear_argv(argv):
  destino = origen = repo = None
  sats_extra, dry, force, yes, no_push = [], False, False, False, False
  i = 0
  while i < len(argv):
    a = argv[i]
    if a in ("-h", "--help"):
      print(__doc__)
      return None
    if a in ("--destino", "--origen", "--sat", "--repo") and i + 1 < len(argv):
      val = argv[i + 1]
      if a == "--destino":
        destino = val
      elif a == "--origen":
        origen = val
      elif a == "--repo":
        repo = val
      else:
        sats_extra.append(val)
      i += 2
    elif a == "--dry-run":
      dry = True; i += 1
    elif a == "--force":
      force = True; i += 1
    elif a in ("-y", "--yes"):
      yes = True; i += 1
    elif a == "--no-push":
      no_push = True; i += 1
    elif a in ("-p", "--push"):
      i += 1  # ya es el default; se acepta por compatibilidad, no hace nada
    else:
      print(f"Argumento desconocido: {a}\nVer: xtool help git-separe")
      return None
  opts = {"destino": destino, "origen": origen, "sats_extra": sats_extra, "repo": repo,
          "dry": dry, "force": force, "yes": yes, "push": not no_push}
  return opts


def main(argv=None):
  argv = list(sys.argv[1:]) if argv is None else list(argv)
  opts = parsear_argv(argv)
  if opts is None:
    return 1
  try:
    return _ejecutar(opts)
  except KeyboardInterrupt:
    print("\nCancelado.")
    return 130


def _ejecutar(opts):
  # ── Repo y estado ──
  raiz = out("git", "rev-parse", "--show-toplevel").strip()
  if not raiz:
    print("ERROR: no estás dentro de un repo git")
    return 1
  os.chdir(raiz)
  if run("git", "diff-index", "--quiet", "HEAD", "--", check=False).returncode != 0:
    print("ℹ tienes cambios sin commitear: se IGNORAN (los slices capturan solo lo commiteado)")

  # ── Satélites (config + detección de monorepo + overrides) ──
  repos, remote = cargar_config()
  if repos is None:
    return 1
  _repo, sats = elegir_repo(repos, opts["repo"], con_extra=bool(opts["sats_extra"]))
  if sats is None:
    return 1
  for extra in opts["sats_extra"]:
    if "=" not in extra:
      print(f"ERROR: --sat espera alias=ruta (recibido: '{extra}')")
      return 1
    alias, ruta = extra.split("=", 1)
    sats[alias.strip().lower()] = ruta.strip().strip("/")

  # ── Destino ──
  destino = opts["destino"] or out("git", "rev-parse", "--abbrev-ref", "HEAD").strip()
  if destino == "HEAD":
    print("ERROR: HEAD desacoplado; indica la rama con --destino")
    return 1
  if not existe_commit(destino):
    print(f"ERROR: la rama destino '{destino}' no existe")
    return 1
  print(f"\n→ destino: {destino}   (rama actual ✓)" if not opts["destino"]
        else f"\n→ destino: {destino}   (--destino)")
  if prefijo_rama(destino) is None and not opts["origen"]:
    print(f"  ⚠ '{destino}' no coincide <prefijo-id>/<nombre>; el origen se buscará solo entre las bases (master/main)")

  # ── Origen ──
  origen = opts["origen"]
  if origen:
    if not existe_commit(origen):
      print(f"ERROR: la rama origen '{origen}' no existe")
      return 1
  else:
    origen = elegir_origen(destino, set(sats), opts["yes"])
    if not origen:
      return 1
  if origen == destino:
    print("ERROR: origen y destino son la misma rama")
    return 1
  if not es_ancestra(origen, destino):
    print(f"  ⚠ '{origen}' NO es ancestra de '{destino}': el diff directo puede incluir cambios de más")

  # ── Plan por satélite ──
  print(f"\n→ cambios por satélite (diff {origen}..{destino}):")
  plan = []
  for alias, ruta in sats.items():
    archivos = archivos_cambiados(origen, destino, ruta)
    if archivos:
      plan.append((alias, ruta, len(archivos)))
      print(f"    {alias:<6} {ruta:<44} {len(archivos):>4} archivos")
  if not plan:
    print("    (ningún satélite tiene cambios: no hay nada que separar)")
    return 0

  todos = archivos_cambiados(origen, destino)
  fuera = [f for f in todos if not any(f == r or f.startswith(r + "/") for r in sats.values())]
  if fuera:
    print(f"  ⚠ {len(fuera)} archivos quedan FUERA de los satélites (no entrarán en ningún slice):")
    for f in fuera[:10]:
      print(f"     {f}")
    if len(fuera) > 10:
      print(f"     ... y {len(fuera) - 10} más")
  else:
    print("    ✓ sin cambios fuera de satélites")

  # ── Slices previas de este destino (generadas por este script) ──
  previas = slices_previas(destino, sats)
  if previas:
    print(f"\n→ slices previas de este destino ({len(previas)}):")
    for nombre in sorted(previas):
      nota = (f"ya fusionada en '{origen}': la nueva solo llevará el delta (o nada)"
              if es_ancestra(nombre, origen) else "")
      print(f"    {nombre}" + (f"  ({nota})" if nota else ""))
    if not opts["force"]:
      print("  (sin --force no se borra ni recrea nada de lo anterior)")

  # ── Ramas a crear / conflictos existentes ──
  print(f"\n→ ramas a crear desde {origen}:")
  por_crear = []
  for alias, _ruta, _n in plan:
    rama = nombre_slice(destino, alias)
    bloqueo = bloqueado_por_prefijo(rama)
    if bloqueo:
      print(f"ERROR: existe la rama '{bloqueo}' y git no permite crear '{rama}' junto a ella")
      print("  (git no admite que coexistan las ramas 'X' y 'X/algo'; renómbrala o bórrala)")
      return 1
    existe = run("git", "show-ref", "--verify", "--quiet", f"refs/heads/{rama}", check=False).returncode == 0
    if existe and rama not in previas:
      print(f"    ✗ {rama} YA EXISTE y NO la generó este script: no la toco")
      print("      (bórrala o renómbrala a mano si de verdad quieres usar ese nombre)")
      return 1
    if existe and not opts["force"]:
      print(f"    ✗ {rama} YA EXISTE (usa --force para recrearla)")
      return 1
    por_crear.append(rama)
    print(f"    {'↻' if existe else '+'} {rama}")

  if opts["dry"]:
    extra = ""
    if previas:
      if opts["force"]:
        sin_reemplazo = len(previas) - len([n for n in previas if n in set(por_crear)])
        extra = f"; --force borraría {len(previas)} slice(s) previa(s)" + (f" ({sin_reemplazo} sin reemplazo)" if sin_reemplazo else "")
      else:
        extra = "; sin --force no se tocarían las slices previas"
    print("\n[dry-run] nada creado" + extra
          + (f" (las slices se publicarían en '{remote}')" if opts["push"] else " (--no-push: no se publicarán)"))
    return 0

  if not opts["yes"]:
    accion = " y publicar en '" + remote + "'" if opts["push"] else ""
    try:
      resp = input(f"\n¿Proceder{accion}? (Enter=sí / n=no): ").strip().lower()
    except EOFError:
      resp = "n"
    if resp.startswith("n"):
      print("Cancelado.")
      return 1

  # ── Borrado local de slices previas (--force) ──
  if opts["force"] and previas:
    for nombre in sorted(previas):
      run("git", "branch", "-D", nombre)
    print(f"\n→ {len(previas)} slice(s) previa(s) borrada(s) localmente")

  # ── Creación de slices (en worktree temporal aislado) ──
  wt = Path(tempfile.mkdtemp(prefix="xtool-git-separe-"))
  wt_ok = run("git", "worktree", "add", "--detach", str(wt), origen, check=False)
  if wt_ok.returncode != 0:
    print(f"ERROR: no se pudo crear el worktree temporal:\n{wt_ok.stderr.strip()}")
    return 1
  creadas = []
  ok_total = True
  try:
    for alias, ruta, _n in plan:
      rama = nombre_slice(destino, alias)
      if run("git", "show-ref", "--verify", "--quiet", f"refs/heads/{rama}", check=False).returncode == 0:
        run("git", "branch", "-D", rama)
      run("git", "checkout", "-q", "-b", rama, origen, cwd=wt)

      diff = subprocess.run(
        ["git", "diff", "--binary", origen, destino, "--", ruta],
        capture_output=True, check=True,
      ).stdout
      apply = subprocess.run(
        ["git", "apply", "--index", "--whitespace=nowarn", "-"],
        input=diff, capture_output=True, cwd=wt,
      )
      if apply.returncode != 0:
        print(f"✗ [{alias}] falló 'git apply': {apply.stderr.decode(errors='replace').strip()}")
        print(f"  se elimina la rama parcial {rama}")
        run("git", "checkout", "-q", "--detach", origen, cwd=wt)
        run("git", "branch", "-D", rama)
        if creadas:
          print(f"  (las slices ya creadas siguen válidas: {' '.join(creadas)})")
        return 1

      run("git", "commit", "-q", "-m",
          f"[{alias}] slice satélite de {destino}\n\nSolo cambios de: {ruta}\n{MARCADOR_SLICE}", cwd=wt)
      run("git", "checkout", "-q", "--detach", origen, cwd=wt)

      if run("git", "diff", "--quiet", rama, destino, "--", ruta, check=False).returncode == 0:
        print(f"✓ [{alias}] {rama} creada y verificada")
        creadas.append(rama)
      else:
        print(f"⚠ [{alias}] {rama} creada PERO difiere del destino en '{ruta}' — revisar")
        creadas.append(rama)
        ok_total = False
  finally:
    run("git", "worktree", "remove", "--force", str(wt), check=False)
    run("git", "worktree", "prune", check=False)

  if creadas:
    print(f"\n→ ramas creadas ({destino} sigue intacta):")
    for rama in creadas:
      print(f"    {'↻' if rama in previas else '+'} {rama}")
    sin_reemplazo = sorted(n for n in previas if n not in set(creadas))
    if sin_reemplazo:
      print(f"    ({len(sin_reemplazo)} previa(s) borrada(s) sin reemplazo: {' '.join(sin_reemplazo)})")

  # ── Publicación y limpieza remota ──
  if opts["push"]:
    recreadas = [r for r in creadas if r in previas]
    nuevas = [r for r in creadas if r not in previas]
    ok_push = True
    if creadas:
      print(f"\n→ publicando {len(creadas)} slices en '{remote}' ..."
            + (" (--force-with-lease: sobrescribe las ya publicadas)" if recreadas else ""))
      if recreadas:
        pr = run("git", "push", "--force-with-lease", remote, *recreadas, check=False)
        if pr.returncode != 0:
          ok_push = False
          print(f"✗ ERROR al pushear (recreadas):\n{pr.stderr.strip()}")
      if nuevas:
        pn = run("git", "push", remote, *nuevas, check=False)
        if pn.returncode != 0:
          ok_push = False
          print(f"✗ ERROR al pushear (nuevas):\n{pn.stderr.strip()}")
    pendientes_borrar = sorted(n for n in previas if n not in set(creadas))
    if pendientes_borrar:
      existe = set()
      for linea in out("git", "ls-remote", "--heads", remote, *pendientes_borrar).splitlines():
        partes = linea.split("\t")
        if len(partes) == 2:
          existe.add(partes[1])
      a_borrar = [n for n in pendientes_borrar if f"refs/heads/{n}" in existe]
      if a_borrar:
        pd = run("git", "push", remote, "--delete", *a_borrar, check=False)
        if pd.returncode == 0:
          print(f"✓ {len(a_borrar)} slice(s) sin reemplazo borrada(s) del remote: {' '.join(a_borrar)}")
        else:
          print(f"⚠ no se pudieron borrar del remote: {' '.join(a_borrar)}\n{pd.stderr.strip()}")
    if not ok_push:
      print("las slices quedaron creadas localmente; publícalas a mano:")
      if recreadas:
        print(f"  git push --force-with-lease {remote} " + " ".join(recreadas))
      if nuevas:
        print(f"  git push {remote} " + " ".join(nuevas))
      return 1
    if creadas:
      print(f"✓ slices publicadas en '{remote}'")
    return 0 if ok_total else 1

  print(f"\nListo ({'con avisos' if not ok_total else 'todo verificado'}). Tu rama actual no se tocó. Para publicar:")
  if creadas:
    cmd = "git push --force-with-lease" if any(r in previas for r in creadas) else "git push"
    print(f"  {cmd} {remote} " + " ".join(creadas))
  return 0 if ok_total else 1


if __name__ == "__main__":
  sys.exit(main())
