#!/usr/bin/env python3
"""Restricted atomic multi-file patch for the existing iSH GitHub bridge.

An owner-authorized request pins main and every original blob. No arbitrary
paths, shell, merge or main write. Git objects are prepared before one ref move.
"""
import base64
import hashlib
import re
import urllib.error

REPO = '/repos/minjae38987/-2'
ACTION = 'PATCH_SOURCE_BATCH_V1'
SHA = re.compile(r'^[0-9a-f]{40}$')
DIGEST = re.compile(r'^[0-9a-f]{64}$')
RID = re.compile(r'^[A-Za-z0-9_-]{4,32}$')
FILES = frozenset((
    'scripts/dual_runner_protocol.mjs',
    'scripts/dual_runner_router.mjs',
    'scripts/dual_runner_coordinator.mjs',
    'scripts/dual_runner_actions.mjs',
    'scripts/code_verify_actions.mjs',
    'tests/dual_runner_protocol.test.mjs',
    'tests/dual_runner_router.test.mjs',
    'tests/dual_runner_coordinator.test.mjs',
))
MAX_SOURCE_BYTES = 150000
MAX_EDIT_BYTES = 1000
MAX_FILES = 5

class PermissionDenied(Exception):
    def __init__(self, phase):
        self.phase = phase
        super().__init__('HTTP_403_' + phase)

def validate(job):
    if not isinstance(job, dict) or set(job) != {'request_id', 'action', 'base_sha', 'edits'}:
        raise ValueError('INVALID_FIELDS')
    if job['action'] != ACTION:
        raise ValueError('INVALID_ACTION')
    if not isinstance(job['request_id'], str) or not RID.fullmatch(job['request_id']):
        raise ValueError('INVALID_ID')
    if not isinstance(job['base_sha'], str) or not SHA.fullmatch(job['base_sha']):
        raise ValueError('INVALID_BASE_SHA')
    edits = job['edits']
    if not isinstance(edits, list) or not 2 <= len(edits) <= MAX_FILES:
        raise ValueError('INVALID_EDIT_COUNT')
    seen = set()
    for entry in edits:
        if not isinstance(entry, dict) or set(entry) != {'path', 'expected_blob_sha', 'old_text', 'new_text', 'target_sha256'}:
            raise ValueError('INVALID_EDIT_FIELDS')
        path = entry['path']
        if not isinstance(path, str) or path not in FILES or path in seen:
            raise ValueError('PATH_NOT_APPROVED_OR_DUPLICATE')
        seen.add(path)
        if not isinstance(entry['expected_blob_sha'], str) or not SHA.fullmatch(entry['expected_blob_sha']):
            raise ValueError('INVALID_BLOB_SHA')
        if not isinstance(entry['target_sha256'], str) or not DIGEST.fullmatch(entry['target_sha256']):
            raise ValueError('INVALID_TARGET_DIGEST')
        for key in ('old_text', 'new_text'):
            value = entry[key]
            if not isinstance(value, str) or len(value.encode('utf-8')) > MAX_EDIT_BYTES:
                raise ValueError('INVALID_EDIT')
        if not entry['old_text'] or entry['old_text'] == entry['new_text']:
            raise ValueError('NOOP_OR_EMPTY_EDIT')
    return job

def decode_file(item):
    if not isinstance(item, dict) or item.get('type') != 'file' or not isinstance(item.get('content'), str):
        raise ValueError('INVALID_GITHUB_CONTENT')
    raw = base64.b64decode(item['content'], validate=True)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError('SOURCE_TOO_LARGE')
    return raw.decode('utf-8')

def edited_bytes(original, edit):
    if original.count(edit['old_text']) != 1:
        raise ValueError('OLD_TEXT_NOT_UNIQUE')
    raw = original.replace(edit['old_text'], edit['new_text'], 1).encode('utf-8')
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError('SOURCE_TOO_LARGE')
    if hashlib.sha256(raw).hexdigest() != edit['target_sha256']:
        raise ValueError('TARGET_DIGEST_MISMATCH')
    return raw

def run(api, token, job):
    job = validate(job)
    rid, base = job['request_id'], job['base_sha']
    branch = 'ish-batch-' + rid
    phase = 'START'
    def call(method, path, data=None):
        nonlocal phase
        phase = method + '_' + path.split('?')[0].split('/')[-1].upper()[:28]
        try:
            return api(method, REPO + path, token, data) if data is not None else api(method, REPO + path, token)
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                raise PermissionDenied(phase) from None
            raise
    def result(status, reason):
        return {'request_id':rid, 'action':ACTION, 'status':status, 'reason':reason, 'branch':branch}
    def branch_sha():
        ref = call('GET', '/git/ref/heads/' + branch)
        return (ref.get('object') or {}).get('sha')
    # Prepare all candidate files and validate ALL their exact expected digests.
    finals = {}
    for edit in job['edits']:
        item = call('GET', '/contents/' + edit['path'] + '?ref=' + base)
        if item.get('sha') != edit['expected_blob_sha']:
            return result('ERROR', 'ORIGINAL_BLOB_MISMATCH')
        try:
            finals[edit['path']] = edited_bytes(decode_file(item), edit)
        except (ValueError, UnicodeError) as exc:
            return result('ERROR', str(exc))
    # A prior exact replay may be checked without altering refs.
    existing = None
    try:
        existing = branch_sha()
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    if existing and existing != base:
        commit = call('GET', '/git/commits/' + existing)
        parents = commit.get('parents') or []
        if len(parents) != 1 or parents[0].get('sha') != base:
            return result('ERROR', 'EXISTING_BRANCH_CONFLICT')
        for path, raw in finals.items():
            item = call('GET', '/contents/' + path + '?ref=' + existing)
            if decode_file(item).encode('utf-8') != raw:
                return result('ERROR', 'EXISTING_BRANCH_CONFLICT')
        comparison = call('GET', '/compare/' + base + '...' + existing)
        changed = {f.get('filename') for f in comparison.get('files', [])}
        if (comparison.get('ahead_by') != 1 or
                comparison.get('total_commits') != 1 or changed != set(finals)):
            return result('ERROR', 'EXISTING_BRANCH_CONFLICT')
        return result('OK', 'ALREADY_COMMITTED')
    if existing:
        return result('ERROR', 'EXISTING_BRANCH_CONFLICT')
    head = call('GET', '/git/ref/heads/main')
    if (head.get('object') or {}).get('sha') != base:
        return result('ERROR', 'BASE_SHA_MOVED')
    base_commit = call('GET', '/git/commits/' + base)
    tree_sha = (base_commit.get('tree') or {}).get('sha')
    if not isinstance(tree_sha, str) or not SHA.fullmatch(tree_sha):
        return result('ERROR', 'BASE_TREE_INVALID')
    # Ref is created first. All subsequent failures leave main untouched.
    try:
        call('POST', '/git/refs', {'ref':'refs/heads/' + branch, 'sha':base})
    except urllib.error.HTTPError as exc:
        if exc.code == 422:
            return result('ERROR', 'EXISTING_BRANCH_CONFLICT')
        raise
    elements = []
    for path, raw in finals.items():
        blob = call('POST', '/git/blobs', {'content':base64.b64encode(raw).decode('ascii'), 'encoding':'base64'})
        sha = blob.get('sha')
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            return result('ERROR', 'BLOB_CREATE_UNVERIFIED')
        elements.append({'path':path, 'mode':'100644', 'type':'blob', 'sha':sha})
    tree = call('POST', '/git/trees', {'base_tree':tree_sha, 'tree':elements})
    if not isinstance(tree.get('sha'), str) or not SHA.fullmatch(tree['sha']):
        return result('ERROR', 'TREE_CREATE_UNVERIFIED')
    commit = call('POST', '/git/commits', {'message':'chore: approved iSH batch patch ' + rid,
                                         'tree':tree['sha'], 'parents':[base]})
    target_sha = commit.get('sha')
    if not isinstance(target_sha, str) or not SHA.fullmatch(target_sha):
        return result('ERROR', 'COMMIT_CREATE_UNVERIFIED')
    if branch_sha() != base:
        return result('ERROR', 'BRANCH_MOVED')
    if (call('GET', '/git/ref/heads/main').get('object') or {}).get('sha') != base:
        return result('ERROR', 'BASE_SHA_MOVED')
    call('PATCH', '/git/refs/heads/' + branch, {'sha':target_sha, 'force':False})
    if branch_sha() != target_sha:
        return result('ERROR', 'READBACK_REF_MISMATCH')
    for path, raw in finals.items():
        actual = call('GET', '/contents/' + path + '?ref=' + target_sha)
        if decode_file(actual).encode('utf-8') != raw:
            return result('ERROR', 'READBACK_CONTENT_MISMATCH')
    return result('OK', 'COMMIT_VERIFIED')
