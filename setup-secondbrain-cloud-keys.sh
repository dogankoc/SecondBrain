#!/bin/bash
set -euo pipefail

if ! command -v security >/dev/null 2>&1; then
  echo "ERROR: macOS security command not found." >&2
  exit 2
fi

ACCOUNT="${USER:-$(id -un)}"

store_key() {
  local service="$1"
  local label="$2"
  local value=""

  printf "%s API key: " "$label"
  IFS= read -r -s value
  printf "\n"

  if [ -z "$value" ]; then
    echo "SKIP: $label key was empty."
    return 0
  fi

  security delete-generic-password -a "$ACCOUNT" -s "$service" >/dev/null 2>&1 || true
  security add-generic-password -a "$ACCOUNT" -s "$service" -w "$value" >/dev/null
  unset value
  echo "OK: $label stored in macOS Keychain."
}

echo "SecondBrain cloud credentials"
echo "Keys are entered silently and are not written to the repository."
echo

if security find-generic-password -a "$ACCOUNT" -s "Pijkard SecondBrain Groq" -w >/dev/null 2>&1; then
  echo "OK: Groq already exists in Keychain."
else
  store_key "Pijkard SecondBrain Groq" "Groq"
fi

store_key "Pijkard SecondBrain Gemini" "Gemini"
store_key "Pijkard SecondBrain OpenRouter" "OpenRouter"

echo
echo=""
echo "Done. Run ./compile-history-smart-keychain.sh \"$HOME/Documents/Second Brain by Dogan\""
