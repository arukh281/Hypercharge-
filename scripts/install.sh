#!/usr/bin/env bash
set -euo pipefail

HYPERCHARGE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${HYPERCHARGE_ROOT}/.venv"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 required (3.11+)" >&2
  exit 1
fi

if [[ ! -d "${VENV}" ]]; then
  python3 -m venv "${VENV}"
fi

# shellcheck source=/dev/null
source "${VENV}/bin/activate"
pip install -e "${HYPERCHARGE_ROOT}" -q

GIT_ROOT=""
if git -C "${HYPERCHARGE_ROOT}/.." rev-parse --show-toplevel >/dev/null 2>&1; then
  GIT_ROOT="$(git -C "${PWD}" rev-parse --show-toplevel 2>/dev/null || true)"
fi

echo ""
echo "Hypercharger install: ${VENV}"
echo ""

if [[ -n "${GIT_ROOT}" && -d "${GIT_ROOT}/.git" ]]; then
  echo "Git repo detected — running onboard..."
  exec hypercharge --plain onboard --path "${GIT_ROOT}" "$@"
else
  exec hypercharge install "$@"
fi
