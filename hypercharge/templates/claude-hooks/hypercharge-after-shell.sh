#!/usr/bin/env bash
# hypercharge-managed — synced by hypercharge setup
set -euo pipefail
INPUT="$(cat)"
ROOT="$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("cwd") or "")' 2>/dev/null || true)"
[ -z "$ROOT" ] && ROOT="$(pwd)"
# shellcheck source=/dev/null
source "$ROOT/.claude/hooks/_hypercharge-python.sh" 2>/dev/null || source "$(dirname "$0")/_hypercharge-python.sh"
PY="$(resolve_hc_python "$ROOT" || true)"
if [ -z "$PY" ]; then
  echo '{}'
  exit 0
fi
printf '%s' "$INPUT" | "$PY" -m hypercharge --plain hooks after-shell --format claude --path "$ROOT"
