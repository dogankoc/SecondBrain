#!/bin/bash
set -euo pipefail
TARGET=""; NAME=""; LANGUAGE="en"; CHECKPOINT_MINUTES="10"; UPGRADE=0
usage(){ cat <<'TXT'
Usage: ./install.sh [options]
  --name "Display Name"
  --path "/path/to/vault"          default: ~/Documents/Second Brain
  --language en|tr|...
  --checkpoint-minutes N            default: 10
  --upgrade
TXT
}
while [ $# -gt 0 ]; do
 case "$1" in
  --name) NAME="$2";shift 2;;
  --path) TARGET="$2";shift 2;;
  --language) LANGUAGE="$2";shift 2;;
  --checkpoint-minutes) CHECKPOINT_MINUTES="$2";shift 2;;
  --upgrade|--merge) UPGRADE=1;shift;;
  -h|--help) usage;exit 0;;
  *) echo "Unknown option: $1" >&2;usage >&2;exit 2;;
 esac
done
ROOT="$(cd "$(dirname "$0")" && pwd)"; SRC="$ROOT/template"
TARGET="${TARGET:-$HOME/Documents/Second Brain}"; TARGET="${TARGET/#\~/$HOME}"
if [ -z "$NAME" ]; then NAME="$(git config --global user.name 2>/dev/null || true)"; [ -n "$NAME" ] || NAME="${USER:-User}"; fi
case "$CHECKPOINT_MINUTES" in ''|*[!0-9]*) echo "--checkpoint-minutes must be an integer" >&2;exit 2;; esac
[ "$CHECKPOINT_MINUTES" -ge 1 ] || { echo "--checkpoint-minutes must be >= 1" >&2; exit 2; }
mkdir -p "$TARGET"
if [ "$(find "$TARGET" -mindepth 1 -maxdepth 1 2>/dev/null | head -1)" ] && [ "$UPGRADE" != 1 ]; then
  echo "Target is not empty: $TARGET" >&2; echo "Use --upgrade to update an existing vault." >&2; exit 3
fi
if [ -d "$TARGET/🔮 850-Companion" ] && [ ! -e "$TARGET/Memory" ]; then mv "$TARGET/🔮 850-Companion" "$TARGET/Memory"; fi
if [ -f "$TARGET/Memory/Kurallar.md" ] && [ ! -e "$TARGET/Memory/Rules.md" ]; then mv "$TARGET/Memory/Kurallar.md" "$TARGET/Memory/Rules.md"; fi
if [ "$UPGRADE" = 1 ] && [ -d "$TARGET/.second-brain" ]; then rm -rf "$TARGET/.second-brain/hooks" "$TARGET/.second-brain/scripts" "$TARGET/.second-brain/skills"; fi
cp -R "$SRC"/. "$TARGET"/
python3 - "$TARGET" "$NAME" "$LANGUAGE" "$CHECKPOINT_MINUTES" <<'PY'
from pathlib import Path
import json,sys
v=Path(sys.argv[1]).expanduser().resolve();name=sys.argv[2];lang=sys.argv[3];minutes=int(sys.argv[4])
cfg=v/'.second-brain/config.json';d={}
if cfg.exists():
    try:
        x=json.loads(cfg.read_text(encoding='utf-8')); d=x if isinstance(x,dict) else {}
    except Exception: pass
d.update({'product':'Second Brain by Pijkard','user_name':name,'language':lang,'checkpoint_minutes':minutes})
cfg.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for p in v.rglob('*.md'):
    try:s=p.read_text(encoding='utf-8')
    except Exception:continue
    p.write_text(s.replace('{{USER_NAME}}',name).replace('{{LANGUAGE}}',lang),encoding='utf-8')
PY
chmod +x "$TARGET/.second-brain/hooks/"*.sh "$TARGET/.second-brain/scripts/"*.py 2>/dev/null || true
rm -rf "$TARGET/.claude" "$TARGET/.codex" "$TARGET/.opencode"; rm -f "$TARGET/opencode.json"
python3 - "$TARGET" "$CHECKPOINT_MINUTES" <<'PY'
from pathlib import Path
import json,sys,shlex
v=Path(sys.argv[1]).expanduser().resolve();minutes=int(sys.argv[2]);home=Path.home()
START='<!-- SECOND-BRAIN-BY-PIJKARD:START -->';END='<!-- SECOND-BRAIN-BY-PIJKARD:END -->'
body=(f"{START}\n# Second Brain by Pijkard — Global Memory\n\nCentral memory vault: `{v}`\n\n"
      "Continue to follow each project's local instructions. This memory layer does not replace project-local context.\n"
      "When relevant, read `Memory/`, `knowledge/index.md`, `index.md`, and `history/index.md` from the vault.\n"
      "Use the vault for durable cross-project memory, preferences, decisions, concepts, and historical lookup.\n"
      "Project-local files remain authoritative for project-specific facts. Never modify `raw/`. Never store secrets.\n"
      f"{END}\n")
def managed(path,block):
    path.parent.mkdir(parents=True,exist_ok=True);old=path.read_text(encoding='utf-8') if path.exists() else ''
    if START in old and END in old:
        a=old.index(START);b=old.index(END,a)+len(END)
        new=old[:a].rstrip()+('\n\n' if old[:a].strip() else '')+block.strip()+('\n\n'+old[b:].lstrip() if old[b:].strip() else '\n')
    else:new=old.rstrip()+('\n\n' if old.strip() else '')+block
    path.write_text(new,encoding='utf-8')
managed(home/'.claude/CLAUDE.md',body); managed(home/'.codex/AGENTS.md',body); managed(home/'.config/opencode/AGENTS.md',body)
def load(path):
    try:
        x=json.loads(path.read_text(encoding='utf-8')); return x if isinstance(x,dict) else {}
    except Exception:return {}
def strip(hooks):
    for event,groups in list(hooks.items()):
        if not isinstance(groups,list):continue
        kept=[]
        for g in groups:
            if not isinstance(g,dict):kept.append(g);continue
            es=g.get('hooks')
            if not isinstance(es,list):kept.append(g);continue
            es=[e for e in es if not(isinstance(e,dict) and 'SECOND_BRAIN_MANAGED=1' in str(e.get('command','')))]
            if es:ng=dict(g);ng['hooks']=es;kept.append(ng)
        if kept:hooks[event]=kept
        else:hooks.pop(event,None)
def wire(path,end_timeout):
    d=load(path);hooks=d.setdefault('hooks',{});strip(hooks)
    for event,stem,timeout in [('SessionStart','session-start',15),('UserPromptSubmit','prompt-counter',5),('PreCompact','pre-compact',10),('SessionEnd','session-end',end_timeout)]:
        script=v/'.second-brain/hooks'/f'{stem}.sh'
        cmd=f'SECOND_BRAIN_MANAGED=1 SECOND_BRAIN_CHECKPOINT_MINUTES={minutes} {shlex.quote(str(script))}'
        hooks.setdefault(event,[]).append({'hooks':[{'type':'command','command':cmd,'timeout':timeout,'statusMessage':f'Second Brain: {stem}'}]})
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
wire(home/'.claude/settings.json',10); wire(home/'.codex/hooks.json',3)
op=home/'.config/opencode/plugins/second-brain-by-pijkard.js'; op.parent.mkdir(parents=True,exist_ok=True)
op.write_text(f'''import fs from "node:fs"\nimport path from "node:path"\nimport {{ spawn }} from "node:child_process"\nconst VAULT={json.dumps(str(v))}\nconst CHECKPOINT_MS={minutes}*60*1000\nconst timers=new Map()\nfunction textOf(parts){{if(!Array.isArray(parts))return "";return parts.filter(p=>p&&p.type==="text"&&typeof p.text==="string").map(p=>p.text).join("\\n")}}\nfunction sid(e){{return e?.properties?.sessionID||e?.sessionID||e?.properties?.info?.id||e?.info?.id}}\nexport const SecondBrainByPijkard=async({{client}})=>{{if(process.env.SECOND_BRAIN_INVOKED==="1")return {{}};const script=path.join(VAULT,".second-brain","scripts","flush.py"),state=path.join(VAULT,".second-brain","scripts",".state");fs.mkdirSync(state,{{recursive:true}});async function checkpoint(id,reason){{if(!id||!fs.existsSync(script))return;try{{let r;try{{r=await client.session.messages({{path:{{id}}}})}}catch{{r=await client.session.messages({{sessionID:id}})}}const rows=r?.data||r||[],lines=[];for(const row of rows){{const info=row?.info||row,role=info?.role;if(role!=="user"&&role!=="assistant")continue;const content=textOf(row?.parts||info?.parts);if(content.trim())lines.push(JSON.stringify({{message:{{role,content}}}}))}}if(lines.length<2)return;const safe=String(id).replace(/[^a-zA-Z0-9_-]/g,"_");const transcript=path.join(state,`opencode-${{safe}}.jsonl`);fs.writeFileSync(transcript,lines.join("\\n")+"\\n","utf8");const child=spawn("python3",[script,"--transcript",transcript,"--reason",reason],{{cwd:VAULT,detached:true,stdio:"ignore",env:{{...process.env,SECOND_BRAIN_LLM:"opencode",SECOND_BRAIN_INVOKED:"1"}}}});child.unref()}}catch(e){{try{{fs.appendFileSync(path.join(state,"opencode-plugin.log"),`${{new Date().toISOString()}} ${{String(e)}}\\n`)}}catch{{}}}}}}function ensure(id){{if(!id||timers.has(id))return;const t=setInterval(()=>void checkpoint(id,"checkpoint"),CHECKPOINT_MS);t.unref?.();timers.set(id,t)}}function stop(id){{const t=timers.get(id);if(t)clearInterval(t);timers.delete(id)}}return{{event:async({{event}})=>{{const id=sid(event);if(id)ensure(id);if(event?.type==="session.compacted")void checkpoint(id,"precompact");if(event?.type==="session.idle"){{void checkpoint(id,"sessionend");stop(id)}}}}}}}}\nexport default SecondBrainByPijkard\n''',encoding='utf-8')
PY
cd "$TARGET"
if command -v git >/dev/null 2>&1; then [ -d .git ] || git init -q; git add -A; if ! git diff --cached --quiet; then GN="$(git config user.name 2>/dev/null||true)"; GM="$(git config user.email 2>/dev/null||true)"; [ -n "$GN" ] || GN="$NAME"; [ -n "$GM" ] || GM="second-brain@localhost"; git -c user.name="$GN" -c user.email="$GM" commit -q -m "Second Brain: install/update" || true; fi; fi
python3 "$TARGET/.second-brain/scripts/doctor.py" || true
echo; echo "INSTALLED/UPDATED: $TARGET"; echo "Use claude / codex / opencode normally inside your existing project directories."
