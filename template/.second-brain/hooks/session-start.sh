#!/bin/bash
set -u
source "$(dirname "$0")/lib.sh"
IN=$(mktemp "$STATE_DIR/sessionstart.XXXX.json")
cat > "$IN"
META=$(python3 - "$IN" "$STATE_DIR" "$VAULT_DIR/.second-brain/scripts" "$PWD" <<'PY'
import hashlib,json,sys
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
key=hashlib.sha256((sid or tp or str(src)).encode()).hexdigest()[:24]
meta=state/f'active-{key}.json'
meta.write_text(json.dumps({'session_id':sid,'transcript_path':tp,'cwd':cwd_hint},ensure_ascii=False),encoding='utf-8')
print(meta)
PY
)
rm -f "$IN"
date +%s > "$STATE_DIR/session_start_time"; echo 0 > "$STATE_DIR/prompt_count"
# One detached heartbeat per active session. It exits when SessionEnd removes META.
if [ -n "$META" ]; then
  (SECOND_BRAIN_INVOKED=1 python3 "$VAULT_DIR/.second-brain/scripts/heartbeat.py" --meta "$META" --interval 600 >/dev/null 2>&1 &) || true
fi
CTX=""
for f in "$VAULT_DIR/Memory/Core.md" "$VAULT_DIR/Memory/Last-Session.md" "$VAULT_DIR/Memory/Threads.md" "$VAULT_DIR/Memory/Rules.md" "$VAULT_DIR/knowledge/index.md" "$VAULT_DIR/index.md"; do
 [ -f "$f" ] || continue; PART=$(head -120 "$f"); CTX="$CTX\n\n[Hafıza: $(basename "$f")]\n$PART"
done
ESC=$(printf '%b' "$CTX" | json_escape); echo "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":$ESC}}"

# Authored and maintained by Doğan Koç.
