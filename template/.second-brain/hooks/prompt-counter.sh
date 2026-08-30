#!/bin/bash
set -u
source "$(dirname "$0")/lib.sh"
IN=$(mktemp "$STATE_DIR/prompt.XXXX.json"); cat > "$IN"
# Refresh transcript path in the matching active-session metadata. This handles clients
# that expose transcript_path only after SessionStart.
python3 - "$IN" "$STATE_DIR" "$VAULT_DIR/.second-brain/scripts" "$PWD" <<'PY' >/dev/null 2>&1 || true
import json,sys
from pathlib import Path
src=Path(sys.argv[1]); state=Path(sys.argv[2]); sys.path.insert(0,sys.argv[3]); cwd_hint=sys.argv[4]
from resolve_transcript import resolve
try:d=json.loads(src.read_text(encoding='utf-8'))
except Exception: raise SystemExit
sid=str(d.get('session_id') or d.get('sessionId') or '')
tp=str(d.get('transcript_path') or d.get('transcriptPath') or '')
if not tp:
    r=resolve(d if isinstance(d,dict) else {},cwd_hint)
    tp=str(r) if r else ''
if not tp: raise SystemExit
for p in state.glob('active-*.json'):
    try:m=json.loads(p.read_text(encoding='utf-8'))
    except Exception:continue
    if sid and str(m.get('session_id') or '')==sid:
        m['transcript_path']=tp; m['cwd']=cwd_hint; p.write_text(json.dumps(m,ensure_ascii=False),encoding='utf-8'); break
PY
rm -f "$IN"
C=0; [ -f "$STATE_DIR/prompt_count" ] && C=$(cat "$STATE_DIR/prompt_count" 2>/dev/null || echo 0); C=$((C+1)); echo "$C" > "$STATE_DIR/prompt_count"
if [ $((C%15)) -eq 0 ]; then M="[Hafıza] $C. mesaj. Kalıcı karar, tercih ve açık işleri dosyala."; E=$(printf '%s' "$M"|json_escape); echo "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$E}}"; fi
