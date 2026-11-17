#!/usr/bin/env bash
# Guarda/recupera la memoria del bot en la rama `trading-state` del propio repo.
# Así el bot "recuerda" entre ejecuciones de GitHub Actions (que empiezan de cero).
#   deploy/gh_state.sh load state     # trae la rama a ./state (o la crea vacía)
#   deploy/gh_state.sh save state     # sube los cambios de ./state a la rama
set -euo pipefail
action="$1"; dir="${2:-state}"; branch="${STATE_BRANCH:-trading-state}"

if [ "$action" = load ]; then
  if git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
    git fetch -q --depth 1 origin "$branch"
    git worktree add -q -B "$branch" "$dir" FETCH_HEAD
  else
    git worktree add -q --detach "$dir"
    (cd "$dir" && git checkout -q --orphan "$branch" && git rm -rq --cached --ignore-unmatch . && find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +)
  fi
elif [ "$action" = save ]; then
  cd "$dir"
  git add -A
  if git diff --cached --quiet; then echo "sin cambios"; exit 0; fi
  git -c user.name="trading-bot" -c user.email="trading-bot@users.noreply.github.com" \
    commit -qm "estado $(date -u +%Y-%m-%dT%H:%MZ)"
  for i in 1 2 3; do git push -q origin "HEAD:$branch" && exit 0; sleep $((i * 5)); done
  exit 1
else
  echo "uso: $0 load|save [carpeta]" >&2; exit 2
fi
