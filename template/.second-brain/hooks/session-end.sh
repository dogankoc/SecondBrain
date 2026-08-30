#!/bin/bash
set -u
source "$(dirname "$0")/lib.sh"
IN=$(mktemp "$STATE_DIR/sessionend.XXXX.json"); cat > "$IN"
python3 "$VAULT_DIR/.second-brain/scripts/flush.py" --hook-input "$IN" --cwd "$PWD" --reason sessionend >/dev/null 2>&1 || true
# Stop only the heartbeat matching this session; fallback removes stale active markers.
python3 - "$IN" "$STATE_DIR" "$VAULT_DIR/.second-brain/scripts" "$PWD" <<'PY' >/dev/null 2>&1 || true
import json,sys
from pathlib import Path
src=Path(sys.argv[1]); state=Path(sys.argv[2]); sys.path.insert(0,sys.argv[3]); cwd_hint=sys.argv[4]
from resolve_transcript import resolve
try:d=json.loads(src.read_text(encoding='utf-8'))
except Exception:d={}
sid=str(d.get('session_id') or d.get('sessionId') or '')
tp=str(d.get('transcript_path') or d.get('transcriptPath') or '')
if not tp:
    r=resolve(d if isinstance(d,dict) else {},cwd_hint)
    tp=str(r) if r else ''
for p in state.glob('active-*.json'):
    try:m=json.loads(p.read_text(encoding='utf-8'))
    except Exception:continue
    if (sid and str(m.get('session_id') or '')==sid) or (tp and str(m.get('transcript_path') or '')==tp):
        p.unlink(missing_ok=True)
PY
H=$(date +%H); H=$((10#$H)); if [ "$H" -ge 18 ]; then (python3 "$VAULT_DIR/.second-brain/scripts/compile.py" >/dev/null 2>&1 &) || true; fi
rm -f "$IN" "$STATE_DIR/session_start_time" "$STATE_DIR/prompt_count"
