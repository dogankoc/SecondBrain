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
    r"\s*\d{4}-\d{2}-\d{2}[T ][0-9:.+-]+.*|\s*[A-Za-z0-9+/]{140,}={0,2}\s*)$"
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
        return 0.0 if not self.original_chars else max(0.0, 100.0 * (1 - self.filtered_chars / self.original_chars))

def _compact_fences(text: str) -> tuple[str, int]:
    omitted = 0
    def repl(m: re.Match[str]) -> str:
        nonlocal omitted
        lang=(m.group(1) or "").strip(); body=m.group(2)
        if len(body) <= 650: return m.group(0)
        keep_head, keep_tail = 320, 120
        omitted += max(0, len(body)-keep_head-keep_tail)
        return f"```{lang or 'text'}\n{body[:keep_head].rstrip()}\n[... code/tool body omitted ...]\n{body[-keep_tail:].lstrip()}\n```"
    return FENCE_RE.sub(repl,text), omitted

def _compact_machine_lines(text: str) -> tuple[str,int]:
    out=[]; run=[]; omitted=0
    def flush():
        nonlocal omitted
        if not run: return
        if len(run)>=3:
            raw="\n".join(run); omitted += len(raw); out.append(f"[... {len(run)} machine/log lines omitted ...]")
        else: out.extend(run)
        run.clear()
    for line in text.splitlines():
        if len(line)>220 or MACHINE_LINE_RE.match(line): run.append(line)
        else: flush(); out.append(line)
    flush(); return "\n".join(out), omitted

def _paragraphs(body:str)->list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n",body) if p.strip()]

def _score(p:str)->int:
    low=p.lower(); score=sum(3 for w in SIGNAL_WORDS if w in low)
    if re.search(r"(?m)^\s*(?:[-*]|\d+[.)])\s+",p): score+=2
    if re.search(r"(?m)^#{1,6}\s+",p): score+=2
    if any(x in low for x in ("http://","https://","error","exception","failed","success","complete")): score+=1
    if len(p)<=500: score+=1
    return score

def _select(body:str, cap:int, always_edges:int=1)->str:
    paras=_paragraphs(body)
    if not paras: return body[:cap].rstrip()
    chosen=set(range(min(always_edges,len(paras))))
    chosen.update(range(max(0,len(paras)-always_edges),len(paras)))
    ranked=sorted(range(len(paras)), key=lambda i:(-_score(paras[i]),i))
    used=sum(len(paras[i]) for i in chosen)
    for i in ranked:
        if i in chosen: continue
        if _score(paras[i]) < 2: continue
        if used + len(paras[i]) > cap: continue
        chosen.add(i); used += len(paras[i])
        if used >= cap*.92: break
    out=[]; last=-2
    for i in sorted(chosen):
        p=paras[i]
        if i>last+1: out.append("[... low-signal content omitted ...]")
        out.append(p); last=i
    return "\n\n".join(out).strip()[:cap].rstrip()

def _trim_assistant(body:str, cap:int=2500)->str:
    # Even medium-sized assistant turns are compressed; this is where most history bulk lives.
    if len(body)<=900: return body.strip()
    return _select(body,cap,always_edges=1)

def _trim_user(body:str, cap:int=6000)->str:
    # User turns are stronger evidence of intent/preferences, so preserve more.
    if len(body)<=cap: return body.strip()
    head=body[:4300].rstrip(); tail=body[-1300:].lstrip()
    return f"{head}\n\n[... {max(0,len(body)-5600)} chars omitted from very long user turn ...]\n\n{tail}"

def _speaker(block:str)->str:
    first=block.splitlines()[0] if block.splitlines() else ""
    return first[4:].strip().lower() if first.startswith("### ") else ""

def _dedupe_adjacent(blocks:list[str])->list[str]:
    out=[]; last_norm=""
    for b in blocks:
        norm=re.sub(r"\s+"," ",b).strip().lower()
        if norm and norm==last_norm: continue
        out.append(b); last_norm=norm
    return out

def prefilter_transcript(text:str)->tuple[str,FilterStats]:
    parts=HEADING_RE.split(text); preamble=parts[0] if parts else text; turns=parts[1:] if len(parts)>1 else []
    kept=[preamble.rstrip()]; fenced=machine=0
    for block in turns:
        if not block.strip(): continue
        lines=block.splitlines(); heading=lines[0].strip() if lines else "### Unknown"; body="\n".join(lines[1:]).strip()
        body,n=_compact_fences(body); fenced+=n
        body,n=_compact_machine_lines(body); machine+=n
        body=_trim_assistant(body) if _speaker(block) in ASSISTANT_NAMES else _trim_user(body)
        if body.strip(): kept.append(f"{heading}\n\n{body.strip()}")
    kept=_dedupe_adjacent(kept)
    filtered="\n\n".join(x for x in kept if x.strip()).strip()+"\n"
    return filtered,FilterStats(len(text),len(filtered),len(turns),max(0,len(kept)-1),fenced,machine)
