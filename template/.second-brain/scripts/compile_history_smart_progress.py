#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import os
import re

import compile_history_smart as smart

base = smart.base
common = smart.common

_CHUNK_RE = re.compile(r"(?m)^chunk=(\d+)/(\d+)\s*$")


def _env_timeout(name: str, default: int) -> int:
    try:
        return max(5, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _provider_timeout(provider: str) -> int:
    return {
        "groq": _env_timeout("SECOND_BRAIN_GROQ_TIMEOUT", 45),
        "gemini": _env_timeout("SECOND_BRAIN_GEMINI_TIMEOUT", 60),
        "openrouter": _env_timeout("SECOND_BRAIN_OPENROUTER_TIMEOUT", 25),
        "ollama": _env_timeout("SECOND_BRAIN_OLLAMA_TIMEOUT", 300),
    }.get(provider, 60)


def _valid_json_object(text: str | None) -> bool:
    if not text:
        return False
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
    try:
        value = json.loads(cleaned)
    except Exception:
        return False
    return isinstance(value, dict) and isinstance(value.get("items", []), list)


def _short_reason(err: str | None) -> str:
    text = str(err or "empty").lower()
    if "cooldown" in text:
        m = re.search(r"cooldown-(\d+)s", text)
        return f"cooldown {m.group(1)}s" if m else "cooldown"
    if "http-429" in text or "rate_limit" in text or "rate limit" in text:
        return "rate limit"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "http-404" in text:
        return "model unavailable"
    if "http-401" in text or "http-403" in text:
        return "auth/access"
    if "missing-key" in text:
        return "key missing"
    if "bad-response" in text or "empty" in text:
        return "invalid response"
    return "request failed"


def _quiet_call(provider: str, prompt: str, tier: str):
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        out, err = common.run_model(
            prompt,
            tier=tier,
            timeout=_provider_timeout(provider),
            provider=provider,
            json_mode=True,
        )
    if err or not out:
        return None, _short_reason(err)
    if not _valid_json_object(out):
        return None, "invalid JSON"
    return out, None


def _cloud_order() -> list[str]:
    clouds = smart._configured_clouds()
    if not clouds:
        return []
    start = smart._cloud_rr_index % len(clouds)
    smart._cloud_rr_index += 1
    return clouds[start:] + clouds[:start]


def human_run_model(
    prompt: str,
    tier: str = "fast",
    timeout: int = 300,
    provider: str = "auto",
):
    match = _CHUNK_RE.search(prompt)
    idx = int(match.group(1)) if match else 0
    total = int(match.group(2)) if match else 0

    if provider and provider != "auto":
        order = [provider]
    else:
        order = _cloud_order()
        if "ollama" not in order:
            order.append("ollama")

    label = f"  Chunk {idx}/{total}" if idx and total else "  Chunk"
    failures: list[str] = []

    for candidate in order:
        out, reason = _quiet_call(candidate, prompt, tier)
        if out:
            suffix = ""
            if failures:
                suffix = "  (" + ", ".join(failures) + ")"
            print(f"{label}  ✓ {candidate.capitalize()}{suffix}", flush=True)
            return out, None
        failures.append(f"{candidate.capitalize()}: {reason}")

    print(f"{label}  ✗ " + ", ".join(failures), flush=True)
    return None, "; ".join(failures)


def quiet_chunks(text: str, size: int = base.CHUNK_CHARS):
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        result = smart.filtered_chunks(text, size)
    print(f"  Hazır: {len(result)} chunk", flush=True)
    return result


base.chunks = quiet_chunks
base.run_model = human_run_model


def provider_summary() -> None:
    clouds = smart._configured_clouds()
    cloud_text = " → ".join(x.capitalize() for x in clouds) if clouds else "yok"
    print("SECOND BRAIN · HISTORY COMPILER", flush=True)
    print(f"  Cloud: {cloud_text}", flush=True)
    print("  Local fallback: Ollama", flush=True)
    print(
        "  Timeout: Groq 45s · Gemini 60s · OpenRouter 25s · Ollama 300s",
        flush=True,
    )
    print("  Mod: round-robin + otomatik fallback + JSON doğrulama", flush=True)
    print("", flush=True)


if __name__ == "__main__":
    provider_summary()
    raise SystemExit(base.main())
