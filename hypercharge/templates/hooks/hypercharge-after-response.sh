#!/usr/bin/env bash
# hypercharge-managed — synced by hypercharge setup
set -euo pipefail
ROOT="${CURSOR_PROJECT_DIR:-$(pwd)}"
# shellcheck source=/dev/null
source "$ROOT/.cursor/hooks/_hypercharge-python.sh" 2>/dev/null || source "$(dirname "$0")/_hypercharge-python.sh"
PY="$(resolve_hc_python "$ROOT" || true)"
if [ -z "$PY" ]; then
  echo '{"additional_context":"<!-- hypercharge BLOCKED --> Hypercharge runtime missing. Run hypercharge setup.","followup_message":"Cannot verify grounding — run hypercharge setup in this repo."}'
  exit 0
fi
cat | "$PY" -m hypercharge --plain hooks after-response --path "$ROOT"
