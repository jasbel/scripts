#!/usr/bin/env bash
#
# get-titles.sh — Recupera el <title> de una lista de páginas vía curl
# y genera un JSON:
#
# [
#   { "name": "Cruceros Familias", "url": "http://scme.local/cruceros-familias",
#     "title": "Cruceros Familias por el Mediterráneo 2027-2028" },
#   ...
# ]
#
# Uso:
#   /home/asbel/projects/scripts/scripts/get-titles.sh                                              # local (BASE_URL por defecto, lista PAGES)
#   /home/asbel/projects/scripts/scripts/get-titles.sh --pages ig                                  # local, lista PAGES_IG
#   /home/asbel/projects/scripts/scripts/get-titles.sh https://sbox-mediterraneo.solocruceros.com   # pre
#   BASE_URL="https://..." /home/asbel/projects/scripts/scripts/get-titles.sh                       # por variable de entorno
#   /home/asbel/projects/scripts/scripts/get-titles.sh > titles.json                                # guardar a fichero
#   /home/asbel/projects/scripts/scripts/get-titles.sh https://sbox-mediterraneo.solocruceros.com --pages ig > /home/asbel/Desktop/titles.json
#
# Añadir páginas: editar la lista PAGES (o PAGES_IG) de abajo.
#   "Nombre|/ruta-relativa"        → se antepone BASE_URL
#   "Nombre|https://url-completa"  → se usa tal cual (ignora BASE_URL)
#
# Requiere: bash, curl, GNU grep (opción -P), sed.

# cd public/dist/assets/landingpages/most-wanted
# grep -rl 'Cruceros.*2027-2028'
#
# install -D -m 644 public/dist/assets/landingpages/most-wanted/spring/data.json public/assets/landingpages/most-wanted/spring/data.json
# install -D -m 644 public/dist/assets/landingpages/most-wanted/premium/data.json public/assets/landingpages/most-wanted/premium/data.json
# install -D -m 644 public/dist/assets/landingpages/most-wanted/cheap/data.json public/assets/landingpages/most-wanted/cheap/data.json
# install -D -m 644 public/dist/assets/landingpages/most-wanted/holyweek/data.json public/assets/landingpages/most-wanted/holyweek/data.json
# install -D -m 644 public/dist/assets/landingpages/most-wanted/allincluded/data.json public/assets/landingpages/most-wanted/allincluded/data.json
# install -D -m 644 public/dist/assets/landingpages/most-wanted/autumn/data.json public/assets/landingpages/most-wanted/autumn/data.json
# install -D -m 644 public/dist/assets/landingpages/most-wanted/winter/data.json public/assets/landingpages/most-wanted/winter/data.json
# install -D -m 644 public/dist/assets/landingpages/most-wanted/boyfriends/data.json public/assets/landingpages/most-wanted/boyfriends/data.json
# install -D -m 644 public/dist/assets/landingpages/most-wanted/lasthour/data.json public/assets/landingpages/most-wanted/lasthour/data.json
# install -D -m 644 public/dist/assets/landingpages/most-wanted/families/data.json public/assets/landingpages/most-wanted/families/data.json
# install -D -m 644 public/dist/assets/landingpages/most-wanted/luxury/data.json public/assets/landingpages/most-wanted/luxury/data.json
# 
# install -D -m 644 public/assets/landingpages/most-wanted/spring/data.json public/dist/assets/landingpages/most-wanted/spring/data.json
# install -D -m 644 public/assets/landingpages/most-wanted/premium/data.json public/dist/assets/landingpages/most-wanted/premium/data.json
# install -D -m 644 public/assets/landingpages/most-wanted/cheap/data.json public/dist/assets/landingpages/most-wanted/cheap/data.json
# install -D -m 644 public/assets/landingpages/most-wanted/holyweek/data.json public/dist/assets/landingpages/most-wanted/holyweek/data.json
# install -D -m 644 public/assets/landingpages/most-wanted/allincluded/data.json public/dist/assets/landingpages/most-wanted/allincluded/data.json
# install -D -m 644 public/assets/landingpages/most-wanted/autumn/data.json public/dist/assets/landingpages/most-wanted/autumn/data.json
# install -D -m 644 public/assets/landingpages/most-wanted/winter/data.json public/dist/assets/landingpages/most-wanted/winter/data.json
# install -D -m 644 public/assets/landingpages/most-wanted/boyfriends/data.json public/dist/assets/landingpages/most-wanted/boyfriends/data.json
# install -D -m 644 public/assets/landingpages/most-wanted/lasthour/data.json public/dist/assets/landingpages/most-wanted/lasthour/data.json
# install -D -m 644 public/assets/landingpages/most-wanted/families/data.json public/dist/assets/landingpages/most-wanted/families/data.json
# install -D -m 644 public/assets/landingpages/most-wanted/luxury/data.json public/dist/assets/landingpages/most-wanted/luxury/data.json

set -uo pipefail

# ─── Argumentos ─────────────────────────────────────────────────────────
#   --pages ig     → usa la lista PAGES_IG
#   --pages=ig     → ídem (forma compacta)
# El resto de argumentos posicionales se tratan como siempre (BASE_URL).
PAGES_SET="default"
POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pages)
      [[ $# -ge 2 ]] || { printf 'ERROR: --pages necesita un valor (p. ej. ig)\n' >&2; exit 1; }
      PAGES_SET="$2"; shift 2 ;;
    --pages=*)
      PAGES_SET="${1#--pages=}"; shift ;;
    *)
      POSITIONAL+=("$1"); shift ;;
  esac
done

# ─── Configuración ──────────────────────────────────────────────────────
# URL base por defecto (entorno local). Se puede sobrescribir:
#   1) pasándola como primer argumento posicional  (máxima prioridad)
#   2) con la variable de entorno BASE_URL
BASE_URL="${BASE_URL:-http://scme.local}"
BASE_URL="${POSITIONAL[0]:-$BASE_URL}"
BASE_URL="${BASE_URL%/}"   # quita la barra final si la lleva


# ─── PÁGINAS (añadir aquí nuevas entradas) ──────────────────────────────
# Formato: "Nombre|/ruta"
PAGES=(
  "Cruceros Famil|/cruceros-familias"
  "Cruceros Barat|/cruceros-baratos"
  "Cruceros Premi|/cruceros-premium"
  "Cruceros de Lu|/lujo"
  "Cruceros Novio|/novios"
  "Cruceros Todo |/cruceros-todo-incluido"
  "Minicruceros|/minicruceros"
  "Última hora|/cruceros-ultima-hora"
  "Primavera|/cruceros-primavera"
  "Verano|/cruceros-verano"
  "Otoño|/cruceros-otono"
  "Invierno|/cruceros-invierno"
  "Navidad y Fin|/cruceros-navidad-y-fin-de-ano"
  "Cruceros Seman|/cruceros-semana-santa"
)
PAGES_IG=(
  "Cruceros Familias|/cruceros-familias"
  "Cruceros Baratos|/cruceros-baratos"
  "Cruceros Premium|/cruceros-premium"
  "Cruceros de Lujo|/cruceros-de-lujo"
  "Cruceros Novios|/cruceros-novios"
  "Cruceros Todo Incluido|/cruceros-todo-incluido"
  "Minicruceros|/minicruceros"
  "Última hora|/ultima-hora"
  "Primavera|/primavera"
  "Verano|/verano"
  "Otoño|/otono"
  "Invierno|/invierno"
  "Navidad y Fin de Año|/cruceros-navidad-y-fin-de-ano"
  "Cruceros Semana Santa|/semana-santa"
  "Cruceros 2026|/cruceros-2026"
  "Cruceros 2027|/cruceros-2027"
  "Cruceros 2028|/cruceros-2028"
)

# ─── Selección de lista de páginas (--pages) ─────────────────────────────
# default → PAGES (la de siempre) · ig → PAGES_IG
case "$PAGES_SET" in
  ig)      PAGES=("${PAGES_IG[@]}") ;;
  default) ;;   # PAGES tal cual
  *)
    printf 'ERROR: valor de --pages no reconocido: "%s" (disponibles: default, ig)\n' "$PAGES_SET" >&2
    exit 1
    ;;
esac

# ─── Interno (no hace falta tocar) ──────────────────────────────────────
CURL_OPTS=(-sL --compressed --max-time 15 -A "get-titles.sh/1.0")

# Escapa una cadena para poder incrustarla en JSON
json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"    # backslash
  s="${s//\"/\\\"}"    # comillas dobles
  s="${s//$'\t'/ }"    # tabulador
  s="${s//$'\r'/}"     # retorno de carro
  s="${s//$'\n'/ }"    # salto de línea
  printf '%s' "$s"
}

# Devuelve el texto de <title> de una URL (vacío si falla)
fetch_title() {
  local url="$1" html
  html="$(curl "${CURL_OPTS[@]}" "$url" 2>/dev/null || true)"
  printf '%s' "$html" \
    | tr '\n' ' ' \
    | grep -oiP '<title[^>]*>\s*\K.*?(?=\s*</title>)' \
    | head -n1 \
    | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//'
}

# ─── Generar JSON ───────────────────────────────────────────────────────
first=1
printf '[\n'
for entry in "${PAGES[@]}"; do
  name="${entry%%|*}"
  path="${entry#*|}"

  # entrada con URL completa → ignora BASE_URL
  if [[ "$path" == http* ]]; then
    url="$path"
  else
    url="${BASE_URL}${path}"
  fi

  title="$(fetch_title "$url")"

  if [[ -z "$title" ]]; then
    printf 'AVISO: sin <title> en %s\n' "$url" >&2
  fi

  (( first )) || printf ',\n'
  first=0
  printf '  {"name": "%s", "url": "%s", "title": "%s"}' \
    "$(json_escape "$name")" \
    "$(json_escape "$url")" \
    "$(json_escape "$title")"
done
printf '\n]\n'
