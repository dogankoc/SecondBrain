#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
for f in "$ROOT"/*.sh "$ROOT"/template/.second-brain/hooks/*.sh; do bash -n "$f"; done
python3 -m py_compile "$ROOT"/template/.second-brain/scripts/*.py
if grep -RniE 'Doğan|Dogan|dogan|dogankoc' "$ROOT" --exclude='*.zip' --exclude='verify.sh' --exclude-dir='.git'; then
  echo "Forbidden personal identifier found" >&2
  exit 9
fi
echo VERIFY_OK
