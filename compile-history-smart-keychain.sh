#!/bin/bash
set -euo pipefail

VAULT="${1:-$HOME/Documents/Second Brain by Dogan}"
VAULT="${VAULT/#\~/$HOME}"
shift || true

ACCOUNT="${USER:-$(id -un)}"

load_keychain() {
  local env_name="$1"
  local service="$2"
  local current="${!env_name:-}"
  if [ -n "$current" ]; then
    return 0
  fi
  local value=""
  value="$(security find-generic-password -a "$ACCOUNT" -s "$service" -w 2>/dev/null || true)"
  if [ -n "$value" ]; then
    export "$env_name=$value"
  fi
  unset value
}

load_keychain GROQ_API_KEY "Pijkard SecondBrain Groq"
load_keychain GEMINI_API_KEY "Pijkard SecondBrain Gemini"
load_keychain OPENROUTER_API_KEY "Pijkard SecondBrain OpenRouter"

[ -n "${GROQ_API_KEY:-}" ] && echo "Groq credential: macOS Keychain/environment"
[ -n "${GEMINI_API_KEY:-}" ] && echo "Gemini credential: macOS Keychain/environment"
[ -n "${OPENROUTER_API_KEY:-}" ] && echo "OpenRouter credential: macOS Keychain/environment"

export SECOND_BRAIN_LLM_PRIORITY="${SECOND_BRAIN_LLM_PRIORITY:-groq,gemini,openrouter,ollama}"
export SECOND_BRAIN_PROVIDER_COOLDOWN="${SECOND_BRAIN_PROVIDER_COOLDOWN:-60}"

export SECOND_BRAIN_GROQ_FAST="${SECOND_BRAIN_GROQ_FAST:-qwen/qwen3.6-27b}"
export SECOND_BRAIN_GROQ_SMART="${SECOND_BRAIN_GROQ_SMART:-qwen/qwen3.8-27b}"
export SECOND_BRAIN_GEMINI_FAST="${SECOND_BRAIN_GEMINI_FAST:-gemini-2.5-flash-lite}"
export SECOND_BRAIN_GEMINI_SMART="${SECOND_BRAIN_GEMINI_SMART:-gemini-2.5-flash}"
export SECOND_BRAIN_OPENROUTER_FAST="${SECOND_BRAIN_OPENROUTER_FAST:-openrouter/free}"
export SECOND_BRAIN_OPENROUTER_SMART="${SECOND_BRAIN_OPENROUTER_SMART:-openrouter/free}"

export SECOND_BRAIN_CLOUD_CHUNK_CHARS="${SECOND_BRAIN_CLOUD_CHUNK_CHARS:-12000}"
export SECOND_BRAIN_OLLAMA_THREADS="${SECOND_BRAIN_OLLAMA_THREADS:-2}"
export SECOND_BRAIN_OLLAMA_BATCH="${SECOND_BRAIN_OLLAMA_BATCH:-16}"
export SECOND_BRAIN_OLLAMA_CTX="${SECOND_BRAIN_OLLAMA_CTX:-8192}"
export SECOND_BRAIN_OLLAMA_COOLDOWN="${SECOND_BRAIN_OLLAMA_COOLDOWN:-8}"
export SECOND_BRAIN_SESSION_COOLDOWN="${SECOND_BRAIN_SESSION_COOLDOWN:-2}"

PROGRESS_SCRIPT="$VAULT/.second-brain/scripts/compile_history_smart_progress.py"
SMART_SCRIPT="$VAULT/.second-brain/scripts/compile_history_smart.py"

if [ -f "$PROGRESS_SCRIPT" ]; then
  exec python3 "$PROGRESS_SCRIPT" "$@"
elif [ -f "$SMART_SCRIPT" ]; then
  exec python3 "$SMART_SCRIPT" "$@"
else
  echo "ERROR: smart history compiler is not installed in vault." >&2
  exit 2
fi
