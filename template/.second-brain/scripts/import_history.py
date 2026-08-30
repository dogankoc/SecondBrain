#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Iterable

from common import user_name, language

SCRIPT_DIR = Path(__file__).resolve().parent
VAULT = SCRIPT_DIR.parent.parent


def safe_slug(value: str, fallback: str = "session") -> str:
    value = re.sub(r"[^\w. -]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"\s+", "-", value.strip())
    value = re.sub(r"-+", "-", value).strip("-._")
    return value[:100] or fallback


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_lines(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                yield obj


def text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"].strip()
        return ""
    if isinstance(content, list):
        out: list[str] = []
        for block in content:
            if isinstance(block, str):
                out.append(block)
            elif isinstance(block, dict):
                # Keep user-facing text only, not tool payloads/results.
                if block.get("type") in {"text", "input_text", "output_text"} and isinstance(block.get("text"), str):
                    out.append(block["text"])
        return "\n".join(x for x in out if x.strip()).strip()
    return ""


def iso_to_dt(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        value = value.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(value)
    except Exception:
        return None


def extract_claude(path: Path) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    turns: list[tuple[str, str]] = []
    meta: dict[str, Any] = {"provider": "claude", "session_id": path.stem}
    first_dt: dt.datetime | None = None
    last_dt: dt.datetime | None = None
    for r in json_lines(path):
        for key in ("cwd", "projectPath", "project_path"):
            if isinstance(r.get(key), str) and r[key]:
                meta.setdefault("cwd", r[key])
        sid = r.get("sessionId") or r.get("session_id")
        if isinstance(sid, str):
            meta["session_id"] = sid
        ts = iso_to_dt(r.get("timestamp") or r.get("created_at") or r.get("createdAt"))
        if ts:
            first_dt = min(first_dt, ts) if first_dt else ts
            last_dt = max(last_dt, ts) if last_dt else ts

        role = None
        content: Any = None
        if r.get("type") == "event_msg" and isinstance(r.get("payload"), dict):
            p = r["payload"]
            role = {"user_message": "user", "agent_message": "assistant"}.get(p.get("type"))
            content = p.get("message")
        elif isinstance(r.get("message"), dict):
            m = r["message"]
            role = m.get("role") or r.get("type")
            content = m.get("content")
        else:
            role = r.get("role") or r.get("type")
            content = r.get("content")

        if role in {"user", "assistant"}:
            text = text_from_content(content)
            if text:
                turns.append((role, text))
    if first_dt:
        meta["started"] = first_dt.isoformat()
    if last_dt:
        meta["ended"] = last_dt.isoformat()
    if "cwd" not in meta:
        # Claude project directory slug is still useful as a fallback label.
        meta["project_slug"] = path.parent.name
    return turns, meta


def extract_codex(path: Path) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    turns: list[tuple[str, str]] = []
    meta: dict[str, Any] = {"provider": "codex", "session_id": path.stem.replace("rollout-", "")}
    first_dt: dt.datetime | None = None
    last_dt: dt.datetime | None = None
    seen: set[tuple[str, str]] = set()

    def add(role: str | None, content: Any) -> None:
        if role not in {"user", "assistant"}:
            return
        text = text_from_content(content)
        if not text:
            return
        key = (role, text)
        if key in seen:
            return
        seen.add(key)
        turns.append(key)

    for r in json_lines(path):
        ts = iso_to_dt(r.get("timestamp") or r.get("created_at") or r.get("createdAt"))
        if ts:
            first_dt = min(first_dt, ts) if first_dt else ts
            last_dt = max(last_dt, ts) if last_dt else ts

        typ = r.get("type")
        p = r.get("payload") if isinstance(r.get("payload"), dict) else {}
        if typ == "session_meta":
            if isinstance(p.get("cwd"), str):
                meta["cwd"] = p["cwd"]
            if isinstance(p.get("id"), str):
                meta["session_id"] = p["id"]
            continue
        if typ == "event_msg":
            pt = p.get("type")
            if pt == "user_message":
                add("user", p.get("message"))
            elif pt == "agent_message":
                add("assistant", p.get("message"))
            continue
        if typ == "response_item":
            pt = p.get("type")
            if pt == "message":
                role = p.get("role")
                add(role, p.get("content"))
            continue
        # Generic fallback for format variations.
        if isinstance(r.get("message"), dict):
            m = r["message"]
            add(m.get("role"), m.get("content"))
        else:
            add(r.get("role"), r.get("content"))

    if first_dt:
        meta["started"] = first_dt.isoformat()
    if last_dt:
        meta["ended"] = last_dt.isoformat()
    return turns, meta


def session_date(meta: dict[str, Any], source: Path) -> str:
    for key in ("started", "ended"):
        d = iso_to_dt(meta.get(key))
        if d:
            return d.astimezone().date().isoformat()
    return dt.datetime.fromtimestamp(source.stat().st_mtime).date().isoformat()


def project_name(meta: dict[str, Any], source: Path) -> str:
    cwd = meta.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd).name or cwd
    slug = meta.get("project_slug")
    if isinstance(slug, str) and slug:
        return slug
    return source.parent.name


def write_session(provider: str, source: Path, turns: list[tuple[str, str]], meta: dict[str, Any], source_hash: str) -> Path:
    date = session_date(meta, source)
    proj = project_name(meta, source)
    sid = str(meta.get("session_id") or source.stem)
    out_dir = VAULT / "history" / provider / date[:4] / date[5:7]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{date}-{safe_slug(proj)}-{safe_slug(sid)[:48]}.md"

    if out.exists():
        old = out.read_text(encoding="utf-8", errors="replace")
        if f"source_sha256: {source_hash}" in old:
            return out

    lines = [
        "---",
        f"title: {provider.title()} — {proj} — {date}",
        "type: imported-session",
        f"provider: {provider}",
        f"session_id: {json.dumps(sid, ensure_ascii=False)}",
        f"project: {json.dumps(proj, ensure_ascii=False)}",
        f"date: {date}",
        f"source_sha256: {source_hash}",
        f"turn_count: {len(turns)}",
        "---",
        "",
        f"# {provider.title()} — {proj} — {date}",
        "",
        "## Metadata",
        "",
        f"- Session: `{sid}`",
        f"- Project: `{meta.get('cwd') or proj}`",
        f"- Source: `{source}`",
    ]
    if meta.get("started"):
        lines.append(f"- Started: `{meta['started']}`")
    if meta.get("ended"):
        lines.append(f"- Ended: `{meta['ended']}`")
    lines += ["", "## Conversation", ""]
    for role, text in turns:
        who = user_name() if role == "user" else provider.title()
        lines += [f"### {who}", "", text.strip(), ""]
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out


def copy_raw(provider: str, source: Path, base: Path) -> Path:
    try:
        rel = source.relative_to(base)
    except ValueError:
        rel = Path(source.name)
    target = VAULT / "raw" / "history" / provider / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or sha256(target) != sha256(source):
        shutil.copy2(source, target)
    return target


def discover(provider: str) -> list[tuple[Path, Path]]:
    home = Path.home()
    found: list[tuple[Path, Path]] = []
    if provider == "claude":
        base = home / ".claude" / "projects"
        if base.exists():
            for p in base.rglob("*.jsonl"):
                if p.is_file():
                    found.append((p, base))
    elif provider == "codex":
        for rootname in ("sessions", "archived_sessions"):
            base = home / ".codex" / rootname
            if base.exists():
                for p in base.rglob("*.jsonl"):
                    if p.is_file():
                        found.append((p, base))
    return sorted(found, key=lambda x: x[0].stat().st_mtime)


def rebuild_index(rows: list[dict[str, str]]) -> None:
    index = VAULT / "history" / "index.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: (r["date"], r["provider"], r["project"], r["session"]), reverse=True)
    lines = [
        "# Imported Conversation History",
        "",
        "Imported Claude Code and Codex sessions. Original JSONL files are preserved unchanged under `raw/history/`.",
        "",
        "| Date | Provider | Project | Session |",
        "|---|---|---|---|",
    ]
    for r in rows:
        rel = Path(r["md"]).relative_to(VAULT).with_suffix("")
        link = str(rel).replace(os.sep, "/")
        lines.append(f"| {r['date']} | {r['provider']} | {r['project']} | [[{link}|{r['session'][:12]}]] |")
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Import historical Claude Code and Codex transcripts into Second Brain.")
    ap.add_argument("--providers", default="claude,codex", help="comma-separated: claude,codex")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    providers = [p.strip().lower() for p in args.providers.split(",") if p.strip()]
    rows: list[dict[str, str]] = []
    totals = {"files": 0, "sessions": 0, "turns": 0, "skipped_empty": 0}

    for provider in providers:
        if provider not in {"claude", "codex"}:
            raise SystemExit(f"Unsupported provider: {provider}")
        files = discover(provider)
        print(f"{provider}: {len(files)} transcript bulundu")
        for source, base in files:
            totals["files"] += 1
            turns, meta = extract_claude(source) if provider == "claude" else extract_codex(source)
            if not turns:
                totals["skipped_empty"] += 1
                continue
            source_hash = sha256(source)
            date = session_date(meta, source)
            proj = project_name(meta, source)
            sid = str(meta.get("session_id") or source.stem)
            if args.dry_run:
                print(f"DRY {provider} {date} {proj} {sid} turns={len(turns)}")
                continue
            copy_raw(provider, source, base)
            md = write_session(provider, source, turns, meta, source_hash)
            rows.append({"date": date, "provider": provider, "project": proj, "session": sid, "md": str(md)})
            totals["sessions"] += 1
            totals["turns"] += len(turns)

    if not args.dry_run:
        # Include already imported pages in index too, so reruns remain complete/idempotent.
        existing: dict[str, dict[str, str]] = {r["md"]: r for r in rows}
        for md in (VAULT / "history").glob("*/*/*/*.md") if (VAULT / "history").exists() else []:
            if str(md) in existing:
                continue
            text = md.read_text(encoding="utf-8", errors="replace")
            def fm(key: str, default=""):
                m = re.search(rf"(?m)^{re.escape(key)}:\s*(.+?)\s*$", text)
                return m.group(1).strip().strip('"') if m else default
            existing[str(md)] = {
                "date": fm("date", md.parts[-3] + "-" + md.parts[-2] + "-01"),
                "provider": fm("provider", md.parts[-4] if len(md.parts) >= 4 else "unknown"),
                "project": fm("project", "unknown"),
                "session": fm("session_id", md.stem),
                "md": str(md),
            }
        rebuild_index(list(existing.values()))
        print(f"IMPORT_OK files={totals['files']} sessions={totals['sessions']} turns={totals['turns']} empty={totals['skipped_empty']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Authored and maintained by Doğan Koç.
