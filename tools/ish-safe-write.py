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

class WriteAccessDenied(Exception):
    def __init__(self, phase):
        super().__init__("GITHUB_HTTP_403_AT_"+phase)
        self.phase=phase


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
    phase="INIT"
    def request(method,path,payload=None):
        nonlocal phase
        if path.endswith("/git/ref/heads/main"):
            phase="READ_MAIN_REF"
        elif "/git/ref/heads/ish-proof-" in path:
            phase="READ_PROOF_REF"
        elif path.endswith("/git/refs") and method=="POST":
            phase="CREATE_PROOF_REF"
        elif "/contents/" in path:
            phase=("WRITE_PROOF_CONTENT" if method=="PUT" else "READ_PROOF_CONTENT")
        try:
            return api(method,path,token,payload) if payload is not None else api(method,path,token)
        except urllib.error.HTTPError as e:
            if e.code==403:
                raise WriteAccessDenied(phase) from None
            raise
    branch="ish-proof-"+rid
    target="automation/ish-write-proofs/"+rid+".json"
    data=payload(rid,sha)
    digest=hashlib.sha256(data).hexdigest()
    def fail(reason):
        return {"request_id":rid,"action":ALLOWED_ACTION,
                "status":"ERROR","reason":reason,
                "branch":branch,"content_sha256":digest}
    # Check the pinned main commit before creating any ref.
    # Do NOT GET a nonexistent ref first: some GitHub permissions respond
    # with 403 instead of 404 for that lookup.
    head=request("GET",REPO+"/git/ref/heads/main")
    current=(head.get("object") or {}).get("sha") if isinstance(head,dict) else None
    existing=None
    created=False
    if current == sha:
        try:
            created_ref=request("POST",REPO+"/git/refs",
                {"ref":"refs/heads/"+branch,"sha":sha})
            created=True
            existing=created_ref
        except urllib.error.HTTPError as e:
            if e.code!=422: raise
            # The ref already exists (or a validation rule failed). A
            # follow-up GET must prove its exact identity, never trust 422.
            existing=request("GET",REPO+"/git/ref/heads/"+branch)
    else:
        # An older, already-completed request may be replayed after main
        # changes. Read-only verification is allowed; a new write is not.
        try:
            existing=request("GET",REPO+"/git/ref/heads/"+branch)
        except urllib.error.HTTPError as e:
            if e.code==404:
                return fail("BASE_SHA_MISMATCH")
            raise
    ref_sha=(existing.get("object") or {}).get("sha") if isinstance(existing,dict) else None
    if not isinstance(ref_sha,str) or not SHA.fullmatch(ref_sha):
        return fail("BRANCH_UNVERIFIED")
    if created and ref_sha!=sha:
        return fail("CREATED_BRANCH_SHA_MISMATCH")
    path=REPO+"/contents/"+target+"?ref="+branch
    previous=None
    try:
        previous=request("GET",path)
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
    # Never modify an already existing branch, even when its HEAD
    # matches the requested commit and the proof file is absent.
    if not created:
        return fail("EXISTING_BRANCH_WITHOUT_PROOF")
    # Detect a main branch update between the first read and the PUT.
    head=request("GET",REPO+"/git/ref/heads/main")
    if not isinstance(head,dict) or (head.get("object") or {}).get("sha")!=sha:
        return fail("BASE_SHA_MISMATCH")
    try:
        request("PUT",REPO+"/contents/"+target,{
            "message":"chore: iSH fixed proof "+rid,
            "content":base64.b64encode(data).decode("ascii"),
            "branch":branch})
    except urllib.error.HTTPError as e:
        # A timed-out or conflicted write is not reported as success.
        return fail("WRITE_FAILED_HTTP_"+str(e.code))
    # Verify content by direct read, not by assuming PUT success.
    committed=request("GET",path)
    try:
        stored=base64.b64decode(committed["content"])
    except (ValueError,TypeError,KeyError):
        return fail("READBACK_INVALID")
    if stored!=data: return fail("READBACK_MISMATCH")
    return {"request_id":rid,"action":ALLOWED_ACTION,"status":"OK",
            "reason":"COMMIT_VERIFIED","branch":branch,
            "content_sha256":digest}
