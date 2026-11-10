#!/usr/bin/env python3
"""Approve-on-issue, restricted single-source patch on an isolated branch.

No shell, local checkout, auto-merge, or writes to main. The caller must pin
main commit and Git blob SHA; only a short exact one-occurrence replacement
in a reviewed allowlist is permitted. The target SHA256 is independently
committed in the request. Read-back checks protect ambiguous API responses.
"""
import base64
import hashlib
import re
import urllib.error

REPO="/repos/minjae38987/-2"
SHA=re.compile(r"^[0-9a-f]{40}$")
DIGEST=re.compile(r"^[0-9a-f]{64}$")
RID=re.compile(r"^[A-Za-z0-9_-]{4,32}$")
FILES=frozenset((
    "scripts/dual_runner_protocol.mjs",
    "scripts/dual_runner_router.mjs",
    "scripts/dual_runner_coordinator.mjs",
))
ACTION="PATCH_SOURCE_V1"
MAX_SOURCE_BYTES=150000
MAX_EDIT_BYTES=1000

class PermissionDenied(Exception):
    def __init__(self,phase):
        self.phase=phase
        super().__init__("HTTP_403_"+phase)

def validate(job):
    keys={"request_id","action","base_sha","path","expected_blob_sha",
          "old_text","new_text","target_sha256"}
    if not isinstance(job,dict) or set(job)!=keys:
        raise ValueError("INVALID_FIELDS")
    if job["action"]!=ACTION: raise ValueError("INVALID_ACTION")
    if not isinstance(job["request_id"],str) or not RID.fullmatch(job["request_id"]):
        raise ValueError("INVALID_ID")
    if not isinstance(job["base_sha"],str) or not SHA.fullmatch(job["base_sha"]):
        raise ValueError("INVALID_BASE_SHA")
    if job["path"] not in FILES: raise ValueError("PATH_NOT_APPROVED")
    if not isinstance(job["expected_blob_sha"],str) or not SHA.fullmatch(job["expected_blob_sha"]):
        raise ValueError("INVALID_BLOB_SHA")
    if not isinstance(job["target_sha256"],str) or not DIGEST.fullmatch(job["target_sha256"]):
        raise ValueError("INVALID_TARGET_DIGEST")
    for key in ("old_text","new_text"):
        value=job[key]
        if not isinstance(value,str) or len(value.encode("utf-8"))>MAX_EDIT_BYTES:
            raise ValueError("INVALID_EDIT")
    if not job["old_text"] or job["old_text"]==job["new_text"]:
        raise ValueError("NOOP_OR_EMPTY_EDIT")
    return job

def decode_content(value):
    if not isinstance(value,dict) or not isinstance(value.get("content"),str):
        raise ValueError("INVALID_GITHUB_CONTENT")
    if value.get("type") not in (None,"file"):
        raise ValueError("NOT_FILE")
    raw=base64.b64decode(value["content"],validate=False)
    if len(raw)>MAX_SOURCE_BYTES:raise ValueError("SOURCE_TOO_LARGE")
    return raw.decode("utf-8")

def patch(original,old,new):
    if original.count(old)!=1:
        raise ValueError("OLD_TEXT_NOT_UNIQUE")
    changed=original.replace(old,new,1)
    if len(changed.encode("utf-8"))>MAX_SOURCE_BYTES:
        raise ValueError("SOURCE_TOO_LARGE")
    return changed.encode("utf-8")

def run(api,token,job):
    job=validate(job)
    rid=job["request_id"]
    branch="ish-code-"+rid
    target=job["path"]
    phase="START"
    def req(method,path,data=None):
        nonlocal phase
        if path.endswith("/git/ref/heads/main"):phase="READ_MAIN_REF"
        elif path.endswith("/git/refs") and method=="POST":phase="CREATE_REF"
        elif "/git/ref/heads/ish-code-" in path:phase="READ_REF"
        elif "/contents/" in path:phase="WRITE_CONTENT" if method=="PUT" else "READ_CONTENT"
        try:
            return api(method,path,token,data) if data is not None else api(method,path,token)
        except urllib.error.HTTPError as ex:
            if ex.code==403: raise PermissionDenied(phase) from None
            raise
    def error(code):
        return {"request_id":rid,"action":ACTION,"status":"ERROR","reason":code,"branch":branch}
    def success(code,sha):
        return {"request_id":rid,"action":ACTION,"status":"OK","reason":code,
                "branch":branch,"content_sha256":sha}
    # Pin original source independently to main, before any mutation.
    source=req("GET",REPO+"/contents/"+target+"?ref="+job["base_sha"])
    if source.get("sha")!=job["expected_blob_sha"]:
        return error("ORIGINAL_BLOB_MISMATCH")
    try: final=patch(decode_content(source),job["old_text"],job["new_text"])
    except ValueError as ex:return error(str(ex))
    digest=hashlib.sha256(final).hexdigest()
    if digest!=job["target_sha256"]:
        return error("TARGET_DIGEST_MISMATCH")
    head=req("GET",REPO+"/git/ref/heads/main")
    if not isinstance(head,dict) or (head.get("object") or {}).get("sha")!=job["base_sha"]:
        return error("BASE_SHA_MOVED")
    created=False
    try:
        ref=req("POST",REPO+"/git/refs",
                {"ref":"refs/heads/"+branch,"sha":job["base_sha"]})
        created=True
    except urllib.error.HTTPError as ex:
        if ex.code!=422:raise
        ref=req("GET",REPO+"/git/ref/heads/"+branch)
    branch_sha=(ref.get("object") or {}).get("sha") if isinstance(ref,dict) else None
    if not isinstance(branch_sha,str) or not SHA.fullmatch(branch_sha):
        return error("REF_UNVERIFIED")
    if created and branch_sha!=job["base_sha"]:
        return error("CREATED_REF_MISMATCH")
    # Read back the branch file before deciding whether another write is safe.
    stored=req("GET",REPO+"/contents/"+target+"?ref="+branch)
    try: stored_raw=decode_content(stored).encode("utf-8")
    except ValueError:return error("BRANCH_CONTENT_INVALID")
    if stored_raw==final:
        return success("ALREADY_COMMITTED",digest)
    # Existing ref must NEVER be overwritten, even if at the same main SHA.
    if not created:return error("EXISTING_BRANCH_CONFLICT")
    if branch_sha!=job["base_sha"] or stored.get("sha")!=job["expected_blob_sha"]:
        return error("BRANCH_BLOB_MISMATCH")
    second=req("GET",REPO+"/git/ref/heads/main")
    if (second.get("object") or {}).get("sha")!=job["base_sha"]:
        return error("BASE_SHA_MOVED")
    try:
        req("PUT",REPO+"/contents/"+target,{
            "message":"chore: approved iSH source patch "+rid,
            "branch":branch,
            "sha":job["expected_blob_sha"],
            "content":base64.b64encode(final).decode("ascii")})
    except urllib.error.HTTPError as ex:
        return error("WRITE_HTTP_"+str(ex.code))
    committed=req("GET",REPO+"/contents/"+target+"?ref="+branch)
    if hashlib.sha256(decode_content(committed).encode("utf-8")).hexdigest()!=digest:
        return error("READBACK_MISMATCH")
    return success("COMMIT_VERIFIED",digest)
