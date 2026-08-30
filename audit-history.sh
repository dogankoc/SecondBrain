#!/bin/bash
set -euo pipefail

VAULT="${1:-$HOME/Documents/Second Brain by Dogan}"
VAULT="${VAULT/#\~/$HOME}"
shift || true

SCRIPT="$VAULT/.second-brain/scripts/audit_history.py"

if [ ! -f "$SCRIPT" ]; then
  echo "ERROR: audit_history.py vault içinde bulunamadı." >&2
  echo "Önce template/.second-brain/scripts/audit_history.py dosyasını vault'a kopyalayın." >&2
  exit 2
fi

exec python3 "$SCRIPT" "$@"
