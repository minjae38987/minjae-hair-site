#!/usr/bin/env python3
"""V1 restricted iSH commit proof. No arbitrary file writes or code execution.

Owner-approved request pins main SHA; the only writable file is a generated
non-sensitive proof under a unique branch. Never change main or merge a PR.
"""
import base64
import hashlib
import json
import re
import urllib.error

REPO="/repos/minjae38987/-2"
ID=re.compile(r"^[a-zA-Z0-9_-]{4,32}$")
SHA=re.compile(r"^[a-f0-9]{40}$")
ALLOWED_ACTION="PROOF_COMMIT"

def validate(req):
    if not isinstance(req,dict) or set(req)!={"request_id","base_sha","action"}:
        raise ValueError("INVALID_SCHEMA")
    rid,sha=req.get("request_id"),req.get("base_sha")
    if not isinstance(rid,str) or not ID.fullmatch(rid):
        raise ValueError("INVALID_ID")
    if not isinstance(sha,str) or not SHA.fullmatch(sha):
        raise ValueError("INVALID_SHA")
    if req.get("action") != ALLOWED_ACTION:
        raise ValueError("UNAPPROVED_ACTION")
    return rid,sha

def payload(rid, sha):
    # Fixed trusted content. Never incorporate user code, shell or GitHub token.
    return (json.dumps({"schema":"ISH_SAFE_WRITE_PROOF_V1",
                        "request_id":rid,"approved_base_sha":sha},
                       sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")

def execute(api,token,req):
    rid,sha=validate(req)
    branch="ish-proof-"+rid
    target="automation/ish-write-proofs/"+rid+".json"
    data=payload(rid,sha)
    digest=hashlib.sha256(data).hexdigest()
    def fail(reason):
        return {"request_id":rid,"action":ALLOWED_ACTION,
                "status":"ERROR","reason":reason,
                "branch":branch,"content_sha256":digest}
    head=api("GET",REPO+"/git/ref/heads/main",token)
    if not isinstance(head,dict) or (head.get("object") or {}).get("sha")!=sha:
        return fail("BASE_SHA_MISMATCH")
    # Probe existing branch first. A replay must not modify an existing
    # branch whose head no longer matches its expected starting point.
    existing=None
    try:
        existing=api("GET",REPO+"/git/ref/heads/"+branch,token)
    except urllib.error.HTTPError as e:
        if e.code!=404: raise
    if existing is None:
        try:
            api("POST",REPO+"/git/refs",token,{"ref":"refs/heads/"+branch,"sha":sha})
        except urllib.error.HTTPError as e:
            if e.code!=422: raise
            # Race with another request. Refetch; never assume ownership.
        existing=api("GET",REPO+"/git/ref/heads/"+branch,token)
    if not isinstance(existing,dict) or not SHA.fullmatch((existing.get("object") or {}).get("sha","")):
        return fail("BRANCH_UNVERIFIED")
    path=REPO+"/contents/"+target+"?ref="+branch
    previous=None
    try:
        previous=api("GET",path,token)
    except urllib.error.HTTPError as e:
        if e.code!=404: raise
    if previous is not None:
        try:
            existing_bytes=base64.b64decode(previous["content"],validate=False)
        except (ValueError,TypeError,KeyError):
            return fail("EXISTING_PROOF_INVALID")
        if existing_bytes!=data:
            return fail("EXISTING_PROOF_CONFLICT")
        return {"request_id":rid,"action":ALLOWED_ACTION,"status":"OK",
                "reason":"ALREADY_COMMITTED","branch":branch,
                "content_sha256":digest}
    if existing["object"]["sha"]!=sha:
        return fail("BRANCH_MOVED_BEFORE_WRITE")
    try:
        api("PUT",REPO+"/contents/"+target,token,{
            "message":"chore: iSH fixed proof "+rid,
            "content":base64.b64encode(data).decode("ascii"),
            "branch":branch})
    except urllib.error.HTTPError as e:
        # A timed-out or conflicted write is not reported as success.
        return fail("WRITE_FAILED_HTTP_"+str(e.code))
    # Verify content by direct read, not by assuming PUT success.
    committed=api("GET",path,token)
    try:
        stored=base64.b64decode(committed["content"])
    except (ValueError,TypeError,KeyError):
        return fail("READBACK_INVALID")
    if stored!=data: return fail("READBACK_MISMATCH")
    return {"request_id":rid,"action":ALLOWED_ACTION,"status":"OK",
            "reason":"COMMIT_VERIFIED","branch":branch,
            "content_sha256":digest}
