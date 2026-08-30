#!/usr/bin/env python3
from __future__ import annotations

import re

import compile_history_smart as smart

base = smart.base
_original_smart_run_model = smart.smart_run_model

_CHUNK_RE = re.compile(r"(?m)^chunk=(\d+)/(\d+)\s*$")


def smart_run_model_with_chunk_progress(
    prompt: str,
    tier: str = "fast",
    timeout: int = 300,
    provider: str = "auto",
):
    match = _CHUNK_RE.search(prompt)
    idx = int(match.group(1)) if match else 0
    total = int(match.group(2)) if match else 0

    if idx and total:
        remaining_before = max(0, total - idx + 1)
        print(
            f"  CHUNK ▶ {idx}/{total}  Kalan {remaining_before}",
            flush=True,
        )

    out, err = _original_smart_run_model(
        prompt,
        tier=tier,
        timeout=timeout,
        provider=provider,
    )

    if idx and total:
        if err:
            print(
                f"  CHUNK ✗ {idx}/{total}  Hata — kalan {max(0, total - idx + 1)}",
                flush=True,
            )
        else:
            done_percent = idx / total * 100.0
            width = 24
            filled = round(done_percent / 100.0 * width)
            bar = "█" * filled + "░" * (width - filled)
            print(
                f"  CHUNK ✓ [{bar}] {idx}/{total}  "
                f"Kalan {max(0, total - idx)}  %{done_percent:.1f}",
                flush=True,
            )

    return out, err


base.run_model = smart_run_model_with_chunk_progress


if __name__ == "__main__":
    smart.provider_summary()
    raise SystemExit(base.main())
