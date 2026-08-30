#!/bin/bash
set -euo pipefail
if [ $# -lt 2 ]; then echo "Usage: $0 <source-vault> <destination-vault>" >&2; exit 2; fi
SRC="${1/#\~/$HOME}"; DST="${2/#\~/$HOME}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
[ -d "$SRC" ] || { echo "Source vault not found: $SRC" >&2; exit 3; }
mkdir -p "$DST"; cp -R "$SRC"/. "$DST"/
"$ROOT/install.sh" --path "$DST" --upgrade
echo "MIGRATED: $SRC -> $DST"
echo "Source vault was not deleted."

# Authored and maintained by Doğan Koç.
