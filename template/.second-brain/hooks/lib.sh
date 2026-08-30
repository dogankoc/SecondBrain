#!/bin/bash
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
STATE_DIR="$VAULT_DIR/.second-brain/hooks/.state"
mkdir -p "$STATE_DIR"
json_escape(){ python3 -c 'import json,sys; print(json.dumps(sys.stdin.read(),ensure_ascii=False))'; }

# Authored and maintained by Doğan Koç.
