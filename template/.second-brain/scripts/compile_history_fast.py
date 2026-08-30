#!/usr/bin/env python3
from __future__ import annotations

import compile_history as base
from history_prefilter import prefilter_transcript

_original_chunks = base.chunks


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


base.chunks = filtered_chunks

if __name__ == "__main__":
    raise SystemExit(base.main())
