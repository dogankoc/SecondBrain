#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
for f in "$ROOT"/*.sh "$ROOT"/template/.second-brain/hooks/*.sh; do bash -n "$f"; done
python3 -m py_compile "$ROOT"/template/.second-brain/scripts/*.py
echo VERIFY_OK

# Authored and maintained by Doğan Koç.
