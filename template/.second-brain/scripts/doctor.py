#!/usr/bin/env python3
import shutil,sys,json,os
from pathlib import Path
from common import VAULT,STATE
checks=[('Vault',VAULT.exists(),str(VAULT)),('Python',True,sys.version.split()[0])]
for cli in ('claude','codex','opencode'): checks.append((cli,bool(shutil.which(cli)),shutil.which(cli) or 'missing'))
for f in ['AGENTS.md','CLAUDE.md','Memory/Core.md','Memory/Last-Session.md','Memory/Threads.md','Memory/Rules.md','knowledge/index.md']:
    q=VAULT/f; checks.append((f,q.exists(),'ok' if q.exists() else 'missing'))
home=Path.home()
checks += [
 ('Claude global adapter',(home/'.claude/CLAUDE.md').exists(),str(home/'.claude/CLAUDE.md')),
 ('Codex global adapter',(home/'.codex/AGENTS.md').exists(),str(home/'.codex/AGENTS.md')),
 ('OpenCode global adapter',(home/'.config/opencode/AGENTS.md').exists(),str(home/'.config/opencode/AGENTS.md')),
]
print('# Second Brain by Pijkard — Doctor')
for n,ok,d in checks: print(('✅' if ok else '⚠️'),n,'—',d)
providers=[x for x in ('claude','codex','opencode') if shutil.which(x)]
print('LLM provider:',', '.join(providers) if providers else 'NONE — automatic summarization/compilation will not run')
h=STATE/'health.json'
if h.exists():
    try: print('Son health:',json.loads(h.read_text(encoding='utf-8')))
    except Exception: pass
