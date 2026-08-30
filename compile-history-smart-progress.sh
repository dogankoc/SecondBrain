#!/bin/bash
set -euo pipefail

VAULT="${1:-$HOME/Documents/Second Brain}"
VAULT="${VAULT/#\~/$HOME}"
shift || true

SCRIPT="$VAULT/.second-brain/scripts/compile_history_smart_progress.py"

if [ ! -f "$SCRIPT" ]; then
  echo "ERROR: smart history progress compiler is not installed in vault:" >&2
  echo "  $SCRIPT" >&2
  exit 2
fi

# macOS Keychain fallback for Groq. No secret is logged or written to the repo.
if [ -z "${GROQ_API_KEY:-}" ] && command -v security >/dev/null 2>&1; then
  KEY="$(security find-generic-password -a "${USER:-}" -s "Pijkard SecondBrain Groq" -w 2>/dev/null || true)"
  if [ -n "$KEY" ]; then
    export GROQ_API_KEY="$KEY"
    unset KEY
    echo "Groq credential: macOS Keychain"
  fi
fi

export SECOND_BRAIN_LLM_PRIORITY="${SECOND_BRAIN_LLM_PRIORITY:-groq,ollama}"
export SECOND_BRAIN_PROVIDER_COOLDOWN="${SECOND_BRAIN_PROVIDER_COOLDOWN:-600}"
export SECOND_BRAIN_GROQ_RATE_RETRIES="${SECOND_BRAIN_GROQ_RATE_RETRIES:-8}"
export SECOND_BRAIN_GROQ_MAX_RETRY_WAIT="${SECOND_BRAIN_GROQ_MAX_RETRY_WAIT:-45}"
export SECOND_BRAIN_CLOUD_CHUNK_CHARS="${SECOND_BRAIN_CLOUD_CHUNK_CHARS:-12000}"

export SECOND_BRAIN_OLLAMA_THREADS="${SECOND_BRAIN_OLLAMA_THREADS:-2}"
export SECOND_BRAIN_OLLAMA_BATCH="${SECOND_BRAIN_OLLAMA_BATCH:-16}"
export SECOND_BRAIN_OLLAMA_CTX="${SECOND_BRAIN_OLLAMA_CTX:-8192}"
export SECOND_BRAIN_OLLAMA_COOLDOWN="${SECOND_BRAIN_OLLAMA_COOLDOWN:-8}"
export SECOND_BRAIN_SESSION_COOLDOWN="${SECOND_BRAIN_SESSION_COOLDOWN:-10}"

exec python3 "$SCRIPT" "$@"
