#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="$1"
RUNTIME_VENV="$2"
COLLECTIONS_DIR="$3"

# Retain the existing venv location for installed controllers. Developer tools
# may share it, but normal setup does not install or require them.
runtime_ready() {
  [[ -x "$RUNTIME_VENV/bin/python" ]] || return 1
  "$RUNTIME_VENV/bin/python" -c '
from importlib.metadata import version
from pathlib import Path
expected = Path("tools/runtime-requirements.txt").read_text().split("ansible-core==", 1)[1].splitlines()[0]
assert version("ansible-core") == expected
' >/dev/null 2>&1 || return 1
  ANSIBLE_COLLECTIONS_PATH="$COLLECTIONS_DIR" "$RUNTIME_VENV/bin/ansible-galaxy" collection list community.general 2>/dev/null |
    awk '$1 == "community.general" && $2 == "13.0.1" { found=1 } END { if (!found) exit 1 }' || return 1
  ANSIBLE_COLLECTIONS_PATH="$COLLECTIONS_DIR" "$RUNTIME_VENV/bin/ansible-doc" -t module community.general.ufw >/dev/null 2>&1
}

if runtime_ready; then
  echo "PASS pinned Ansible runtime already installed (no downloads)"
  exit 0
fi

"$PYTHON_BIN" -m venv "$RUNTIME_VENV"
"$RUNTIME_VENV/bin/python" -m pip install --disable-pip-version-check --no-cache-dir -r tools/runtime-requirements.txt
ANSIBLE_COLLECTIONS_PATH="$COLLECTIONS_DIR" "$RUNTIME_VENV/bin/ansible-galaxy" collection install -r ansible/requirements.yml -p "$COLLECTIONS_DIR"
runtime_ready
echo "PASS pinned Ansible runtime installed"
