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
  print("Uso: xtool <comando> [args...]")
  print("      xtool help <comando>   # manual del comando")
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


def _resolve(name_arg):
  name = name_arg.replace("-", "_")
  if not VALID_NAME.match(name) or not (TOOLS_DIR / f"{name}.py").exists():
    print(f"xtool: comando desconocido: {name_arg}")
    _print_usage()
    return None
  return name


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
