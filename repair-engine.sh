#!/bin/bash
set -euo pipefail
TARGET="${1:-$HOME/Documents/Second Brain}"
TARGET="${TARGET/#\~/$HOME}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
[ -d "$TARGET" ] || { echo "Vault not found: $TARGET" >&2; exit 2; }
rm -rf "$TARGET/.second-brain/hooks" "$TARGET/.second-brain/scripts" "$TARGET/.second-brain/skills"
mkdir -p "$TARGET/.second-brain"
cp -R "$ROOT/template/.second-brain"/. "$TARGET/.second-brain"/
chmod +x "$TARGET/.second-brain/hooks/"*.sh "$TARGET/.second-brain/scripts/"*.py 2>/dev/null || true
echo "ENGINE_REPAIRED: $(cat "$TARGET/.second-brain/ENGINE_VERSION" 2>/dev/null || echo unknown)"
