#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

import common
import compile_history as base
from history_prefilter import prefilter_transcript

# Free cloud providers first; Ollama is the final local fallback.
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


def _cloud_chunk_size(default: int = 12000) -> int:
    try:
        value = int(os.environ.get("SECOND_BRAIN_CLOUD_CHUNK_CHARS", str(default)))
    except ValueError:
        value = default
    return max(6000, min(value, base.CHUNK_CHARS))


def _retry_after_seconds(header_map: dict[str, str], body: str) -> float | None:
    value = header_map.get("Retry-After", "").strip()
    if value:
        try:
            return max(0.0, float(value))
        except ValueError:
            pass

    match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", body, flags=re.I)
    if match:
        try:
            return max(0.0, float(match.group(1)))
        except ValueError:
            pass
    return None


def _curl_groq(prompt: str, tier: str, timeout: int, json_mode: bool):
    """Call Groq with curl; on 429 return immediately so router can rotate provider.

    Retry-After is synthesized from the Groq response body when necessary, allowing
    common.run_model() to put only Groq on a short cooldown while Gemini/OpenRouter
    process the current chunk. The API key never appears in logs or process args.
    """
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        return None, "missing-key", None, {}, ""

    model = (
        os.environ.get("SECOND_BRAIN_GROQ_FAST", "qwen/qwen3.6-27b")
        if tier == "fast"
        else os.environ.get("SECOND_BRAIN_GROQ_SMART", "qwen/qwen3.8-27b")
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        with tempfile.TemporaryDirectory(prefix="second-brain-groq-") as td:
            td_path = Path(td)
            request_path = td_path / "request.json"
            response_path = td_path / "response.json"
            headers_path = td_path / "headers.txt"
            config_path = td_path / "curl.conf"

            request_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            config_path.write_text(
                "\n".join(
                    [
                        "silent",
                        "show-error",
                        'request = "POST"',
                        'url = "https://api.groq.com/openai/v1/chat/completions"',
                        f'header = "Authorization: Bearer {key}"',
                        'header = "Content-Type: application/json"',
                        'header = "Accept: application/json"',
                        f'data-binary = "@{request_path}"',
                        f'dump-header = "{headers_path}"',
                        f'output = "{response_path}"',
                        'write-out = "%{http_code}"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            os.chmod(config_path, 0o600)

            cp = subprocess.run(
                ["curl", "--config", str(config_path)],
                text=True,
                capture_output=True,
                timeout=timeout,
            )
            if cp.returncode != 0:
                return None, f"curl-exit-{cp.returncode}:{(cp.stderr or '')[-500:]}", None, {}, model

            try:
                status = int((cp.stdout or "").strip()[-3:])
            except Exception:
                status = None

            header_map: dict[str, str] = {}
            if headers_path.exists():
                for line in headers_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if ":" not in line:
                        continue
                    name, value = line.split(":", 1)
                    name = name.strip()
                    value = value.strip()
                    if name.lower() == "retry-after":
                        header_map["Retry-After"] = value
                    else:
                        header_map[name] = value

            body = response_path.read_text(encoding="utf-8", errors="replace") if response_path.exists() else ""

            if status == 429:
                retry_after = _retry_after_seconds(header_map, body)
                if retry_after is not None:
                    header_map["Retry-After"] = str(max(1, math.ceil(retry_after) + 1))

            if status is None or status < 200 or status >= 300:
                compact = " ".join(body.split())[-1000:]
                return None, f"http-{status}:{compact}", status, header_map, model

            try:
                data = json.loads(body)
                out = str(data["choices"][0]["message"]["content"]).strip()
            except Exception as exc:
                return None, f"bad-response:{exc}", status, header_map, model

            return out, (None if out else "empty"), status, header_map, model

    except subprocess.TimeoutExpired:
        return None, "timeout", None, {}, model
    except FileNotFoundError:
        return None, "curl-missing", None, {}, model
    except Exception as exc:
        return None, f"curl-error:{exc}", None, {}, model


# Groq Cloudflare rejects urllib on this workload; use curl for Groq only.
common._run_groq = _curl_groq


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
        cooldown = float(os.environ.get("SECOND_BRAIN_SESSION_COOLDOWN", "2"))
    except ValueError:
        cooldown = 2.0

    if cooldown > 0:
        print(f"  COOLING session complete — waiting {cooldown:g}s", flush=True)
        time.sleep(cooldown)


base.chunks = filtered_chunks
base.run_model = smart_run_model
base.save_state = save_state_with_progress


def provider_summary() -> None:
    priority = os.environ.get("SECOND_BRAIN_LLM_PRIORITY", "groq,gemini,openrouter,ollama")

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
    print("  groq_transport=curl", flush=True)
    print("  rate_limit_policy=rotate-provider-immediately", flush=True)

    cooldowns = []
    for provider in ("groq", "gemini", "openrouter", "ollama"):
        try:
            remaining = common._cooldown_remaining(provider)
        except Exception:
            remaining = 0
        if remaining > 0:
            cooldowns.append(f"{provider}:{remaining}s")
    print(f"  provider_cooldowns={','.join(cooldowns) if cooldowns else 'none'}", flush=True)
    print("  cloud keys are read from environment only; key values are never logged", flush=True)


if __name__ == "__main__":
    provider_summary()
    raise SystemExit(base.main())
