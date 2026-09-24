#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -r /etc/os-release ]]; then
  echo "ERROR setup: /etc/os-release is unavailable; automatic controller bootstrap supports Ubuntu 24.04." >&2
  exit 2
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "24.04" ]]; then
  echo "ERROR setup: automatic OS prerequisite installation currently supports Ubuntu 24.04 only." >&2
  echo "Detected: ${PRETTY_NAME:-unknown}" >&2
  exit 2
fi

if (( EUID == 0 )); then
  APT=(apt-get)
elif command -v sudo >/dev/null 2>&1; then
  APT=(sudo apt-get)
else
  echo "ERROR setup: root privileges or sudo are required to install controller prerequisites." >&2
  exit 2
fi

PACKAGES=(python3 python3-yaml python3-venv openssh-client ca-certificates)
MISSING=()
for package in "${PACKAGES[@]}"; do
  if [[ "$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)" != "install ok installed" ]]; then
    MISSING+=("$package")
  fi
done
if (( ${#MISSING[@]} )); then
  echo "==> Installing missing Solo VPS controller prerequisites"
  "${APT[@]}" update
  "${APT[@]}" install -y --no-install-recommends "${MISSING[@]}"
else
  echo "PASS controller OS prerequisites already installed"
fi

echo "==> Ensuring a controller SSH identity"
python3 scripts/ensure_ssh_key.py

echo "PASS controller OS prerequisites"
