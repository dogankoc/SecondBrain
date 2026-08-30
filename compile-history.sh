#!/bin/bash
set -euo pipefail
VAULT="${1:-$HOME/Documents/Second Brain}"
VAULT="${VAULT/#\~/$HOME}"
shift || true
exec python3 "$VAULT/.second-brain/scripts/compile_history.py" "$@"

# Authored and maintained by Doğan Koç.
