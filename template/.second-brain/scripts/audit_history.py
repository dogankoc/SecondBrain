#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import time
from collections import defaultdict
from pathlib import Path

import compile_history as base
from history_prefilter import prefilter_transcript

VAULT = base.VAULT
STATE_DIR = base.STATE_FILE.parent
USAGE_LOG = STATE_DIR / "history-provider-usage.jsonl"
REPORT_JSON = STATE_DIR / "history-audit-report.json"
REPORT_MD = STATE_DIR / "history-audit-report.md"
REPROCESS_TXT = STATE_DIR / "history-audit-reprocess.txt"

DURABLE_ROOTS = [
    VAULT / "entities",
    VAULT / "concepts",
    VAULT / "decisions",
    VAULT / "syntheses",
    VAULT / "🏰 300-Projects",
]
DURABLE_FILES = [
    VAULT / "Memory" / "Rules.md",
    VAULT / "Memory" / "Threads.md",
]


def load_usage() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    if not USAGE_LOG.exists():
        return out
    for line in USAGE_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        source = str(row.get("source", "")).strip()
        if source:
            out[source].append(row)
    return out


def durable_documents() -> list[tuple[Path, str]]:
    docs: list[tuple[Path, str]] = []
    for root in DURABLE_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            try:
                docs.append((path, path.read_text(encoding="utf-8", errors="replace")))
            except Exception:
                pass
    for path in DURABLE_FILES:
        if path.exists():
            try:
                docs.append((path, path.read_text(encoding="utf-8", errors="replace")))
            except Exception:
                pass
    return docs


def backlinks_for(rel: str, docs: list[tuple[Path, str]]) -> list[str]:
    token = f"[[{Path(rel).with_suffix('').as_posix()}|"
    hits: list[str] = []
    for path, text in docs:
        if token in text:
            hits.append(path.relative_to(VAULT).as_posix())
    return hits


def weak_doc(path_rel: str) -> list[str]:
    path = VAULT / path_rel
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ["durable-output-unreadable"]

    reasons: list[str] = []
    if len(text.strip()) < 180:
        reasons.append("durable-output-too-short")
    if "history_compiled: true" in text:
        if "## Summary" not in text:
            reasons.append("missing-summary-section")
        if "## Claims" not in text:
            reasons.append("missing-claims-section")
    return reasons


def audit() -> dict:
    sessions = base.discover_sessions()
    state = base.load_state()
    compiled = state.get("compiled", {}) if isinstance(state.get("compiled"), dict) else {}
    docs = durable_documents()
    usage = load_usage()

    rows: list[dict] = []
    counts = defaultdict(int)

    for session in sessions:
        rel = session.relative_to(VAULT).as_posix()
        text = session.read_text(encoding="utf-8", errors="replace")
        digest = base.digest_text(text)
        stored = compiled.get(rel)
        links = backlinks_for(rel, docs)
        filtered, stats = prefilter_transcript(text)
        events = usage.get(rel, [])
        providers = sorted({str(x.get("provider", "")) for x in events if x.get("provider")})
        fallback_count = sum(1 for x in events if x.get("fallbacks"))

        fail: list[str] = []
        review: list[str] = []

        if stored is None:
            fail.append("not-compiled")
        elif stored != digest:
            fail.append("source-hash-mismatch")

        if stored == digest and not links:
            # A session may legitimately contain no durable knowledge. Only flag
            # substantial transcripts for review rather than treating this as corruption.
            if stats.filtered_chars >= 6000:
                review.append("no-durable-backlink")

        for path_rel in links:
            fail.extend(weak_doc(path_rel))

        if events:
            if "ollama" in providers:
                review.append("used-ollama")
            if "codex" in providers:
                review.append("used-chatgpt-codex")
            if fallback_count >= max(2, len(events) // 2):
                review.append("many-provider-fallbacks")
        elif stored == digest:
            review.append("no-provider-telemetry-legacy")

        fail = sorted(set(fail))
        review = sorted(set(review))
        status = "FAIL" if fail else "REVIEW" if review else "PASS"
        counts[status] += 1

        rows.append({
            "source": rel,
            "status": status,
            "fail": fail,
            "review": review,
            "source_chars": len(text),
            "filtered_chars": stats.filtered_chars,
            "backlinks": links,
            "providers": providers,
            "provider_events": len(events),
            "fallback_events": fallback_count,
        })

    return {
        "generated_at": int(time.time()),
        "total": len(rows),
        "counts": dict(counts),
        "rows": rows,
    }


def write_report(report: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# History Audit Report",
        "",
        f"- Total: {report['total']}",
        f"- PASS: {report['counts'].get('PASS', 0)}",
        f"- REVIEW: {report['counts'].get('REVIEW', 0)}",
        f"- FAIL: {report['counts'].get('FAIL', 0)}",
        "",
        "## FAIL",
        "",
    ]
    failed = [r for r in report["rows"] if r["status"] == "FAIL"]
    if not failed:
        lines.append("- Yok")
    for row in failed:
        lines.append(f"- `{row['source']}` — {', '.join(row['fail'])}")

    lines += ["", "## REVIEW", ""]
    reviewed = [r for r in report["rows"] if r["status"] == "REVIEW"]
    if not reviewed:
        lines.append("- Yok")
    for row in reviewed:
        lines.append(f"- `{row['source']}` — {', '.join(row['review'])}")

    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    candidates = [r["source"] for r in report["rows"] if r["status"] == "FAIL"]
    REPROCESS_TXT.write_text("\n".join(candidates) + ("\n" if candidates else ""), encoding="utf-8")


def queue_reprocess(report: dict, include_review: bool) -> int:
    state = base.load_state()
    compiled = state.get("compiled", {}) if isinstance(state.get("compiled"), dict) else {}
    wanted = {
        r["source"]
        for r in report["rows"]
        if r["status"] == "FAIL" or (include_review and r["status"] == "REVIEW")
    }
    present = sorted(x for x in wanted if x in compiled)
    if not present:
        return 0

    backup = base.STATE_FILE.with_name(f"history-compile-state.backup-{int(time.time())}.json")
    shutil.copy2(base.STATE_FILE, backup)
    for rel in present:
        compiled.pop(rel, None)
    state["compiled"] = compiled
    state["audit_reprocess_queued"] = present
    state["audit_state_backup"] = backup.name
    base.save_state(state)
    return len(present)


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit compiled history quality and queue suspicious sessions for selective reprocessing.")
    ap.add_argument("--queue-reprocess", action="store_true", help="remove FAIL sessions from compiled state after backing it up")
    ap.add_argument("--include-review", action="store_true", help="with --queue-reprocess, also queue REVIEW sessions")
    args = ap.parse_args()

    report = audit()
    write_report(report)

    print("SECOND BRAIN · HISTORY AUDIT")
    print(f"  Total: {report['total']}")
    print(f"  PASS: {report['counts'].get('PASS', 0)}")
    print(f"  REVIEW: {report['counts'].get('REVIEW', 0)}")
    print(f"  FAIL: {report['counts'].get('FAIL', 0)}")
    print(f"  Rapor: {REPORT_MD}")

    if args.queue_reprocess:
        queued = queue_reprocess(report, args.include_review)
        print(f"  Reprocess kuyruğu: {queued} session")
        print("  Sonraki normal history compiler çalıştırması yalnız state'ten çıkarılan session'ları yeniden işler.")

    return 1 if report['counts'].get('FAIL', 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
