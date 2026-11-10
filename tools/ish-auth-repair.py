#!/usr/bin/env python3
"""Interactive credential repair on the iSH device. Never log a token.

Only install a token after validating the expected GitHub owner and the
pinned repository's main ref. Does not create branches or mutate GitHub.
"""
import getpass
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

API = "https://api.github.com"
OWNER = "minjae38987"
REPO = "-2"
TOKEN_FILE = Path.home()/".config"/"minjae-ish-bridge"/"github_token"
SHA = re.compile(r"^[0-9a-f]{40}$")

def get_json(path,token):
    request = urllib.request.Request(API+path,headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"minjae-ish-credential-verify"})
    with urllib.request.urlopen(request,timeout=20) as response:
        return json.loads(response.read(100000).decode("utf-8"))

def check(token, fetch=get_json):
    if not token or any(ch.isspace() for ch in token):
        return "TOKEN_FORMAT_INVALID"
    try:
        user=fetch("/user",token)
        if not isinstance(user,dict) or user.get("login","").lower()!=OWNER:
            return "ACCOUNT_MISMATCH"
        ref=fetch("/repos/"+OWNER+"/"+REPO+"/git/ref/heads/main",token)
        sha=(ref.get("object") or {}).get("sha") if isinstance(ref,dict) else None
        if not isinstance(sha,str) or not SHA.fullmatch(sha):
            return "MAIN_REF_INVALID"
    except urllib.error.HTTPError as error:
        if error.code in (401,403):
            return "TOKEN_OR_REPOSITORY_PERMISSION_"+str(error.code)
        return "GITHUB_HTTP_"+str(error.code)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError):
        return "NETWORK_OR_API_FAILURE"
    return "READ_VERIFIED"

def store(token,path=TOKEN_FILE):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    temp=path.with_name("github_token.new")
    fd=os.open(str(temp),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            f.write(token+"\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(temp),str(path))
        os.chmod(str(path),0o600)
    finally:
        if temp.exists():
            temp.unlink()

def main():
    print("iSH GitHub credentials: private interactive verification")
    print("Required repository: minjae38987/-2")
    print("Required fine-grained permissions: Contents READ/WRITE, Issues READ/WRITE")
    token=getpass.getpass("New GitHub token (input hidden): ").strip()
    status=check(token)
    print("Verification:",status)
    if status!="READ_VERIFIED":
        print("Old credentials remain unchanged.")
        return 1
    try:
        store(token)
    except (OSError,FileExistsError):
        print("Secure token save failed. Old credentials were not intentionally overwritten.")
        return 1
    print("Token replaced locally. Restart iSH worker to load the new token.")
    print("Note: reading main does not itself prove write permission.")
    return 0

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled; old token kept.")
        raise SystemExit(130)
