#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, time
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except Exception:
        return {}


def nested_values(obj: Any, keys: set[str]) -> list[str]:
    out=[]
    if isinstance(obj,dict):
        for k,v in obj.items():
            if k in keys and isinstance(v,(str,int,float)):
                out.append(str(v))
            out.extend(nested_values(v,keys))
    elif isinstance(obj,list):
        for v in obj:
            out.extend(nested_values(v,keys))
    return out


def claude_project_dir(cwd: str) -> Path | None:
    """Map /Users/name/project -> ~/.claude/projects/-Users-name-project."""
    if not cwd or not cwd.startswith('/'):
        return None
    key=cwd.rstrip('/').replace('/','-')
    return Path.home()/'.claude'/'projects'/key


def newest_jsonl(directory: Path, max_age: int=900) -> Path | None:
    if not directory.is_dir():
        return None
    now=time.time(); found=[]
    try:
        for p in directory.glob('*.jsonl'):
            try:
                st=p.stat()
            except OSError:
                continue
            if now-st.st_mtime <= max_age:
                found.append((st.st_mtime,p.resolve()))
    except Exception:
        return None
    if not found:
        return None
    found.sort(reverse=True,key=lambda x:x[0])
    return found[0][1]


def sample_matches(path: Path, session_id: str, cwd: str) -> tuple[int,int]:
    sid_hits=cwd_hits=0
    try:
        with path.open('r',encoding='utf-8',errors='replace') as f:
            lines=[]
            for _ in range(40):
                line=f.readline()
                if not line: break
                lines.append(line)
        text=''.join(lines)
        if session_id and session_id in text: sid_hits=1
        if cwd and cwd in text: cwd_hits=1
    except Exception:
        pass
    return sid_hits,cwd_hits


def resolve(data: dict[str,Any], cwd_hint: str='') -> Path | None:
    # 1) Explicit hook field if present.
    vals=nested_values(data,{'transcript_path','transcriptPath','transcript'})
    for raw in vals:
        p=Path(raw).expanduser()
        if p.is_file():
            return p.resolve()

    sids=nested_values(data,{'session_id','sessionId','sessionID'})
    session_id=next((x for x in sids if len(x)>=12), '')
    cwds=nested_values(data,{'cwd','working_directory','workingDirectory','project_dir','projectDir'})
    cwd=next((x for x in cwds if x.startswith('/')), '') or cwd_hint

    claude_root=Path.home()/'.claude'/'projects'

    # 2) Exact active project directory. This is Claude Code's actual on-disk mapping:
    #    /Users/alex/project -> ~/.claude/projects/-Users-alex-project/
    project_dir=claude_project_dir(cwd)
    if project_dir and project_dir.is_dir():
        if session_id:
            exact=project_dir/f'{session_id}.jsonl'
            if exact.is_file():
                return exact.resolve()
            for p in project_dir.glob(f'*{session_id}*.jsonl'):
                if p.is_file():
                    return p.resolve()
        latest=newest_jsonl(project_dir, max_age=1800)
        if latest:
            return latest

    # 3) Exact session ID anywhere under Claude/Codex session stores.
    roots=[claude_root, Path.home()/'.codex'/'sessions']
    for root in roots:
        if not root.exists() or not session_id:
            continue
        for pattern in (f'**/{session_id}.jsonl',f'**/*{session_id}*.jsonl'):
            try:
                for p in root.glob(pattern):
                    if p.is_file():
                        return p.resolve()
            except Exception:
                pass

    # 4) Content-match recent files.
    candidates=[]; now=time.time()
    for root in roots:
        if not root.exists():
            continue
        try:
            for p in root.rglob('*.jsonl'):
                try:
                    st=p.stat()
                except OSError:
                    continue
                age=now-st.st_mtime
                if age>1800:
                    continue
                sid_hit,cwd_hit=sample_matches(p,session_id,cwd)
                score=(sid_hit*100)+(cwd_hit*30)-min(age,1799)/120
                candidates.append((score,st.st_mtime,p.resolve(),sid_hit,cwd_hit))
        except Exception:
            pass
    if candidates:
        candidates.sort(reverse=True,key=lambda x:(x[0],x[1]))
        best=candidates[0]
        if best[3] or best[4]:
            return best[2]

    # 5) Last resort for Claude: the newest project transcript if it was modified
    #    in the last 2 minutes. This covers hook payloads with neither cwd nor transcript_path.
    fresh=[]
    if claude_root.is_dir():
        try:
            for p in claude_root.glob('*/*.jsonl'):
                try: st=p.stat()
                except OSError: continue
                if now-st.st_mtime <= 120:
                    fresh.append((st.st_mtime,p.resolve()))
        except Exception:
            pass
    if fresh:
        fresh.sort(reverse=True,key=lambda x:x[0])
        return fresh[0][1]
    return None


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--hook-input',required=True)
    ap.add_argument('--cwd',default='')
    args=ap.parse_args()
    data=load(Path(args.hook_input))
    p=resolve(data,args.cwd)
    if p:
        print(p)
        return 0
    return 1

if __name__=='__main__':
    raise SystemExit(main())
