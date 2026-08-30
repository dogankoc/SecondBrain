from pathlib import Path
import datetime as dt, json, os, re, shutil, subprocess, tempfile, time
SCRIPT_DIR=Path(__file__).resolve().parent
VAULT=SCRIPT_DIR.parent.parent
STATE=SCRIPT_DIR/'.state'; STATE.mkdir(parents=True,exist_ok=True)
WIKI_DIRS=('sources','entities','concepts','decisions','syntheses')
CONFIG_FILE=VAULT/'.second-brain/config.json'
def load_config():
    try:
        d=json.loads(CONFIG_FILE.read_text(encoding='utf-8')); return d if isinstance(d,dict) else {}
    except Exception:return {}
def config_value(key,default=None):return load_config().get(key,default)
def user_name():return str(config_value('user_name',os.environ.get('USER','User')) or 'User')
def language():return str(config_value('language','en') or 'en').lower()
def checkpoint_minutes():
    try:return max(1,int(config_value('checkpoint_minutes',10)))
    except Exception:return 10
def now(): return dt.datetime.now().astimezone()
def atomic_write(p,text):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name('.'+p.name+f'.{os.getpid()}.tmp'); t.write_text(text,encoding='utf-8'); os.replace(t,p)
def health(component,error,warning=False):
    p=STATE/'health.json'; d={}
    try: d=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
    except Exception: d={}
    d.update(ts=int(time.time()),component=component,error=error,warning=bool(warning)); atomic_write(p,json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def append_log(msg):
    with (VAULT/'log.md').open('a',encoding='utf-8') as f: f.write(f"## [{now():%Y-%m-%d %H:%M}] {msg}\n\n")
def slugify(s):
    s=str(s).translate(str.maketrans('çğıöşüÇĞİÖŞÜ','cgiosuCGIOSU')).lower(); return re.sub(r'[^a-z0-9]+','-',s).strip('-')[:100] or 'untitled'
def _provider_order(requested='auto'):
    requested=(requested or 'auto').lower()
    if requested=='auto': requested=os.environ.get('SECOND_BRAIN_LLM','auto').lower()
    if requested!='auto': return [requested]
    return [x.strip().lower() for x in os.environ.get('SECOND_BRAIN_LLM_PRIORITY','claude,codex,opencode').split(',') if x.strip()]
def _run(cmd,prompt,timeout):
    env=os.environ.copy(); env['SECOND_BRAIN_INVOKED']='1'
    try:
        with tempfile.TemporaryDirectory(prefix='second-brain-pijkard-') as td:
            cp=subprocess.run(cmd,input=prompt,text=True,capture_output=True,cwd=td,env=env,timeout=timeout)
        if cp.returncode: return None,f'exit-{cp.returncode}:{(cp.stderr or "")[-500:]}'
        return (cp.stdout or '').strip(),None
    except subprocess.TimeoutExpired: return None,'timeout'
    except Exception as e: return None,f'exec-error:{e}'
def run_model(prompt,tier='fast',timeout=300,provider='auto'):
    errors=[]
    for p in _provider_order(provider):
        if p=='claude':
            exe=shutil.which('claude')
            if not exe: errors.append('claude-missing'); continue
            model=os.environ.get('SECOND_BRAIN_CLAUDE_FAST','haiku') if tier=='fast' else os.environ.get('SECOND_BRAIN_CLAUDE_SMART','sonnet')
            out,err=_run([exe,'-p','--model',model,'--output-format','text','--safe-mode','--tools',''],prompt,timeout)
        elif p=='codex':
            exe=shutil.which('codex')
            if not exe: errors.append('codex-missing'); continue
            cmd=[exe,'exec','--ephemeral','--skip-git-repo-check']
            model=os.environ.get('SECOND_BRAIN_CODEX_FAST' if tier=='fast' else 'SECOND_BRAIN_CODEX_SMART')
            if model: cmd += ['-m',model]
            cmd += ['-']
            out,err=_run(cmd,prompt,timeout)
        elif p in ('opencode','opencode2'):
            exe=shutil.which('opencode') or shutil.which('opencode2')
            if not exe: errors.append('opencode-missing'); continue
            cmd=[exe,'run']
            model=os.environ.get('SECOND_BRAIN_OPENCODE_FAST' if tier=='fast' else 'SECOND_BRAIN_OPENCODE_SMART')
            if model: cmd += ['--model',model]
            cmd += [prompt]
            out,err=_run(cmd,'',timeout)
        else:
            errors.append(f'unknown:{p}'); continue
        if not err and out: return out,None
        errors.append(f'{p}:{err or "empty"}')
    return None,';'.join(errors) or 'no-provider'
run_claude=run_model
