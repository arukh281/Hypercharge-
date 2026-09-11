#!/usr/bin/env bash
# hypercharge-managed — resolve python for hooks
resolve_hc_python() {
  local root="$1"
  local runtime="$root/.cursor/hypercharge/runtime.json"
  local py=""
  if [ -f "$runtime" ]; then
    py="$(python3 -c "import json; print(json.load(open('$runtime')).get('hypercharge_python',''))" 2>/dev/null || true)"
    if [ -n "$py" ] && [ -x "$py" ] && "$py" -m hypercharge --version >/dev/null 2>&1; then
      echo "$py"
      return 0
    fi
  fi
  for candidate in "$root/.venv/bin/python" "$(command -v python3 2>/dev/null || true)" "$(command -v python 2>/dev/null || true)"; do
    [ -z "$candidate" ] && continue
    [ -x "$candidate" ] || continue
    if "$candidate" -m hypercharge --version >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}
