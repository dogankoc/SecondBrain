#!/bin/bash
set -euo pipefail

VAULT="${1:-$HOME/Documents/Second Brain}"
VAULT="${VAULT/#\~/$HOME}"
shift || true

SCRIPT="$VAULT/.second-brain/scripts/compile_history_smart.py"

if [ ! -f "$SCRIPT" ]; then
  echo "ERROR: smart history compiler is not installed in vault:" >&2
  echo "  $SCRIPT" >&2
  echo >&2
  echo "Update the vault engine from this repository before running." >&2
  exit 2
fi

export SECOND_BRAIN_LLM_PRIORITY="${SECOND_BRAIN_LLM_PRIORITY:-groq,gemini,openrouter,ollama}"
export SECOND_BRAIN_PROVIDER_COOLDOWN="${SECOND_BRAIN_PROVIDER_COOLDOWN:-600}"

# Groq free-tier TPM windows commonly ask for ~20-35s retries. Prefer waiting
# for Groq over immediately heating the local Ollama fallback.
export SECOND_BRAIN_GROQ_RATE_RETRIES="${SECOND_BRAIN_GROQ_RATE_RETRIES:-8}"
export SECOND_BRAIN_GROQ_MAX_RETRY_WAIT="${SECOND_BRAIN_GROQ_MAX_RETRY_WAIT:-45}"

# Conservative local fallback defaults. They are used only when Ollama is reached.
export SECOND_BRAIN_OLLAMA_THREADS="${SECOND_BRAIN_OLLAMA_THREADS:-2}"
export SECOND_BRAIN_OLLAMA_BATCH="${SECOND_BRAIN_OLLAMA_BATCH:-16}"
export SECOND_BRAIN_OLLAMA_CTX="${SECOND_BRAIN_OLLAMA_CTX:-8192}"
export SECOND_BRAIN_OLLAMA_COOLDOWN="${SECOND_BRAIN_OLLAMA_COOLDOWN:-8}"
export SECOND_BRAIN_SESSION_COOLDOWN="${SECOND_BRAIN_SESSION_COOLDOWN:-10}"

exec python3 "$SCRIPT" "$@"
