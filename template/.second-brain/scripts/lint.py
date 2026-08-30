#!/usr/bin/env python3
import re
from common import VAULT,WIKI_DIRS,now,atomic_write
LINK=re.compile(r'\[\[([^\]|#]+)')
def fm(t):
    if not t.startswith('---\n'):return {}
    e=t.find('\n---\n',4)
    if e<0:return {}
    d={}
    for l in t[4:e].splitlines():
        if ':' in l:k,v=l.split(':',1);d[k.strip()]=v.strip().strip('"')
    return d
def resolve(l):
    for p in (VAULT/l,(VAULT/l).with_suffix('.md')):
        if p.exists():return p
    h=list(VAULT.rglob(l.split('/')[-1]+'.md'));return h[0] if len(h)==1 else None
def main():
    files=[p for p in VAULT.rglob('*.md') if '.claude' not in p.parts and 'raw' not in p.parts]; incoming={p:0 for p in files};broken=[];schema=[];src=[];contr=[]
    for p in files:
        t=p.read_text(encoding='utf-8',errors='replace')
        for l in LINK.findall(t):
            r=resolve(l.strip())
            if r in incoming:incoming[r]+=1
            elif not r:broken.append((p,l))
        rel=p.relative_to(VAULT)
        if rel.parts and rel.parts[0] in WIKI_DIRS:
            d=fm(t)
            if not d:schema.append((p,'frontmatter yok'))
            elif not d.get('type'):schema.append((p,'type yok'))
            if rel.parts[0]!='sources' and '## Sources' not in t:src.append((p,'Sources bölümü yok'))
            if re.search(r'## Contradictions\s*\n(?:\s*\n)?-\s+\S',t):contr.append(p)
    exempt={'index.md','log.md','knowledge/index.md','knowledge/log.md'};orph=[p for p,n in incoming.items() if n==0 and p.relative_to(VAULT).as_posix() not in exempt and p.name not in ('CLAUDE.md','README.md')]
    lines=['# Wiki Lint Report','',f'Generated: {now().isoformat()}','',f'- Broken links: {len(broken)}',f'- Orphans: {len(orph)}',f'- Schema issues: {len(schema)}',f'- Source/provenance issues: {len(src)}',f'- Explicit contradictions: {len(contr)}','']
    for name,items in [('Broken Links',broken),('Orphans',orph),('Schema',schema),('Source Issues',src),('Contradictions',contr)]:
        lines+=['## '+name,'']; lines += ['- none'] if not items else [f'- `{(x[0] if isinstance(x,tuple) else x).relative_to(VAULT)}`'+(f' — {x[1]}' if isinstance(x,tuple) else '') for x in items[:200]];lines.append('')
    out=VAULT/'knowledge/lint-report.md';atomic_write(out,'\n'.join(lines)+'\n');print('\n'.join(lines[:10]));return 1 if broken or schema else 0
if __name__=='__main__':raise SystemExit(main())
