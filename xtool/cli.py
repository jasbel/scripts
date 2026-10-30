import ast
import importlib
import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent / "tools"

VALID_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _available_tools():
  return sorted(p.stem for p in TOOLS_DIR.glob("*.py") if p.name != "__init__.py")


def _docstring(name):
  """Lee el docstring del tool sin importarlo (evita side effects)."""
  path = TOOLS_DIR / f"{name}.py"
  try:
    tree = ast.parse(path.read_text(encoding="utf-8"))
  except Exception:
    return ""
  return (ast.get_docstring(tree) or "").strip()


def _short(name):
  doc = _docstring(name)
  return doc.splitlines()[0] if doc else "(sin descripción)"


def _cmd_name(name):
  return name.replace("_", "-")


def _print_usage():
  print("Uso: xtool <comando> [args...]   (alias: x)")
  print("      xtool help <comando>   # manual del comando")
  print("      Los comandos git-* aceptan atajo sin prefijo (xtool diff = xtool git-diff)")
  tools = _available_tools()
  if tools:
    print("\nComandos disponibles:")
    for t in tools:
      print(f"  {_cmd_name(t):<12} {_short(t)}")


def _print_manual(name):
  doc = _docstring(name)
  print(f"xtool {_cmd_name(name)}")
  print("-" * 40)
  print(doc if doc else "(sin manual: agrega un docstring al módulo)")


def _print_complete():
  """Emite `comando:descripción` (uno por línea) para autocompletado de shell."""
  tools = _available_tools()
  for t in tools:
    print(f"{_cmd_name(t)}:{_short(t)}")
  for t in tools:
    short = t[len("git_"):] if t.startswith("git_") else None
    if short and short not in tools:
      print(f"{_cmd_name(short)}:{_short(t)}")
  print("help:manual del comando (xtool help <comando>)")


def _exists(name):
  return bool(VALID_NAME.match(name)) and (TOOLS_DIR / f"{name}.py").exists()


def _resolve(name_arg):
  name = name_arg.replace("-", "_")
  if _exists(name):
    return name
  # Atajo: `xtool diff` equivale a `xtool git-diff` (si no existe un tool propio con ese nombre).
  if _exists(f"git_{name}"):
    return f"git_{name}"
  print(f"xtool: comando desconocido: {name_arg}")
  _print_usage()
  return None


def main(argv=None):
  argv = list(sys.argv[1:]) if argv is None else list(argv)

  if not argv or argv[0] in ("-h", "--help", "help"):
    if len(argv) > 1 and argv[0] == "help":
      name = _resolve(argv[1])
      if name:
        _print_manual(name)
        return 0
      return 1
    _print_usage()
    return 0

  if argv[0] == "__complete":
    # Hook de autocompletado: formato máquina para shells (zsh/bash).
    _print_complete()
    return 0

  name = _resolve(argv[0])
  if name is None:
    return 1

  if len(argv) > 1 and argv[1] in ("-h", "--help"):
    _print_manual(name)
    return 0

  mod = importlib.import_module(f"xtool.tools.{name}")
  fn = getattr(mod, "main", None)
  if not callable(fn):
    print(f"xtool: {name}.py no define main(argv)")
    return 1

  return fn(argv[1:])
