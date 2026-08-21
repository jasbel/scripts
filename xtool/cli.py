import importlib
import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent / "tools"

VALID_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _available_tools():
  return sorted(p.stem for p in TOOLS_DIR.glob("*.py") if p.name != "__init__.py")


def _print_usage():
  print("Uso: xtool <comando> [args...]")
  tools = _available_tools()
  if tools:
    print("\nComandos disponibles:")
    for t in tools:
      print(f"  xtool {t.replace('_', '-')}")


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
    _print_usage()
    return 0

  name = _resolve(argv[0])
  if name is None:
    return 1

  mod = importlib.import_module(f"xtool.tools.{name}")
  fn = getattr(mod, "main", None)
  if not callable(fn):
    print(f"xtool: {name}.py no define main(argv)")
    return 1

  return fn(argv[1:])
