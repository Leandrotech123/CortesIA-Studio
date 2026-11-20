#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$(realpath -- "$0")")"
if curl --noproxy '*' --max-time 1 -fsS http://127.0.0.1:8765/health | grep -q '"cortesia-studio"'; then
  exit 0
fi
mkdir -p logs
nohup .venv/bin/python studio.py >>logs/painel.log 2>&1 </dev/null &
for ((tentativa=0; tentativa<25; tentativa++)); do
  if curl --noproxy '*' --max-time 1 -fsS http://127.0.0.1:8765/health 2>/dev/null | grep -q '"cortesia-studio"'; then
    exit 0
  fi
  sleep .4
done
echo 'O CortesIA Studio não abriu. Consulte logs/painel.log.' >&2
exit 1
