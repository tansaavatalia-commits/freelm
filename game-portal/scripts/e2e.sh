#!/usr/bin/env bash
# Avvia API (D1 locale), giochi e portale; esegue il test E2E nel browser; ferma tutto.
# Uso: pnpm e2e   (richiede Chromium + Playwright installati sulla macchina)
set -uo pipefail
cd "$(dirname "$0")/.."
LOG="$(mktemp -d)"
groups=()

cleanup() {
  for g in "${groups[@]}"; do kill -TERM -- "-$g" 2>/dev/null || true; done
  sleep 1
  for g in "${groups[@]}"; do kill -KILL -- "-$g" 2>/dev/null || true; done
}
trap cleanup EXIT

# Ogni server in un proprio gruppo di processi (setsid), così la chiusura è completa.
start() { local dir="$1" name="$2"; shift 2; setsid bash -c "cd '$dir' && exec $*" > "$LOG/$name.log" 2>&1 & groups+=($!); }

for port in 8787 5174 4173; do
  if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$port/"; then echo "Porta $port già occupata: chiudi il processo che la usa." >&2; exit 1; fi
done

TOKEN="$(node -e "console.log(require('crypto').randomBytes(24).toString('hex'))")"
printf 'ADMIN_TOKEN=%s\n' "$TOKEN" > backend/.dev.vars
export WRANGLER_SEND_METRICS=false
pnpm build > "$LOG/build.log" 2>&1 || { echo "Build fallita: $LOG/build.log" >&2; exit 1; }
(cd backend && npx wrangler d1 migrations apply tabluo --local > "$LOG/migrate.log" 2>&1) || { echo "Migrazione fallita: $LOG/migrate.log" >&2; exit 1; }
start backend api npx wrangler dev --local --port 8787 --ip 127.0.0.1
start games games npx vite preview --port 5174 --strictPort --host 127.0.0.1
start frontend web npx vite preview --port 4173 --strictPort --host 127.0.0.1

for _ in $(seq 1 90); do
  if curl -fs --max-time 2 http://127.0.0.1:8787/api/v1/health >/dev/null && curl -fs --max-time 2 http://127.0.0.1:5174/mines/index.html >/dev/null && curl -fs --max-time 2 http://127.0.0.1:4173/ >/dev/null; then
    ADMIN_TOKEN="$TOKEN" node tests/e2e/smoke.mjs
    status=$?
    [ $status -ne 0 ] && echo "Log dei server: $LOG" >&2
    exit $status
  fi
  sleep 0.5
done
echo "Server non pronti entro 45 s; log in $LOG" >&2
exit 1
