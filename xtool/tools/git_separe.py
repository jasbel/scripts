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
  3. Plan: cambios por satélite según ~/.config/xtool/git-separe.json
     (alias -> ruta relativa a la raíz del repo) y aviso de archivos que
     quedan FUERA de todos los satélites (no entrarían en ningún slice).
  4. Crea <destino>-sat/<alias> desde <origen> aplicando SOLO los cambios de
     su ruta: git diff --binary origen..destino -- ruta | git apply --index.
     Tras commitear VERIFICA que el contenido de la ruta en el slice sea
     idéntico al del destino; si difiere lo avoca ruidosamente.
     (El slice no puede llamarse <destino>/<alias>: git no permite que
     coexistan las ramas 'X' y 'X/algo'.)
  5. Vuelve a la rama original y pushea las slices creadas al remote
     (default "origin", configurable como "remote" en el JSON). Con
     --no-push las deja solo locales e imprime el comando para publicarlas.

Opciones:
  --destino <rama>   rama con todos los cambios (default: rama actual)
  --origen <rama>    rama base limpia (default: autodetección interactiva)
  --sat a=ruta       agrega/sobrescribe un satélite (repetible),
                     p.ej. --sat ltp=DDD/1_Presentation/Web/latampass
  --dry-run          solo muestra el plan, no crea nada
  --force            recrea ramas slice existentes (las borra primero)
  --no-push          NO publica las slices tras crearlas (default: pushea)
  -y/--yes           no pregunta (falla si no puede autodetectar el origen)

Requiere git ≥ 2.5 (usa un worktree temporal aislado para no tocar tu
working tree: puedes tener cambios sin commitear, se ignoran — los slices
solo capturan lo COMMITEADO entre origen y destino).

Configuración en ~/.config/xtool/git-separe.json (o la ruta de la variable
de entorno GIT_SEPARE_CONFIG); se crea con defaults la primera vez:

  {
    "sufijo_slice": "-sat",
    "remote": "origin",
    "satelites": {
      "me":    "DDD/1_Presentation/Web/symfony_mediterraneo",
      "sc":    "DDD/1_Presentation/Web/symfony_home",
      "islas": "DDD/1_Presentation/Web/symfony_islasgriegas",
      "lujo":  "DDD/1_Presentation/Web/symfony_lujo"
    }
  }

- sufijo_slice: cómo se llama cada rama slice: <destino><sufijo>/<alias>
  (p.ej. feat-44913/replicate-home-layout-search-sat/me).
- remote: a dónde publica --push (default "origin").

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

SAT_DEFECTO = {
  "me": "DDD/1_Presentation/Web/symfony_mediterraneo",
  "sc": "DDD/1_Presentation/Web/symfony_home",
  "islas": "DDD/1_Presentation/Web/symfony_islasgriegas",
  "lujo": "DDD/1_Presentation/Web/symfony_lujo",
}

# <prefijo-con-id>/<nombre>: feat-44913/replicate-home-layout-search
PATRON_PREFIJO = re.compile(r"^([A-Za-z][A-Za-z0-9._-]*-\d+)/(.+)$")
HINTS_ORIGEN = ("origin", "main", "master", "base")
# Bases del repo consideradas siempre como candidatas a origen (en orden).
BASES_ORIGEN = ("master", "main")
SUFIJO_DEFECTO = "-sat"
REMOTO_DEFECTO = "origin"


def nombre_slice(destino: str, sufijo: str, alias: str) -> str:
  return f"{destino}{sufijo}/{alias}"


def mostrar_ruta(ruta: Path) -> str:
  """Ruta para mostrar, con ~ en lugar del home."""
  return str(ruta).replace(str(Path.home()), "~", 1)


def cargar_config():
  """Lee (creándola si no existe) la configuración JSON de satélites.

  Devuelve (dict alias -> ruta, sufijo_slice, remote) o (None, None, None).
  """
  ruta = Path(os.environ.get(ENV_CONFIG, "") or CONFIG_DEFAULT)
  if not ruta.is_file():
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(
      {"sufijo_slice": SUFIJO_DEFECTO, "remote": REMOTO_DEFECTO, "satelites": SAT_DEFECTO},
      indent=2) + "\n", encoding="utf-8")
    print(f"[config] se creó {mostrar_ruta(ruta)} con los satélites por defecto")
  try:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
  except (json.JSONDecodeError, OSError) as e:
    print(f"ERROR: no se pudo leer {ruta}: {e}")
    return None, None
  sats = datos.get("satelites") if isinstance(datos, dict) else None
  if not isinstance(sats, dict) or not sats:
    print(f"ERROR: {ruta} debe tener un objeto no vacío bajo la clave 'satelites'")
    return None, None, None
  limpio = {}
  for alias, ruta_sat in sats.items():
    alias, ruta_sat = str(alias).strip().lower(), str(ruta_sat).strip().strip("/")
    if alias and ruta_sat and not alias.startswith("-"):
      limpio[alias] = ruta_sat
  if not limpio:
    print(f"ERROR: {ruta} no define satélites válidos (alias=ruta relativa)")
    return None, None, None
  sufijo = str(datos.get("sufijo_slice") or SUFIJO_DEFECTO).strip()
  if not sufijo.startswith("-") or "/" in sufijo:
    print("ERROR: sufijo_slice debe empezar con '-' y no contener '/' (p.ej. '-sat')")
    return None, None, None
  remote = str(datos.get("remote") or REMOTO_DEFECTO).strip() or REMOTO_DEFECTO
  return limpio, sufijo, remote


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


def candidatos_origen(destino: str, aliases, sufijo: str):
  """Candidatas a origen: bases del repo (master/main) + ramas con el mismo
  prefijo-id, aptas para ser origen.

  Excluye el destino, sus slices (<destino><sufijo>/...) y ramas que
  terminan en /<alias> (slices viejos). Orden: ancestra+hint > ancestra.
  """
  prefijo = prefijo_rama(destino)
  posibles = list(BASES_ORIGEN)
  if prefijo:
    for rama in ramas_locales():
      if rama == destino or rama.startswith(destino + "/"):
        continue
      if rama.startswith(destino + sufijo + "/"):
        continue
      if not rama.startswith(prefijo + "/"):
        continue
      if "/" in rama and rama.rsplit("/", 1)[1] in aliases:
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


def elegir_origen(destino: str, aliases, sufijo: str, yes: bool):
  """Autodetecta/pregunta el origen. Devuelve el nombre o None."""
  cands = candidatos_origen(destino, aliases, sufijo)
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
  destino = origen = None
  sats_extra, dry, force, yes, no_push = [], False, False, False, False
  i = 0
  while i < len(argv):
    a = argv[i]
    if a in ("-h", "--help"):
      print(__doc__)
      return None
    if a in ("--destino", "--origen", "--sat") and i + 1 < len(argv):
      val = argv[i + 1]
      if a == "--destino":
        destino = val
      elif a == "--origen":
        origen = val
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
  opts = {"destino": destino, "origen": origen, "sats_extra": sats_extra,
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

  # ── Satélites (config + overrides) ──
  sats, sufijo, remote = cargar_config()
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
    origen = elegir_origen(destino, set(sats), sufijo, opts["yes"])
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

  # ── Ramas a crear / conflictos existentes ──
  base_slice = destino + sufijo
  if run("git", "show-ref", "--verify", "--quiet", f"refs/heads/{base_slice}", check=False).returncode == 0:
    print(f"ERROR: existe la rama '{base_slice}' y git no permite crear '{base_slice}/<alias>' junto a ella")
    print(f"  (git no admite que coexistan las ramas 'X' y 'X/algo'; renómbrala o bórrala)")
    return 1
  print(f"\n→ ramas a crear desde {origen}:")
  por_crear = []
  for alias, _ruta, _n in plan:
    rama = nombre_slice(destino, sufijo, alias)
    existe = run("git", "show-ref", "--verify", "--quiet", f"refs/heads/{rama}", check=False).returncode == 0
    if existe and not opts["force"]:
      print(f"    ✗ {rama} YA EXISTE (usa --force para recrearla)")
      return 1
    por_crear.append(rama)
    print(f"    {'↻' if existe else '+'} {rama}")

  if opts["dry"]:
    print("\n[dry-run] nada creado" + (f" (las slices se publicarían en '{remote}')"
                                       if opts["push"] else " (--no-push: no se publicarán)"))
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
      rama = nombre_slice(destino, sufijo, alias)
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
          f"[{alias}] slice satélite de {destino}\n\nSolo cambios de: {ruta}\n(generado con xtool git-separe)", cwd=wt)
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

  if opts["push"] and creadas:
    print(f"\n→ publicando {len(creadas)} slices en '{remote}' ...")
    pu = run("git", "push", remote, *creadas, check=False)
    if pu.returncode != 0:
      print(f"✗ ERROR al pushear:\n{pu.stderr.strip()}")
      print("las slices quedaron creadas localmente; publícalas a mano:")
      print(f"  git push {remote} " + " ".join(creadas))
      return 1
    print(f"✓ slices publicadas en '{remote}'")
    return 0 if ok_total else 1

  print(f"\nListo ({'con avisos' if not ok_total else 'todo verificado'}). Tu rama actual no se tocó. Para publicar:")
  print(f"  git push {remote} " + " ".join(creadas))
  return 0 if ok_total else 1


if __name__ == "__main__":
  sys.exit(main())
