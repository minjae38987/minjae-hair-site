#!/usr/bin/env python3
"""Offline batch patch security and atomicity regression (Python 3.9+)."""
import base64
import hashlib
from importlib.machinery import SourceFileLoader
from pathlib import Path
import unittest
import urllib.error

m=SourceFileLoader('ish_batch_patch',str(Path(__file__).with_name('ish-batch-patch.py'))).load_module()
BASE='a'*40
FILES={'scripts/dual_runner_protocol.mjs':'const a = 1;\n','scripts/dual_runner_router.mjs':'const b = 1;\n'}
def job():
    return {'request_id':'batch_smoke1','action':m.ACTION,'base_sha':BASE,
            'edits':[{'path':p,'expected_blob_sha':'b'*40,'old_text':' = 1','new_text':' = 2',
                      'target_sha256':hashlib.sha256(s.replace(' = 1',' = 2').encode()).hexdigest()}
                     for p,s in FILES.items()]}
class API:
    def __init__(self):
        self.ref=None;self.files={};self.writes=0;self.main=BASE;self.events=[];self.extra=False
    def __call__(self,method,path,token,data=None):
        self.events.append((method,path))
        path=path[len(m.REPO):]
        if path=='/git/ref/heads/main':return {'object':{'sha':self.main}}
        if path.startswith('/git/ref/heads/ish-batch-'):
            if self.ref is None:raise urllib.error.HTTPError(path,404,'absent',None,None)
            return {'object':{'sha':self.ref}}
        if path.startswith('/contents/'):
            p=path.split('?')[0][10:]
            ref=path.split('ref=')[1]
            s=(self.files.get(p,FILES[p]) if ref!=BASE else FILES[p])
            return {'type':'file','sha':'b'*40,'content':base64.b64encode(s.encode()).decode()}
        if path.startswith('/git/commits/') and method=='GET':
            return {'tree':{'sha':'c'*40},'parents':([{'sha':BASE}] if not path.endswith(BASE) else [])}
        if path=='/git/refs' and method=='POST':
            if self.ref is not None:raise urllib.error.HTTPError(path,422,'exists',None,None)
            self.ref=BASE;return {'object':{'sha':self.ref}}
        if path=='/git/blobs' and method=='POST':
            self.writes+=1
            self.files[self.writes]=base64.b64decode(data['content']).decode()
            return {'sha':chr(100+self.writes)*40}
        if path=='/git/trees' and method=='POST':
            self.tree=data['tree'];return {'sha':'e'*40}
        if path=='/git/commits' and method=='POST':return {'sha':'f'*40}
        if path.startswith('/git/refs/heads/') and method=='PATCH':
            self.ref=data['sha']
            for i,e in enumerate(self.tree,1):self.files[e['path']]=self.files[i]
            return {'object':{'sha':self.ref}}
        if path.startswith('/compare/'):
            return {'ahead_by':1,'total_commits':1,
                    'files':[{'filename':p} for p in list(FILES)+(['unexpected'] if self.extra else [])]}
        raise AssertionError((method,path))
class Tests(unittest.TestCase):
    def test_two_file_atomic_commit(self):
        a=API();r=m.run(a,'secret',job())
        self.assertEqual(r['reason'],'COMMIT_VERIFIED')
        self.assertEqual(a.writes,2)
        self.assertEqual(len([x for x in a.events if x[0]=='PATCH']),1)
        self.assertFalse(any(p.endswith('/main') and v!='GET' for v,p in a.events))
    def test_replay(self):
        a=API();m.run(a,'secret',job())
        self.assertEqual(m.run(a,'secret',job())['reason'],'ALREADY_COMMITTED')
        self.assertEqual(a.writes,2)
    def test_unexpected_change_rejected(self):
        a=API();m.run(a,'secret',job());a.extra=True
        self.assertEqual(m.run(a,'secret',job())['reason'],'EXISTING_BRANCH_CONFLICT')
    def test_sha_and_digest_fail_closed(self):
        for field,value in [('expected_blob_sha','0'*40),('target_sha256','0'*64)]:
            a=API();j=job();j['edits'][1][field]=value
            self.assertEqual(m.run(a,'secret',j)['status'],'ERROR')
            self.assertEqual(a.writes,0)
    def test_stale_main(self):
        a=API();a.main='0'*40
        self.assertEqual(m.run(a,'secret',job())['reason'],'BASE_SHA_MOVED')
    def test_no_extra_fields_and_unsafe_paths(self):
        for path in ('../.env','tools/ish-bridge-v2.py','.github/workflows/deploy.yml'):
            j=job();j['edits'][0]['path']=path
            with self.assertRaises(ValueError):m.validate(j)
        j=job();j['shell']='whoami'
        with self.assertRaises(ValueError):m.validate(j)
        j=job();j['edits'][1]['path']=j['edits'][0]['path']
        with self.assertRaises(ValueError):m.validate(j)
        j=job();j['edits']=j['edits'][:1]
        with self.assertRaises(ValueError):m.validate(j)
    def test_invalid_edit_length_and_ambiguity(self):
        j=job();j['edits'][0]['new_text']='x'*1001
        with self.assertRaises(ValueError):m.validate(j)
        with self.assertRaises(ValueError):m.edited_bytes('abc abc',{'old_text':'abc','new_text':'x','target_sha256':'0'*64})
    def test_existing_empty_branch(self):
        a=API();a.ref=BASE
        self.assertEqual(m.run(a,'secret',job())['reason'],'EXISTING_BRANCH_CONFLICT')
    def test_token_never_in_result(self):
        self.assertNotIn('private_token',str(m.run(API(),'private_token',job())))
if __name__=='__main__':unittest.main(verbosity=2)
