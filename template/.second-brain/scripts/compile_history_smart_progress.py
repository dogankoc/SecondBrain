#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import signal
import time

import compile_history_smart as smart

base = smart.base
common = smart.common

_CHUNK_RE = re.compile(r"(?m)^chunk=(\d+)/(\d+)\s*$")

_run_started_at = time.monotonic()
_completed_chunk_durations: list[float] = []
_current_session_started_at: float | None = None
_current_session_total_chunks = 0
_current_session_completed_chunks = 0
_primary_rr_index = 0


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


class _HardTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise _HardTimeout()


def _quiet_call(provider: str, prompt: str, tier: str):
    timeout = _provider_timeout(provider)
    capture = io.StringIO()

    old_handler = None
    can_alarm = hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")
    try:
        if can_alarm:
            old_handler = signal.getsignal(signal.SIGALRM)
            signal.signal(signal.SIGALRM, _alarm_handler)
            signal.setitimer(signal.ITIMER_REAL, timeout)

        with contextlib.redirect_stdout(capture):
            out, err = common.run_model(
                prompt,
                tier=tier,
                timeout=timeout,
                provider=provider,
                json_mode=True,
            )
    except _HardTimeout:
        return None, f"hard timeout {timeout}s"
    finally:
        if can_alarm:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)

    if err or not out:
        return None, _short_reason(err)
    if not _valid_json_object(out):
        return None, "invalid JSON"
    return out, None


def _cloud_order() -> list[str]:
    """Primary rotation is Groq ↔ Gemini; OpenRouter is reserve-only fallback.

    Each new chunk starts with the next primary provider. If it fails or is in
    cooldown, the other primary is tried. OpenRouter is attempted only when both
    primary providers fail for that chunk, preserving its limited free daily quota.
    Ollama is appended later as the final local fallback.
    """
    global _primary_rr_index

    configured = smart._configured_clouds()
    if not configured:
        return []

    configured_set = set(configured)
    primaries = [p for p in ("groq", "gemini") if p in configured_set]

    if primaries:
        preferred = primaries[_primary_rr_index % len(primaries)]
        _primary_rr_index += 1
        order = [preferred] + [p for p in primaries if p != preferred]
    else:
        order = []

    if "openrouter" in configured_set:
        order.append("openrouter")

    for candidate in configured:
        if candidate not in order:
            order.append(candidate)
    return order


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _mean_chunk_duration() -> float | None:
    if not _completed_chunk_durations:
        return None
    sample = _completed_chunk_durations[-30:]
    return sum(sample) / len(sample)


def human_run_model(
    prompt: str,
    tier: str = "fast",
    timeout: int = 300,
    provider: str = "auto",
):
    global _current_session_started_at
    global _current_session_total_chunks
    global _current_session_completed_chunks

    match = _CHUNK_RE.search(prompt)
    idx = int(match.group(1)) if match else 0
    total = int(match.group(2)) if match else 0

    if idx == 1 and total:
        _current_session_started_at = time.monotonic()
        _current_session_total_chunks = total
        _current_session_completed_chunks = 0

    if provider and provider != "auto":
        order = [provider]
    else:
        order = _cloud_order()
        if "ollama" not in order:
            order.append("ollama")

    label = f"  Chunk {idx}/{total}" if idx and total else "  Chunk"
    failures: list[str] = []
    chunk_started_at = time.monotonic()

    for candidate in order:
        out, reason = _quiet_call(candidate, prompt, tier)
        if out:
            elapsed = time.monotonic() - chunk_started_at
            _completed_chunk_durations.append(elapsed)
            _current_session_completed_chunks += 1

            suffix = ""
            if failures:
                suffix = "  (" + ", ".join(failures) + ")"

            avg = _mean_chunk_duration()
            eta_text = ""
            if avg is not None and total:
                remaining_chunks = max(0, total - idx)
                eta_text = f" · session ETA ~{_fmt_duration(avg * remaining_chunks)}"

            print(
                f"{label}  ✓ {candidate.capitalize()} · {_fmt_duration(elapsed)}{eta_text}{suffix}",
                flush=True,
            )

            if total and idx == total and _current_session_started_at is not None:
                session_elapsed = time.monotonic() - _current_session_started_at
                session_avg = (
                    session_elapsed / _current_session_completed_chunks
                    if _current_session_completed_chunks
                    else 0.0
                )
                print(
                    f"  Session ✓ {_fmt_duration(session_elapsed)} · "
                    f"ort. chunk {_fmt_duration(session_avg)}",
                    flush=True,
                )

            return out, None

        failures.append(f"{candidate.capitalize()}: {reason}")

    elapsed = time.monotonic() - chunk_started_at
    print(
        f"{label}  ✗ {_fmt_duration(elapsed)} · " + ", ".join(failures),
        flush=True,
    )
    return None, "; ".join(failures)


def quiet_chunks(text: str, size: int = base.CHUNK_CHARS):
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        result = smart.filtered_chunks(text, size)
    print(f"  Hazır: {len(result)} chunk", flush=True)
    return result


base.chunks = quiet_chunks
base.run_model = human_run_model

_original_save_state = smart.save_state_with_progress


def save_state_with_human_progress(data):
    before = smart._last_compiled_count
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        _original_save_state(data)

    current = smart._last_compiled_count
    if current <= before:
        return

    total = smart._total_sessions or current
    remaining = max(0, total - current)
    percent = (current / total * 100.0) if total else 100.0
    width = 30
    filled = round(percent / 100.0 * width)
    bar = "█" * filled + "░" * (width - filled)

    run_elapsed = time.monotonic() - _run_started_at
    run_session_count = max(1, current - len(smart._initial_compiled))
    avg_session = run_elapsed / run_session_count
    eta = avg_session * remaining

    print(
        f"  GENEL [{bar}] %{percent:.1f} · {current}/{total} tamamlandı · "
        f"Kalan {remaining} · ETA ~{_fmt_duration(eta)}",
        flush=True,
    )

    try:
        cooldown = float(os.environ.get("SECOND_BRAIN_SESSION_COOLDOWN", "2"))
    except ValueError:
        cooldown = 2.0
    if cooldown > 0:
        time.sleep(cooldown)


base.save_state = save_state_with_human_progress


def provider_summary() -> None:
    clouds = smart._configured_clouds()
    primaries = [p for p in ("groq", "gemini") if p in clouds]
    primary_text = " ↔ ".join(x.capitalize() for x in primaries) if primaries else "yok"
    reserve_text = "OpenRouter" if "openrouter" in clouds else "yok"

    print("SECOND BRAIN · HISTORY COMPILER", flush=True)
    print(f"  Ana cloud: {primary_text}", flush=True)
    print(f"  Cloud yedek: {reserve_text}", flush=True)
    print("  Son fallback: Ollama", flush=True)
    print(
        "  Hard timeout: Groq 45s · Gemini 60s · OpenRouter 25s · Ollama 300s",
        flush=True,
    )
    print("  Mod: primary round-robin + reserve fallback + JSON doğrulama + süre/ETA", flush=True)
    print("", flush=True)


if __name__ == "__main__":
    provider_summary()
    raise SystemExit(base.main())
