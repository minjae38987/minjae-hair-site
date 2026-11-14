const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'styles/mens-leaf-volume-perm/index.html'),'utf8');
test('Leaf page retains canonical, before/after, and exactly one H1',()=>{
  assert.equal((html.match(/<h1\b/g)||[]).length,1);
  assert.equal((html.match(/<img\b/g)||[]).length,2);
  assert.match(html,/rel="canonical"/);
  assert.match(html,/BEFORE ·/);
  assert.match(html,/AFTER ·/);
});
test('Leaf consultation text does not make unsupported mandatory-perm or result guarantee claims',()=>{
  assert.match(html,/id="consult-decision"/);
  assert.match(html,/길이와 무게/);
  assert.match(html,/뿌리와 모류/);
  assert.match(html,/스타일 재현/);
  assert.match(html,/볼륨펌이 필수인가요\?/);
  assert.match(html,/필수는 아닙니다/);
});
test('Both mobile and article Naver booking CTAs and tracking stay intact',()=>{
  assert.equal((html.match(/m\.booking\.naver\.com\/booking\//g)||[]).length,2);
  assert.match(html,/id="mobile-booking-cta"/);
  assert.match(html,/assets\/booking-analytics\.js/);
  assert.match(html,/assets\/ga4-consent\.js/);
});
