#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass

ASSISTANT_NAMES = {"assistant", "claude", "codex", "opencode"}
SIGNAL_WORDS = (
    "decision", "decided", "recommend", "recommended", "result", "summary", "conclusion",
    "next step", "next action", "todo", "follow-up", "follow up", "open issue", "remaining",
    "important", "architecture", "design", "root cause", "fixed", "resolved", "status",
    "completed", "should", "must", "preference", "constraint", "risk", "trade-off", "tradeoff",
    "karar", "öner", "sonuç", "özet", "sonraki", "yapılacak", "takip", "açık", "kalan",
    "önemli", "mimari", "tasarım", "kök neden", "düzelt", "çözüld", "durum", "tamamland",
    "tercih", "kural", "gerekiyor", "gerekli", "risk", "sorun", "hata", "neden",
)
MACHINE_LINE_RE = re.compile(
    r"^(?:\s*[\[{].*[\]}],?\s*|\s*(?:INFO|DEBUG|TRACE|WARN|ERROR)\b.*|"
    r"\s*\d{4}-\d{2}-\d{2}[T ][0-9:.+-]+.*|\s*[A-Za-z0-9+/]{180,}={0,2}\s*)$"
)
FENCE_RE = re.compile(r"```([^\n]*)\n(.*?)```", re.S)
HEADING_RE = re.compile(r"(?m)(?=^### [^\n]{1,120}\s*$)")

@dataclass
class FilterStats:
    original_chars: int
    filtered_chars: int
    original_blocks: int
    kept_blocks: int
    omitted_fenced_chars: int = 0
    omitted_machine_chars: int = 0

    @property
    def reduction_percent(self) -> float:
        if not self.original_chars:
            return 0.0
        return max(0.0, 100.0 * (1 - self.filtered_chars / self.original_chars))

def _compact_fences(text: str) -> tuple[str, int]:
    omitted = 0
    def repl(match: re.Match[str]) -> str:
        nonlocal omitted
        lang = (match.group(1) or "").strip()
        body = match.group(2)
        if len(body) <= 1200:
            return match.group(0)
        omitted += len(body) - 900
        return (
            f"```{lang or 'text'}\n{body[:650].rstrip()}\n\n"
            f"[... {len(body) - 900} chars omitted by history prefilter ...]\n\n"
            f"{body[-250:].lstrip()}\n```"
        )
    return FENCE_RE.sub(repl, text), omitted

def _compact_machine_lines(text: str) -> tuple[str, int]:
    out: list[str] = []
    run: list[str] = []
    omitted = 0
    def flush() -> None:
        nonlocal omitted
        if not run:
            return
        if len(run) >= 4:
            raw = "\n".join(run)
            omitted += len(raw)
            out.append(f"[... {len(run)} machine/log lines omitted by history prefilter ...]")
        else:
            out.extend(run)
        run.clear()
    for line in text.splitlines():
        if len(line) > 260 or MACHINE_LINE_RE.match(line):
            run.append(line)
        else:
            flush(); out.append(line)
    flush()
    return "\n".join(out), omitted

def _paragraphs(body: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]

def _score_paragraph(p: str) -> int:
    low = p.lower()
    score = sum(2 for word in SIGNAL_WORDS if word in low)
    if re.search(r"(?m)^\s*(?:[-*]|\d+[.)])\s+", p): score += 1
    if re.search(r"(?m)^#{1,6}\s+", p): score += 1
    if len(p) < 900: score += 1
    return score

def _trim_assistant(body: str, cap: int = 6500) -> str:
    if len(body) <= cap:
        return body.strip()
    paras = _paragraphs(body)
    if not paras:
        return body[:cap].rstrip()
    chosen: set[int] = set(range(min(2, len(paras))))
    chosen.update(range(max(0, len(paras)-2), len(paras)))
    ranked = sorted(((-_score_paragraph(p), i) for i,p in enumerate(paras)), key=lambda x:(x[0],x[1]))
    for neg_score, i in ranked:
        if -neg_score <= 1: continue
        chosen.add(i)
        if sum(len(paras[j]) for j in chosen) >= cap * .9: break
    result: list[str] = []
    used = 0; last = -2
    for i in sorted(chosen):
        p = paras[i]
        if used + len(p) > cap and result: continue
        if i > last + 1: result.append("[... low-signal assistant content omitted ...]")
        result.append(p); used += len(p); last = i
    return "\n\n".join(result).strip()[:cap].rstrip()

def _trim_user(body: str, cap: int = 9000) -> str:
    if len(body) <= cap:
        return body.strip()
    return (
        f"{body[:6500].rstrip()}\n\n"
        f"[... {max(0, len(body)-8500)} chars omitted from very long user turn ...]\n\n"
        f"{body[-2000:].lstrip()}"
    )

def _speaker_from_block(block: str) -> str:
    first = block.splitlines()[0] if block.splitlines() else ""
    return first[4:].strip().lower() if first.startswith("### ") else ""

def prefilter_transcript(text: str) -> tuple[str, FilterStats]:
    parts = HEADING_RE.split(text)
    preamble = parts[0] if parts else text
    turn_blocks = parts[1:] if len(parts) > 1 else []
    kept: list[str] = [preamble.rstrip()]
    omitted_fenced = omitted_machine = 0
    for block in turn_blocks:
        if not block.strip(): continue
        lines = block.splitlines()
        heading = lines[0].strip() if lines else "### Unknown"
        body = "\n".join(lines[1:]).strip()
        body, n = _compact_fences(body); omitted_fenced += n
        body, n = _compact_machine_lines(body); omitted_machine += n
        body = _trim_assistant(body) if _speaker_from_block(block) in ASSISTANT_NAMES else _trim_user(body)
        if body.strip(): kept.append(f"{heading}\n\n{body.strip()}")
    filtered = "\n\n".join(x for x in kept if x.strip()).strip() + "\n"
    return filtered, FilterStats(
        original_chars=len(text), filtered_chars=len(filtered), original_blocks=len(turn_blocks),
        kept_blocks=max(0,len(kept)-1), omitted_fenced_chars=omitted_fenced,
        omitted_machine_chars=omitted_machine,
    )
