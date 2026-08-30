#!/usr/bin/env python3
from __future__ import annotations

import os
import time

import compile_history as base
from history_prefilter import prefilter_transcript

_original_chunks = base.chunks
_original_save_state = base.save_state
_last_compiled_count: int | None = None


def filtered_chunks(text: str, size: int = base.CHUNK_CHARS):
    filtered, stats = prefilter_transcript(text)
    before = _original_chunks(text, size)
    after = _original_chunks(filtered, size)
    print(
        f"  PREFILTER chars={stats.original_chars}->{stats.filtered_chars} "
        f"reduction={stats.reduction_percent:.1f}% "
        f"chunks={len(before)}->{len(after)}"
    )
    return after


def save_state_with_cooldown(data):
    global _last_compiled_count

    compiled = data.get("compiled", {}) if isinstance(data, dict) else {}
    current_count = len(compiled) if isinstance(compiled, dict) else 0

    _original_save_state(data)

    if _last_compiled_count is None:
        _last_compiled_count = current_count
        return

    if current_count <= _last_compiled_count:
        return

    _last_compiled_count = current_count

    try:
        cooldown = float(os.environ.get("SECOND_BRAIN_SESSION_COOLDOWN", "25"))
    except ValueError:
        cooldown = 25.0

    if cooldown <= 0:
        return

    print(f"  COOLING session complete — waiting {cooldown:g}s", flush=True)
    time.sleep(cooldown)


# Seed the initial compiled-session count so the first newly completed session
# also receives a cooldown.
try:
    _state = base.load_state()
    _compiled = _state.get("compiled", {}) if isinstance(_state, dict) else {}
    _last_compiled_count = len(_compiled) if isinstance(_compiled, dict) else 0
except Exception:
    _last_compiled_count = 0

base.chunks = filtered_chunks
base.save_state = save_state_with_cooldown

if __name__ == "__main__":
    raise SystemExit(base.main())
