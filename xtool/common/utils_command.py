import re
import socket
import subprocess

import psutil


def get_local_ip():
  try:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
      s.connect(("8.8.8.8", 80))
      return s.getsockname()[0]
  except Exception:
    return "127.0.0.1"


def kill_proccess(command_line: str):
  """Matar procesos que coincidan con el patrón de línea de comando dado."""
  for proc in psutil.process_iter(["pid", "cmdline"]):
    try:
      cmdline = proc.info["cmdline"]
      if cmdline and command_line in " ".join(cmdline):
        proc.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
      pass


def ps_process():
  """Listar procesos java/selenium/grid/appium en ejecución."""
  for proc in psutil.process_iter(["pid", "cmdline", "name"]):
    try:
      cmdline = proc.info["cmdline"]
      name = proc.info["name"]
      if cmdline:
        cmdline_str = " ".join(cmdline)
        if ("java" in name.lower() or "java" in cmdline_str.lower()) and any(keyword in cmdline_str.lower() for keyword in ["selenium", "grid", "appium"]):
          print(f"PID: {proc.info['pid']}, Command: {cmdline_str}")
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
      pass


def kill_port_process(port: int):
  """Matar proceso/contenedor escuchando en el puerto específico usando múltiples métodos.

  Maneja problemas de permisos donde psutil no puede ver los PIDs de conexión.
  También maneja contenedores Docker que pueden estar usando los puertos.
  """
  killed_any = False

  # Método 1: lsof (más eficiente cuando está disponible)
  try:
    result = subprocess.run(["lsof", "-t", "-i", f":{port}", "-sTCP:LISTEN"], capture_output=True, text=True, timeout=5)
    if result.returncode == 0 and result.stdout.strip():
      for pid_str in result.stdout.strip().split("\n"):
        try:
          proc = psutil.Process(int(pid_str))
          proc.kill()
          killed_any = True
        except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
          continue
      if killed_any:
        return True
  except Exception:
    pass

  # Método 2: contenedores Docker que mapeen el puerto
  try:
    docker_result = subprocess.run(["docker", "ps", "--format", "{{.ID}}\t{{.Ports}}"], capture_output=True, text=True, timeout=10)
    if docker_result.returncode == 0 and docker_result.stdout.strip():
      for line in docker_result.stdout.strip().split("\n"):
        if f":{port}->" in line.replace(" ", ""):
          container_id = line.split("\t")[0]
          if container_id:
            subprocess.run(["docker", "stop", container_id], timeout=30)
            return True
  except Exception:
    pass

  # Método 3: inspección de conexiones con psutil (fallback por permisos)
  try:
    for proc in psutil.process_iter(["pid"]):
      try:
        for conn in proc.net_connections(kind="inet"):
          if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
            proc.kill()
            return True
      except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, AttributeError):
        continue
  except Exception:
    pass

  return False
