#!/usr/bin/env python3
"""Restricted, read-only iSH command bridge over a private GitHub issue.
Python 3.9+. No Git pulls, no arbitrary code execution, no credential exfiltration.
"""
import getpass
import html.parser
import json
import os
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
ACTIONS = frozenset(("PING", "LUMI_PUBLIC", "LUMI_JS_META", "PYTHON_ENV", "GIT_DIAG"))

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

def run_action(action):
    if action == "PING": return {"bridge":"online","python":sys.version.split()[0],"github_actions_used":False}
    if action == "PYTHON_ENV": return {"python":sys.version.split()[0],"platform":sys.platform}
    if action == "GIT_DIAG": return git_diag()
    if action == "LUMI_PUBLIC": return lumi_public()
    if action == "LUMI_JS_META": return lumi_js_meta()
    raise ValueError("허용되지 않는 명령")

def comments(token):
    # The repository and issue IDs are fixed. Do not accept arbitrary URLs.
    path = "/repos/{}/{}/issues/{}/comments?per_page=100".format(OWNER,REPO,ISSUE)
    return api("GET",path,token)

def send(token, request_id, status, data):
    payload = {"request_id":request_id,"status":status,"data":data}
    api("POST","/repos/{}/{}/issues/{}/comments".format(OWNER,REPO,ISSUE),token,
        {"body":RESULT + json.dumps(payload,ensure_ascii=False,separators=(",",":"))})

def checkpoint_get():
    try: return int(STATE_FILE.read_text().strip())
    except (OSError, ValueError): return 0

def checkpoint_set(value):
    STATE_FILE.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    tmp=STATE_FILE.with_suffix(".tmp")
    tmp.write_text(str(value))
    tmp.replace(STATE_FILE)

def poll(token):
    last=checkpoint_get()
    items=comments(token)
    if not isinstance(items,list): raise ValueError("GitHub API result is not a list")
    for entry in sorted(items,key=lambda x:int(x.get("id",0))):
        ident=int(entry.get("id",0))
        if ident<=last: continue
        # Skip invalid messages and all messages from unexpected accounts.
        if entry.get("user",{}).get("login","").lower()!=OWNER.lower():
            checkpoint_set(ident);last=ident;continue
        body=entry.get("body","")
        if not body.startswith(PREFIX):
            checkpoint_set(ident);last=ident;continue
        try:
            request=json.loads(body[len(PREFIX):].strip())
            if set(request)!={"request_id","action"}: raise ValueError("요청 형식 오류")
            if request["action"] not in ACTIONS: raise ValueError("허용되지 않는 명령")
            if not isinstance(request["request_id"],str) or len(request["request_id"])>80:
                raise ValueError("request_id 오류")
            result=run_action(request["action"])
            send(token,request["request_id"],"OK",result)
            print("완료:",request["request_id"],request["action"],flush=True)
        except Exception as exc:
            # Never place exception details or secrets in the issue.
            try: send(token,str(ident),"ERROR",{"type":type(exc).__name__})
            except Exception: print("결과 전송 실패",flush=True);raise
            print("작업 실패:",ident,type(exc).__name__,flush=True)
        checkpoint_set(ident);last=ident
    return last

def main():
    print("iSH 제한형 원격 브리지 V2 | 허용된 읽기 전용 검사만 실행",flush=True)
    token=token_get()
    print("GitHub 인증 확인. Ctrl-C 로 종료. iSH 앱을 전면에 유지하세요.",flush=True)
    while True:
        try: poll(token)
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
