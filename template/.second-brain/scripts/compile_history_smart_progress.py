#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
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
        "codex": _env_timeout("SECOND_BRAIN_CODEX_TIMEOUT", 90),
        "ollama": _env_timeout("SECOND_BRAIN_OLLAMA_TIMEOUT", 300),
    }.get(provider, 60)


def _provider_label(provider: str) -> str:
    return {
        "groq": "Groq",
        "gemini": "Gemini",
        "openrouter": "OpenRouter",
        "codex": "ChatGPT/Codex",
        "ollama": "Ollama",
    }.get(provider, provider.capitalize())


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
    if "codex-missing" in text or "codex_missing" in text:
        return "CLI missing"
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


def _provider_order() -> list[str]:
    """Groq is the primary worker; free/plan-backed services are layered fallbacks."""
    configured = set(smart._configured_clouds())
    order: list[str] = []

    for provider in ("groq", "gemini", "openrouter"):
        if provider in configured:
            order.append(provider)

    if shutil.which("codex"):
        order.append("codex")

    order.append("ollama")
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

    order = [provider] if provider and provider != "auto" else _provider_order()

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
                f"{label}  ✓ {_provider_label(candidate)} · {_fmt_duration(elapsed)}{eta_text}{suffix}",
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

        failures.append(f"{_provider_label(candidate)}: {reason}")

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
    clouds = set(smart._configured_clouds())
    codex_ready = shutil.which("codex") is not None

    print("SECOND BRAIN · HISTORY COMPILER", flush=True)
    print(f"  Ana: {'Groq' if 'groq' in clouds else 'yok'}", flush=True)
    print(f"  Yedek 1: {'Gemini' if 'gemini' in clouds else 'yok'}", flush=True)
    print(f"  Yedek 2: {'OpenRouter' if 'openrouter' in clouds else 'yok'}", flush=True)
    print(f"  Yedek 3: {'ChatGPT/Codex CLI hazır' if codex_ready else 'ChatGPT/Codex CLI bulunamadı'}", flush=True)
    print("  Son fallback: Ollama", flush=True)
    print(
        "  Hard timeout: Groq 45s · Gemini 60s · OpenRouter 25s · ChatGPT/Codex 90s · Ollama 300s",
        flush=True,
    )
    print("  Mod: Groq-first + katmanlı fallback + JSON doğrulama + süre/ETA", flush=True)
    print("", flush=True)


if __name__ == "__main__":
    provider_summary()
    raise SystemExit(base.main())
