#!/usr/bin/env python3
"""Restricted, read-only iSH command bridge over a private GitHub issue.
Python 3.9+. No Git pulls, no arbitrary code execution, no credential exfiltration.
"""
import getpass
import fcntl
import html.parser
import json
import os
import re
from pathlib import Path
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

OWNER = "minjae38987"
REPO = "-2"
ISSUE = 22
API = "https://api.github.com"
HOST = "https://chatbot-service.lumi.ing"
TOKEN_FILE = Path.home() / ".config" / "minjae-ish-bridge" / "github_token"
STATE_FILE = Path.home() / ".config" / "minjae-ish-bridge" / "last_comment_id"
PREFIX = "ISH_V2_REQUEST "
RESULT = "ISH_V2_RESULT "
V3_PREFIX = "ISH_V3_REQUEST "
V3_RESULT = "ISH_V3_RESULT "
DUAL_PREFIX = "HAIR_JOB_V1 "
DUAL_RESULT = "HAIR_JOB_RESULT_V1 "
DUAL_ALLOWED = frozenset(("PING","LUMI_PUBLIC","GIT_DIAG","PYTHON_ENV","LUMI_AUTH_MAP","LUMI_LOGIN_FLOW"))
SHARED_PREFIX = "MINJAE_JOB_V1 "
SHARED_RESULT = "MINJAE_RESULT_V1 "
SHARED_TASKS = frozenset(("HEALTH_CHECK", "LUMI_PUBLIC"))
ACTIONS = frozenset(("PING", "LUMI_PUBLIC", "LUMI_JS_META", "PYTHON_ENV", "GIT_DIAG", "LUMI_AUTH_MAP", "TASK_PLAN_V1", "CAPABILITIES", "LUMI_LOGIN_FLOW"))
PLAN_STEPS = frozenset(("ping", "python_env", "git_diag", "lumi_public", "lumi_js_meta", "lumi_auth_map", "lumi_public_js_terms"))
FIXED_JS_TERMS = frozenset(("login","password","auth","fetch(","localStorage","sessionStorage","Authorization","Bearer ","signInWith","axios","XMLHttpRequest","csrf","cookie"))

def api(method, path, token, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "minjae-ish-readonly-bridge-v2",
                 **({"Content-Type": "application/json"} if data is not None else {})})
    with urllib.request.urlopen(req, timeout=20) as res:
        raw = res.read(1500000)
        return json.loads(raw.decode("utf-8")) if raw else {}

def token_get():
    token = os.getenv("GH_TOKEN", "").strip() or os.getenv("GITHUB_TOKEN", "").strip()
    if not token and TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
    if not token:
        print("GitHub 토큰이 필요합니다. 입력 내용은 화면에 표시되지 않습니다.", flush=True)
        token = getpass.getpass("GitHub 토큰: ").strip()
        if not token:
            raise ValueError("토큰이 입력되지 않았습니다")
        info = api("GET", "/user", token)
        if info.get("login", "").lower() != OWNER.lower():
            raise ValueError("허용된 GitHub 계정이 아닙니다")
        TOKEN_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        TOKEN_FILE.write_text(token + "\n")
        os.chmod(TOKEN_FILE, 0o600)
    user = api("GET", "/user", token)
    if user.get("login", "").lower() != OWNER.lower():
        raise ValueError("GitHub 토큰의 계정이 올바르지 않습니다")
    return token

class PublicHTML(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_open = False
        self.title = []
        self.scripts = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title": self.title_open = True
        if tag == "script" and a.get("src"): self.scripts.append(a["src"][:200])
    def handle_endtag(self, tag):
        if tag == "title": self.title_open = False
    def handle_data(self, data):
        if self.title_open: self.title.append(data.strip())

def lumi_public():
    req = urllib.request.Request(HOST + "/", headers={"User-Agent":"minjae-ish-readonly-bridge-v2"})
    with urllib.request.urlopen(req, timeout=18) as res:
        status = res.status
        raw = res.read(1200000)
        content_type = res.headers.get("content-type","")[:70]
    parser = PublicHTML()
    parser.feed(raw.decode("utf-8", "replace"))
    return {"http_status":status, "content_type":content_type,
            "title":" ".join(parser.title)[:100],
            "script_paths":[x for x in parser.scripts if x.startswith("/assets/")][:5]}

def lumi_js_meta():
    info = lumi_public()
    local = info.get("script_paths",[])
    if not local:
        return {"app_script_found":False}
    path = local[0]
    # Only exact script discovered in the public site's own HTML.
    req = urllib.request.Request(HOST + path, headers={"User-Agent":"minjae-ish-readonly-bridge-v2"})
    with urllib.request.urlopen(req, timeout=25) as res:
        chunk=res.read(5500000)
    data=chunk.decode("utf-8", "replace")
    return {"app_script_found":True,"bytes_read":len(chunk),
            "login_token_count":data.lower().count("login"),
            "password_token_count":data.lower().count("password"),
            "auth_token_count":data.lower().count("auth"),
            "fetch_token_count":data.count("fetch(")}
            

def lumi_auth_map():
    """Static inspection of published frontend JS. Never send code snippets or secrets."""
    info = lumi_public()
    scripts = info.get("script_paths", [])
    if not scripts:
        return {"app_script_found":False}
    script_path = scripts[0]
    if not script_path.startswith("/assets/") or not script_path.endswith(".js"):
        return {"app_script_found":False,"reason":"non_js_asset"}
    req = urllib.request.Request(HOST + script_path,
                                 headers={"User-Agent":"minjae-ish-readonly-bridge-v2"})
    with urllib.request.urlopen(req, timeout=30) as res:
        raw = res.read(5500001)
    if len(raw) > 5500000:
        return {"app_script_found":True,"size_limit_exceeded":True}
    data = raw.decode("utf-8","replace")
    terms = ("fetch(", "axios", "XMLHttpRequest", "localStorage", "sessionStorage",
             "credentials:", "Authorization", "Bearer ", "supabase", "firebase",
             "signInWith", "password", "로그인", "비밀번호", "직원 로그인", "관리자",
             "서울대입구점")
    counts = {term:len(re.findall(re.escape(term),data,re.I)) for term in terms}
    # Only publish fixed-format counters, not embedded URLs, source text or credentials.
    return {"app_script_found":True,"js_bytes":len(raw),
            "authentication_hint_counts":counts,
            "login_method":"UNVERIFIED",
            "official_api_availability":"UNVERIFIED",
            "analysis_scope":"public_static_frontend_only"}


def lumi_login_flow():
    """Bounded public JS authentication-route inventory, not an authentication attempt."""
    info=lumi_public()
    paths=info.get("script_paths",[])
    if not paths or not paths[0].startswith("/assets/") or not paths[0].endswith(".js"):
        return {"status":"script_not_found"}
    req=urllib.request.Request(HOST+paths[0],headers={"User-Agent":"minjae-ish-readonly-bridge-v2"})
    with urllib.request.urlopen(req,timeout=30) as res:
        raw=res.read(5500001)
    if len(raw)>5500000: return {"status":"bundle_too_large"}
    source=raw.decode("utf-8","replace")
    # Search only public code for conventional authentication and API method names.
    identifiers=("signInWithPassword","signInWithEmailAndPassword","signInWithOAuth",
                 "signInAnonymously","onAuthStateChanged","getIdToken",
                 "createClient","createBrowserClient","getSession",
                 "signOut","setSession","getUser","onAuthStateChange",
                 "localStorage","sessionStorage","Authorization","Bearer ",
                 "fetch(","XMLHttpRequest","axios","firebase","supabase")
    counts={name:source.count(name) for name in identifiers if name in source}
    # Extract public absolute URL hostnames only; do not return paths, queries or token strings.
    hosts=set()
    for m in re.finditer(r'https?://[A-Za-z0-9][A-Za-z0-9.:-]{2,120}',source):
        try:
            host=urllib.parse.urlsplit(m.group()).hostname
            if host and re.fullmatch(r'[a-zA-Z0-9.-]{3,100}',host):
                hosts.add(host.lower())
        except ValueError:
            pass
    # Keep only a short fixed sample of host names; not app source or credentials.
    return {"bundle_bytes":len(raw),"login_identifier_counts":counts,
            "public_url_hostnames":sorted(hosts)[:25],
            "authenticated":False,"customer_data_read":False,
            "api_contract_verified":False}

def git_diag():
    folder = Path("/root/minjae-ai-hub")
    diag = {"repo_folder_exists": folder.exists(),
            "git_directory_exists": (folder / ".git").exists()}
    if not diag["git_directory_exists"]:
        return diag
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    tests = {
        "local_worktree": ["git", "-C", str(folder), "rev-parse", "--is-inside-work-tree"],
        "remote_read": ["git", "-C", str(folder), "ls-remote", "--heads", "origin"],
    }
    for name, args in tests.items():
        try:
            r = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=12, env=env, check=False)
            diag[name] = "OK" if r.returncode == 0 else "FAILED_EXIT_" + str(r.returncode)
        except (OSError, subprocess.TimeoutExpired) as e:
            diag[name] = type(e).__name__
    return diag


def lumi_public_js_terms(terms):
    """Count only preapproved literals in published first-party JS; never return snippets."""
    if not isinstance(terms,list) or not terms or len(terms)>10:
        raise ValueError("invalid_terms")
    if any(not isinstance(x,str) or x not in FIXED_JS_TERMS for x in terms):
        raise ValueError("unapproved_terms")
    info=lumi_public()
    paths=info.get("script_paths",[])
    if not paths or not paths[0].startswith("/assets/") or not paths[0].endswith(".js"):
        return {"status":"app_script_not_found"}
    req=urllib.request.Request(HOST+paths[0],headers={"User-Agent":"minjae-ish-readonly-bridge-v2"})
    with urllib.request.urlopen(req,timeout=30) as res:
        raw=res.read(5500001)
    if len(raw)>5500000: return {"status":"file_too_large"}
    source=raw.decode("utf-8","replace")
    return {"counts":{term:source.lower().count(term.lower()) for term in terms},"size_bytes":len(raw)}

def task_plan(request):
    """Allowlisted declarative execution plans, bounded and read-only."""
    steps=request.get("steps")
    if not isinstance(steps,list) or not 1<=len(steps)<=5:
        raise ValueError("plan_steps_required_1_to_5")
    results=[]
    for step in steps:
        if not isinstance(step,dict) or step.get("op") not in PLAN_STEPS:
            raise ValueError("unsupported_plan_step")
        op=step["op"]
        if op=="lumi_public_js_terms":
            if set(step)!={"op","terms"}: raise ValueError("unsupported_step_parameters")
            output=lumi_public_js_terms(step["terms"])
        else:
            if set(step)!={"op"}: raise ValueError("unsupported_step_parameters")
            output={
                "ping":lambda:{"bridge":"online","python":sys.version.split()[0],"github_actions_used":False},
                "python_env":lambda:{"python":sys.version.split()[0],"platform":sys.platform},
                "git_diag":git_diag,
                "lumi_public":lumi_public,
                "lumi_js_meta":lumi_js_meta,
                "lumi_auth_map":lumi_auth_map
            }[op]()
        results.append({"step":op,"result":output})
    return {"plan_version":1,"steps":results,"readonly":True}

def run_action(action, request=None):
    if action == "TASK_PLAN_V1": return task_plan(request or {})
    if action == "CAPABILITIES": return {"allowed_actions":sorted(ACTIONS),"plan_steps":sorted(PLAN_STEPS),"dual_runner_jobs":sorted(DUAL_ALLOWED),"arbitrary_shell":False,"github_actions_required":False}
    if action == "PING": return {"bridge":"online","python":sys.version.split()[0],"github_actions_used":False}
    if action == "PYTHON_ENV": return {"python":sys.version.split()[0],"platform":sys.platform}
    if action == "GIT_DIAG": return git_diag()
    if action == "LUMI_PUBLIC": return lumi_public()
    if action == "LUMI_JS_META": return lumi_js_meta()
    if action == "LUMI_AUTH_MAP": return lumi_auth_map()
    if action == "LUMI_LOGIN_FLOW": return lumi_login_flow()
    raise ValueError("허용되지 않는 명령")

def run_shared_job(request):
    """Versioned dual-runner protocol. iSH only accepts explicitly routed safe tasks."""
    if not isinstance(request, dict) or set(request) != {"request_id", "runner", "task"}:
        raise ValueError("invalid_job_fields")
    rid = request["request_id"]
    if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9._-]{4,80}", rid):
        raise ValueError("invalid_request_id")
    if request["runner"] != "ish" or request["task"] not in SHARED_TASKS:
        raise ValueError("unsupported_ish_task")
    if request["task"] == "HEALTH_CHECK":
        result = {"runtime": "ish", "python": sys.version.split()[0]}
    elif request["task"] == "LUMI_PUBLIC":
        state = lumi_public()
        result = {"http_status": int(state["http_status"])}
    return {"request_id": rid, "runner": "ish", "task": request["task"],
            "status": "OK" if request["task"] == "HEALTH_CHECK" or result.get("http_status") == 200 else "ERROR",
            "data": result}


def send_shared(token, payload):
    """Publish only the schema-validated, non-sensitive response."""
    allowed_fields = {"request_id", "runner", "task", "status", "data"}
    if not isinstance(payload, dict) or set(payload) != allowed_fields:
        raise ValueError("invalid_shared_result")
    message = SHARED_RESULT + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    api("POST", "/repos/{}/{}/issues/{}/comments".format(OWNER, REPO, ISSUE),
        token, {"body": message})


def comments(token, since_id=0):
    # Fixed issue, paginated to avoid missing new jobs once over 100 comments.
    base = "/repos/{}/{}/issues/{}/comments".format(OWNER,REPO,ISSUE)
    results=[]
    for page in range(1,16):
        batch=api("GET",base+"?per_page=100&page="+str(page),token)
        if not isinstance(batch,list): raise ValueError("invalid_issue_response")
        results.extend(x for x in batch if int(x.get("id",0))>since_id)
        if len(batch)<100: return results
    raise ValueError("issue_comment_page_limit")

def send(token, request_id, status, data, prefix=RESULT, action=None):
    payload = {"request_id":request_id,"status":status,"data":data}
    if action is not None:
        payload["action"] = action
    try:
        api("POST","/repos/{}/{}/issues/{}/comments".format(OWNER,REPO,ISSUE),token,
            {"body":prefix + json.dumps(payload,ensure_ascii=False,separators=(",",":"))})
    except urllib.error.HTTPError as exc:
        print("Issue #22 결과 전송 실패: HTTP",exc.code,flush=True)
        raise

def checkpoint_get():
    try: return int(STATE_FILE.read_text().strip())
    except (OSError, ValueError): return 0

def checkpoint_set(value):
    STATE_FILE.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    tmp=STATE_FILE.with_suffix(".tmp")
    tmp.write_text(str(value))
    tmp.replace(STATE_FILE)

def dual_job(token, body):
    """Fixed-schema iSH jobs; never accept arbitrary shell, URLs or credentials."""
    try:
        if len(body)>1000: raise ValueError("job_too_long")
        job=json.loads(body[len(DUAL_PREFIX):].strip())
        if not isinstance(job,dict) or set(job)!={"id","runner","task"}:
            raise ValueError("invalid_job_schema")
        jid=job["id"]
        if not isinstance(jid,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}",jid):
            raise ValueError("invalid_id")
        if job["runner"]!="ish" or job["task"] not in DUAL_ALLOWED:
            # An Actions-targeted message is never executed by iSH.
            return
        task=job["task"]
        try:
            data=run_action(task)
            status="OK"
        except Exception:
            data={}
            status="EXECUTION_ERROR"
        payload={"protocol":"HAIR_JOB_RESULT_V1","id":jid,"runner":"ish",
                 "task":task,"status":status,"details":data}
        api("POST","/repos/{}/{}/issues/{}/comments".format(OWNER,REPO,ISSUE),token,
            {"body":DUAL_RESULT+json.dumps(payload,ensure_ascii=False,separators=(",",":"))})
        print("Dual job:",jid,task,status,flush=True)
    except (ValueError,TypeError,KeyError,json.JSONDecodeError):
        print("Invalid dual job ignored",flush=True)

def poll(token):
    last=checkpoint_get()
    try:
        items=comments(token,last)
    except urllib.error.HTTPError as exc:
        print("Issue #22 댓글 조회 실패: HTTP", exc.code, flush=True)
        raise
    if not isinstance(items,list): raise ValueError("GitHub API result is not a list")
    for entry in sorted(items,key=lambda x:int(x.get("id",0))):
        ident=int(entry.get("id",0))
        if ident<=last: continue
        # Skip invalid messages and all messages from unexpected accounts.
        if entry.get("user",{}).get("login","").lower()!=OWNER.lower():
            checkpoint_set(ident);last=ident;continue
        body=entry.get("body","")
        if body.startswith(SHARED_PREFIX):
            job=None
            try:
                job=json.loads(body[len(SHARED_PREFIX):].strip())
                # Jobs for Actions are never executed or acknowledged by iSH.
                if not isinstance(job, dict) or job.get("runner")!="ish":
                    checkpoint_set(ident);last=ident;continue
                result=run_shared_job(job)
                send_shared(token,result)
                print("공통 작업 완료:", result["request_id"], result["task"], flush=True)
            except Exception as exc:
                rid=str(ident)
                if isinstance(job,dict) and isinstance(job.get("request_id"),str):
                    if re.fullmatch(r"[A-Za-z0-9._-]{4,80}",job["request_id"]):
                        rid=job["request_id"]
                fail={"request_id":rid,"runner":"ish","task":"UNSUPPORTED",
                      "status":"ERROR","data":{"type":type(exc).__name__}}
                send_shared(token,fail)
                print("공통 작업 오류:",ident,type(exc).__name__,flush=True)
            checkpoint_set(ident);last=ident;continue
        if body.startswith(DUAL_PREFIX):
            dual_job(token,body)
            checkpoint_set(ident);last=ident;continue
        is_v3 = body.startswith(V3_PREFIX)
        if not is_v3 and not body.startswith(PREFIX):
            checkpoint_set(ident);last=ident;continue
        prefix = V3_PREFIX if is_v3 else PREFIX
        out_prefix = V3_RESULT if is_v3 else RESULT
        try:
            request=json.loads(body[len(prefix):].strip())
            if not isinstance(request,dict): raise ValueError("invalid_request")
            action=request.get("action")
            expected={"request_id","action","steps"} if action=="TASK_PLAN_V1" else {"request_id","action"}
            if set(request)!=expected: raise ValueError("invalid_fields")
            if action not in ACTIONS:
                print("Unsupported request ignored:",ident,flush=True)
                checkpoint_set(ident);last=ident;continue
            rid=request.get("request_id")
            if not isinstance(rid,str) or not re.fullmatch(r"[A-Za-z0-9._-]{4,80}",rid):
                raise ValueError("invalid_request_id")
            try:
                data=run_action(action,request)
                status="OK"
            except urllib.error.HTTPError as exc:
                data={"http_status":exc.code}
                status="ERROR"
            except Exception as exc:
                data={"type":type(exc).__name__}
                status="ERROR"
            send(token,rid,status,data,prefix=out_prefix,action=action)
            print("Completed:",rid,action,status,flush=True)
        except (ValueError,TypeError,KeyError,json.JSONDecodeError):
            print("Malformed request ignored:",ident,flush=True)
        checkpoint_set(ident);last=ident
    return last

def main():
    lock_path=TOKEN_FILE.parent / "bridge.lock"
    lock_path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    lock=open(lock_path,"a+")
    try:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print("iSH bridge already active; duplicate disabled",flush=True)
        return
    print("iSH 제한형 원격 브리지 V3 | 이전 V2 작업도 지원",flush=True)
    token=token_get()
    print("GitHub 인증 확인. Ctrl-C 로 종료. iSH 앱을 전면에 유지하세요.",flush=True)
    while True:
        try: poll(token)
        except urllib.error.HTTPError as exc:
            print("GitHub API 오류 HTTP",exc.code,"(토큰 권한·저장소 접근 확인)",flush=True)
        except (urllib.error.URLError,TimeoutError,OSError) as exc:
            print("통신 오류:",type(exc).__name__,"(재시도)",flush=True)
        if "--once" in sys.argv: break
        time.sleep(20)

if __name__=="__main__":
    try: main()
    except KeyboardInterrupt: print("\n중지됨")
    except Exception as exc:
        print("실행 오류:",type(exc).__name__)
        sys.exit(1)
