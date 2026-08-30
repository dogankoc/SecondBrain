#!/usr/bin/env python3
"""Periodic 10-minute checkpoint loop for Claude/Codex sessions."""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FLUSH = SCRIPT_DIR / 'flush.py'
sys.path.insert(0, str(SCRIPT_DIR))
from resolve_transcript import resolve


def load_meta(path: Path) -> dict:
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except Exception:
        return {}


def save_meta(path: Path, meta: dict) -> None:
    try:path.write_text(json.dumps(meta,ensure_ascii=False),encoding='utf-8')
    except Exception:pass


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--meta',required=True); ap.add_argument('--interval',type=int,default=600); args=ap.parse_args()
    meta_path=Path(args.meta); interval=max(60,args.interval)
    while meta_path.exists():
        time.sleep(interval)
        if not meta_path.exists(): break
        meta=load_meta(meta_path); transcript=str(meta.get('transcript_path') or '')
        if not transcript or not Path(transcript).exists():
            r=resolve({'session_id':meta.get('session_id',''),'cwd':meta.get('cwd','')},str(meta.get('cwd') or ''))
            if r:
                transcript=str(r); meta['transcript_path']=transcript; save_meta(meta_path,meta)
        if not transcript or not Path(transcript).exists(): continue
        env=os.environ.copy(); env['SECOND_BRAIN_INVOKED']='1'
        try:
            subprocess.run([sys.executable,str(FLUSH),'--transcript',transcript,'--reason','checkpoint'],cwd=str(SCRIPT_DIR.parent.parent),env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=300,check=False)
        except Exception:pass
    return 0

if __name__=='__main__': raise SystemExit(main())
