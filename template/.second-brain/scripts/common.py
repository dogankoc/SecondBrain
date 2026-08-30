from pathlib import Path
import datetime as dt, json, os, re, shutil, subprocess, tempfile, time
import urllib.error, urllib.parse, urllib.request

SCRIPT_DIR=Path(__file__).resolve().parent
VAULT=SCRIPT_DIR.parent.parent
STATE=SCRIPT_DIR/'.state'; STATE.mkdir(parents=True,exist_ok=True)
WIKI_DIRS=('sources','entities','concepts','decisions','syntheses')
CONFIG_FILE=VAULT/'.second-brain/config.json'
PROVIDER_STATE=STATE/'provider-cooldowns.json'

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
    default='groq,gemini,openrouter,ollama,claude,codex,opencode'
    return [x.strip().lower() for x in os.environ.get('SECOND_BRAIN_LLM_PRIORITY',default).split(',') if x.strip()]

def _run(cmd,prompt,timeout):
    env=os.environ.copy(); env['SECOND_BRAIN_INVOKED']='1'
    try:
        with tempfile.TemporaryDirectory(prefix='second-brain-') as td:
            cp=subprocess.run(cmd,input=prompt,text=True,capture_output=True,cwd=td,env=env,timeout=timeout)
        if cp.returncode: return None,f'exit-{cp.returncode}:{(cp.stderr or "")[-500:]}'
        return (cp.stdout or '').strip(),None
    except subprocess.TimeoutExpired:return None,'timeout'
    except Exception as e:return None,f'exec-error:{e}'

def _load_provider_state():
    try:
        d=json.loads(PROVIDER_STATE.read_text(encoding='utf-8')); return d if isinstance(d,dict) else {}
    except Exception:return {}
def _save_provider_state(d): atomic_write(PROVIDER_STATE,json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def _cooldown_remaining(provider):
    d=_load_provider_state(); until=float(d.get(provider,0) or 0); return max(0,int(until-time.time()))
def _set_cooldown(provider,seconds):
    d=_load_provider_state(); d[provider]=time.time()+max(1,int(seconds)); _save_provider_state(d)
def _retry_seconds(headers,default=600):
    try:return max(1,int(headers.get('Retry-After','') or default))
    except Exception:return default

def _safe_error(err):
    text=str(err or 'empty').replace('\n',' ').replace('\r',' ')
    for name in ('GROQ_API_KEY','GEMINI_API_KEY','OPENROUTER_API_KEY'):
        secret=os.environ.get(name,'')
        if secret:text=text.replace(secret,'[REDACTED]')
    text=re.sub(r'(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,}\]]+',r'\1[REDACTED]',text)
    return text[:700]

def _http_json(url,payload,headers=None,timeout=300):
    data=json.dumps(payload,ensure_ascii=False).encode('utf-8')
    req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json',**(headers or {})},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8')),None,None,r.headers
    except urllib.error.HTTPError as e:
        try: body=e.read().decode('utf-8','replace')[-1000:]
        except Exception: body=''
        return None,f'http-{e.code}:{body}',e.code,e.headers
    except Exception as e:return None,f'http-error:{e}',None,{}

def _openai_compatible(provider,url,key,model,prompt,timeout,json_mode=True,extra_headers=None):
    payload={'model':model,'messages':[{'role':'user','content':prompt}],'temperature':0.1,'stream':False}
    if json_mode: payload['response_format']={'type':'json_object'}
    headers={'Authorization':f'Bearer {key}',**(extra_headers or {})}
    data,err,status,hdrs=_http_json(url,payload,headers,timeout)
    if status==400 and json_mode and err and 'response_format' in err:
        payload.pop('response_format',None); data,err,status,hdrs=_http_json(url,payload,headers,timeout)
    if err:return None,err,status,hdrs
    try:return str(data['choices'][0]['message']['content']).strip(),None,status,hdrs
    except Exception as e:return None,f'bad-response:{e}',status,hdrs

def _run_groq(prompt,tier,timeout,json_mode):
    key=os.environ.get('GROQ_API_KEY','').strip()
    if not key:return None,'missing-key',None,{},''
    model=os.environ.get('SECOND_BRAIN_GROQ_FAST','qwen/qwen3.6-27b') if tier=='fast' else os.environ.get('SECOND_BRAIN_GROQ_SMART','qwen/qwen3.8-27b')
    out,err,status,hdrs=_openai_compatible('groq','https://api.groq.com/openai/v1/chat/completions',key,model,prompt,timeout,json_mode)
    return out,err,status,hdrs,model

def _run_openrouter(prompt,tier,timeout,json_mode):
    key=os.environ.get('OPENROUTER_API_KEY','').strip()
    if not key:return None,'missing-key',None,{},''
    model=os.environ.get('SECOND_BRAIN_OPENROUTER_FAST','openrouter/free') if tier=='fast' else os.environ.get('SECOND_BRAIN_OPENROUTER_SMART','openrouter/free')
    headers={'HTTP-Referer':os.environ.get('SECOND_BRAIN_OPENROUTER_REFERER','https://github.com/dogankoc/SecondBrain'),'X-Title':'Pijkard SecondBrain'}
    out,err,status,hdrs=_openai_compatible('openrouter','https://openrouter.ai/api/v1/chat/completions',key,model,prompt,timeout,json_mode,headers)
    return out,err,status,hdrs,model

def _run_gemini(prompt,tier,timeout,json_mode):
    key=os.environ.get('GEMINI_API_KEY','').strip()
    if not key:return None,'missing-key',None,{},''
    model=os.environ.get('SECOND_BRAIN_GEMINI_FAST','gemini-2.5-flash-lite') if tier=='fast' else os.environ.get('SECOND_BRAIN_GEMINI_SMART','gemini-2.5-flash')
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(model,safe='')}:generateContent?key={urllib.parse.quote(key,safe='')}"
    generation={'temperature':0.1}
    if json_mode:generation['responseMimeType']='application/json'
    payload={'contents':[{'role':'user','parts':[{'text':prompt}]}],'generationConfig':generation}
    data,err,status,hdrs=_http_json(url,payload,{},timeout)
    if err:return None,err,status,hdrs,model
    try:
        parts=data['candidates'][0]['content']['parts']; out=''.join(str(x.get('text','')) for x in parts).strip(); return out,None,status,hdrs,model
    except Exception as e:return None,f'bad-response:{e}',status,hdrs,model

def _run_ollama(prompt,tier,timeout,json_mode):
    base=os.environ.get('SECOND_BRAIN_OLLAMA_URL','http://127.0.0.1:11434').rstrip('/')
    model=os.environ.get('SECOND_BRAIN_OLLAMA_FAST','qwen2.5:7b-instruct-q4_K_M') if tier=='fast' else os.environ.get('SECOND_BRAIN_OLLAMA_SMART','qwen2.5:7b-instruct-q4_K_M')
    try: threads=int(os.environ.get('SECOND_BRAIN_OLLAMA_THREADS','2')); batch=int(os.environ.get('SECOND_BRAIN_OLLAMA_BATCH','16')); ctx=int(os.environ.get('SECOND_BRAIN_OLLAMA_CTX','8192'))
    except Exception: threads,batch,ctx=2,16,8192
    payload={'model':model,'prompt':prompt,'stream':False,'keep_alive':0,'options':{'temperature':0.1,'num_thread':threads,'num_batch':batch,'num_ctx':ctx}}
    if json_mode:payload['format']='json'
    data,err,status,hdrs=_http_json(base+'/api/generate',payload,{},timeout)
    if err:return None,err,status,hdrs,model
    try:out=str(data.get('response','')).strip()
    except Exception:out=''
    try: cooldown=float(os.environ.get('SECOND_BRAIN_OLLAMA_COOLDOWN','8'))
    except Exception: cooldown=8
    if cooldown>0:time.sleep(cooldown)
    return out,(None if out else 'empty'),status,hdrs,model

def run_model(prompt,tier='fast',timeout=300,provider='auto',json_mode=False):
    errors=[]
    for p in _provider_order(provider):
        remaining=_cooldown_remaining(p)
        if remaining>0:
            print(f'  LLM SKIP provider={p} reason=cooldown remaining={remaining}s',flush=True)
            errors.append(f'{p}:cooldown-{remaining}s'); continue
        model=''
        if p=='groq': out,err,status,hdrs,model=_run_groq(prompt,tier,timeout,json_mode)
        elif p=='gemini': out,err,status,hdrs,model=_run_gemini(prompt,tier,timeout,json_mode)
        elif p=='openrouter': out,err,status,hdrs,model=_run_openrouter(prompt,tier,timeout,json_mode)
        elif p=='ollama': out,err,status,hdrs,model=_run_ollama(prompt,tier,timeout,json_mode)
        elif p=='claude':
            exe=shutil.which('claude')
            if not exe: errors.append('claude-missing'); continue
            model=os.environ.get('SECOND_BRAIN_CLAUDE_FAST','haiku') if tier=='fast' else os.environ.get('SECOND_BRAIN_CLAUDE_SMART','sonnet')
            out,err=_run([exe,'-p','--model',model,'--output-format','text','--safe-mode','--tools',''],prompt,timeout); status=None; hdrs={}
        elif p=='codex':
            exe=shutil.which('codex')
            if not exe: errors.append('codex-missing'); continue
            cmd=[exe,'exec','--ephemeral','--skip-git-repo-check']; model=os.environ.get('SECOND_BRAIN_CODEX_FAST' if tier=='fast' else 'SECOND_BRAIN_CODEX_SMART','')
            if model:cmd += ['-m',model]
            cmd += ['-']; out,err=_run(cmd,prompt,timeout); status=None; hdrs={}
        elif p in ('opencode','opencode2'):
            exe=shutil.which('opencode') or shutil.which('opencode2')
            if not exe: errors.append('opencode-missing'); continue
            cmd=[exe,'run']; model=os.environ.get('SECOND_BRAIN_OPENCODE_FAST' if tier=='fast' else 'SECOND_BRAIN_OPENCODE_SMART','')
            if model:cmd += ['--model',model]
            cmd += [prompt]; out,err=_run(cmd,'',timeout); status=None; hdrs={}
        else: errors.append(f'unknown:{p}'); continue
        if not err and out:
            print(f'  LLM provider={p} model={model or "default"}',flush=True)
            return out,None
        safe=_safe_error(err)
        if status in (429,500,502,503,504):
            default=int(os.environ.get('SECOND_BRAIN_PROVIDER_COOLDOWN','600'))
            seconds=_retry_seconds(hdrs,default); _set_cooldown(p,seconds)
            print(f'  LLM FAIL provider={p} model={model or "default"} http={status or "n/a"} reason={safe} cooldown={seconds}s -> fallback',flush=True)
            errors.append(f'{p}:{safe};cooldown={seconds}s')
        else:
            print(f'  LLM FAIL provider={p} model={model or "default"} http={status or "n/a"} reason={safe} -> fallback',flush=True)
            errors.append(f'{p}:{safe}')
    return None,';'.join(errors) or 'no-provider'

run_claude=run_model
