# Autocompletado bash para xtool
# Fuente desde ~/.bashrc:
#   source ~/.local/share/xtool/completions/xtool.bash
#
# La lista de comandos se genera dinámicamente desde `xtool`
# (los tools nuevos en xtool/tools/ autocompletean solos).

_xtool() {
  local cur prev cmd commands
  COMPREPLY=()
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"
  cmd="${COMP_WORDS[1]}"

  # Comandos: parsea la sección "Comandos disponibles:" de la salida de xtool
  commands="$(xtool 2>/dev/null | awk '/^Comandos disponibles:/{f=1;next} f&&NF{print $1}')"
  if [[ -z "$commands" ]]; then
    # Fallback estático si xtool no responde
    commands="emails git-cherry git-deploy git-diff kill-port"
  fi
  commands="$commands help"

  if [[ $COMP_CWORD -eq 1 ]]; then
    COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
    return 0
  fi

  case "$cmd" in
    help)
      COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
      ;;
    emails)
      if [[ "$prev" == "--port" ]]; then
        return 0
      fi
      if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "--port --no-install -h --help" -- "$cur") )
      elif [[ $COMP_CWORD -eq 2 ]]; then
        COMPREPLY=( $(compgen -W "server build watch extract" -- "$cur") )
      fi
      ;;
    git-cherry)
      if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "-f --force -h --help" -- "$cur") )
      else
        # Acepta ruta de repo local o hash de commit
        COMPREPLY=( $(compgen -d -S/ -- "$cur") )
      fi
      ;;
    git-deploy)
      if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "-y --yes -f --force --no-push -h --help" -- "$cur") )
      else
        # Commit o rango: hashes recientes del repo actual + atajos útiles
        COMPREPLY=( $(compgen -W "HEAD HEAD~1 HEAD~2 HEAD~3 $(git log --format='%h' -10 2>/dev/null)" -- "$cur") )
      fi
      ;;
    git-diff|kill-port)
      # Sin opciones: no proponer nada
      ;;
    *)
      COMPREPLY=( $(compgen -f -- "$cur") )
      ;;
  esac
  return 0
}

complete -o bashdefault -o default -F _xtool xtool
complete -o bashdefault -o default -F _xtool x
