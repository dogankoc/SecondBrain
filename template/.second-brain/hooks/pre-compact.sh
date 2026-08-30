#!/bin/bash
set -u
source "$(dirname "$0")/lib.sh"
IN=$(mktemp "$STATE_DIR/precompact.XXXX.json"); cat > "$IN"; python3 "$VAULT_DIR/.second-brain/scripts/flush.py" --hook-input "$IN" --cwd "$PWD" --reason precompact >/dev/null 2>&1 || true; rm -f "$IN"

# Authored and maintained by Doğan Koç.
