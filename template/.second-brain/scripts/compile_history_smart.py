#!/usr/bin/env python3
from __future__ import annotations

import os
import time

import common
import compile_history as base
from history_prefilter import prefilter_transcript

# History compilation should use free cloud providers first and local Ollama last.
# Paid/interactive CLI providers remain available only when explicitly requested.
os.environ.setdefault(
    "SECOND_BRAIN_LLM_PRIORITY",
    "groq,gemini,openrouter,ollama",
)

_original_chunks = base.chunks
_original_save_state = base.save_state
_initial_state = base.load_state()
_initial_compiled = _initial_state.get("compiled", {}) if isinstance(_initial_state, dict) else {}
_last_compiled_count = len(_initial_compiled) if isinstance(_initial_compiled, dict) else 0
_total_sessions = len(base.discover_sessions())


def _cloud_chunk_size(default: int = 14000) -> int:
    """Keep free-tier cloud requests safely below low per-minute token limits."""
    try:
        value = int(os.environ.get("SECOND_BRAIN_CLOUD_CHUNK_CHARS", str(default)))
    except ValueError:
        value = default
    return max(6000, min(value, base.CHUNK_CHARS))


def filtered_chunks(text: str, size: int = base.CHUNK_CHARS):
    filtered, stats = prefilter_transcript(text)
    before = _original_chunks(text, size)
    target_size = _cloud_chunk_size()
    after = _original_chunks(filtered, target_size)
    print(
        f"  PREFILTER chars={stats.original_chars}->{stats.filtered_chars} "
        f"reduction={stats.reduction_percent:.1f}% "
        f"chunks={len(before)}->{len(after)} "
        f"target_chars={target_size}",
        flush=True,
    )
    return after


def smart_run_model(prompt, tier="fast", timeout=300, provider="auto"):
    # History extraction always requires machine-parseable JSON.
    return common.run_model(
        prompt,
        tier=tier,
        timeout=timeout,
        provider=provider,
        json_mode=True,
    )


def save_state_with_progress(data):
    global _last_compiled_count

    compiled = data.get("compiled", {}) if isinstance(data, dict) else {}
    current_count = len(compiled) if isinstance(compiled, dict) else 0

    _original_save_state(data)

    if current_count <= _last_compiled_count:
        return

    _last_compiled_count = current_count

    total = _total_sessions or current_count
    remaining = max(0, total - current_count)
    percent = (current_count / total * 100.0) if total else 100.0
    width = 30
    filled = round(percent / 100.0 * width)
    bar = "█" * filled + "░" * (width - filled)

    print(
        f"  PROGRESS [{bar}] {percent:.1f}%  "
        f"Tamamlanan {current_count}/{total}  Kalan {remaining}",
        flush=True,
    )

    try:
        cooldown = float(os.environ.get("SECOND_BRAIN_SESSION_COOLDOWN", "10"))
    except ValueError:
        cooldown = 10.0

    if cooldown > 0:
        print(
            f"  COOLING session complete — waiting {cooldown:g}s",
            flush=True,
        )
        time.sleep(cooldown)


base.chunks = filtered_chunks
base.run_model = smart_run_model
base.save_state = save_state_with_progress


def provider_summary() -> None:
    priority = os.environ.get(
        "SECOND_BRAIN_LLM_PRIORITY",
        "groq,gemini,openrouter,ollama",
    )

    configured = []
    if os.environ.get("GROQ_API_KEY"):
        configured.append("groq")
    if os.environ.get("GEMINI_API_KEY"):
        configured.append("gemini")
    if os.environ.get("OPENROUTER_API_KEY"):
        configured.append("openrouter")
    configured.append("ollama")

    print("HYBRID LLM ROUTER", flush=True)
    print(f"  priority={priority}", flush=True)
    print(f"  available/configured={','.join(configured)}", flush=True)
    print(f"  cloud_chunk_chars={_cloud_chunk_size()}", flush=True)

    cooldowns = []
    for provider in ("groq", "gemini", "openrouter", "ollama"):
        try:
            remaining = common._cooldown_remaining(provider)
        except Exception:
            remaining = 0
        if remaining > 0:
            cooldowns.append(f"{provider}:{remaining}s")
    print(
        f"  provider_cooldowns={','.join(cooldowns) if cooldowns else 'none'}",
        flush=True,
    )
    print(
        "  cloud keys are read from environment only; key values are never logged",
        flush=True,
    )


if __name__ == "__main__":
    provider_summary()
    raise SystemExit(base.main())
