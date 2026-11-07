#!/usr/bin/env node
/**
 * Real mobile browser audit for minjae-hair-site.
 * Playwright Chromium renders 4 published pages; Lighthouse audits 2 important pages.
 * Output: audit-mobile/report.json, report.md, screenshots/, lighthouse/*.json
 */
import { chromium, devices } from 'playwright';
import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync, existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const SITE = 'https://minjae38987.github.io/minjae-hair-site/';
const TARGETS = [
  ['home', SITE],
  ['leaf-cut', SITE + 'styles/mens-leaf-cut-before-after/'],
  ['volume-perm', SITE + 'styles/mens-leaf-volume-perm/'],
  ['down-perm', SITE + 'styles/mens-down-perm-guide/'],
];
const OUT = process.env.AUDIT_OUTPUT || 'audit-mobile';
mkdirSync(OUT, { recursive: true });
mkdirSync(join(OUT, 'screenshots'), { recursive: true });
mkdirSync(join(OUT, 'lighthouse'), { recursive: true });

const report = { auditedAt: new Date().toISOString(), engine: 'Playwright Chromium + Lighthouse', targets: [], lighthouse: [], limitations: [
  'A rendered page and laboratory Lighthouse scores do not confirm Google indexing or ranking.',
  'Simulated Lighthouse lab data is not real-user CrUX Core Web Vitals.',
  'Embedded Instagram content can be restricted by the platform independently of website code.'
] };
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const ctx = await browser.newContext({ ...devices['iPhone 13'], locale: 'ko-KR', colorScheme: 'light' });
for (const [name, url] of TARGETS) {
  const page = await ctx.newPage();
  const result = { name, url, status: 'unchecked', jsErrors: [], firstPartyFailures: [] };
  page.on('pageerror', err => result.jsErrors.push(String(err.message).slice(0,240)));
  page.on('response', response => {
    const resUrl = response.url();
    if (resUrl.startsWith(SITE) && response.status() >= 400) result.firstPartyFailures.push({ status: response.status(), url: resUrl });
  });
  try {
    const res = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 40000 });
    await page.waitForTimeout(1200);
    result.http = res?.status() ?? null;
    result.status = res?.ok() ? 'rendered' : 'http-error';
    result.title = await page.title();
    result.h1 = await page.locator('h1').count();
    result.hasBookingLink = await page.locator('a[href*="booking.naver.com"]').count() > 0;
    result.hasMobileBooking = await page.locator('#mobile-booking-cta a').isVisible().catch(() => false);
    // Lazy-loading images often sit below the initial viewport; scroll each into view.
    // Keep the initial viewport metrics above unchanged.
    result.totalImages = await page.locator('img').count();
    for (let i = 0; i < result.totalImages; i++) {
      const image = page.locator('img').nth(i);
      await image.scrollIntoViewIfNeeded({ timeout: 8000 }).catch(() => {});
      await image.evaluate(el => {
        if (el.complete) return;
        return new Promise(resolve => {
          el.addEventListener('load', resolve, { once: true });
          el.addEventListener('error', resolve, { once: true });
          setTimeout(resolve, 5000);
        });
      }).catch(() => {});
    }
    result.visibleImages = await page.locator('img').evaluateAll(items => items.filter(x => x.complete && x.naturalWidth > 0).length);
    result.brokenImages = await page.locator('img').evaluateAll(items => items.filter(x => x.complete && x.naturalWidth === 0).map(x => x.src));
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await page.waitForTimeout(150);
    result.horizontalOverflowPx = await page.evaluate(() => Math.max(0, document.documentElement.scrollWidth - window.innerWidth));
    result.viewport = await page.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight }));
    result.blogLinks = await page.locator('a[href*="ahairmj.blogspot.com"], a[href*="blog.naver.com/a-hair_mj"]').count();
    await page.screenshot({ path: join(OUT, 'screenshots', name + '.png'), fullPage: false });
  } catch(err) {
    result.status = 'browser-error';
    result.error = String(err.message).slice(0, 600);
  } finally {
    report.targets.push(result);
    console.log('MOBILE_PAGE', JSON.stringify(result));
    await page.close();
  }
}
await ctx.close();
await browser.close();

const executable = chromium.executablePath();
for (const [name, url] of [TARGETS[0], TARGETS[3]]) {
  const file = join(OUT, 'lighthouse', name + '.json');
  const args = [
    'lighthouse', url,
    '--output=json', '--output-path=' + file,
    '--only-categories=performance,seo,accessibility',
    '--form-factor=mobile', '--throttling-method=simulate',
    '--chrome-flags=--headless --no-sandbox --disable-dev-shm-usage',
    '--quiet',
  ];
  const p = spawnSync('npx', ['--no-install', ...args], {
    env: { ...process.env, CHROME_PATH: executable },
    encoding: 'utf8', timeout: 210000, maxBuffer: 4_000_000,
  });
  const item = { name, url, completed: p.status === 0 && existsSync(file) };
  if (item.completed) {
    try {
      const obj = JSON.parse(readFileSync(file, 'utf8'));
      item.scores = Object.fromEntries(Object.entries(obj.categories || {}).map(([k,v]) => [k, Math.round((v.score ?? 0) * 100)]));
      for (const key of ['largest-contentful-paint','cumulative-layout-shift','total-blocking-time','first-contentful-paint','speed-index']) {
        const a = obj.audits?.[key]; if(a) item[key] = { numericValue: a.numericValue, displayValue: a.displayValue };
      }
      item.accessibilityFailures = (obj.categories?.accessibility?.auditRefs || [])
        .map(ref => ({ id: ref.id, weight: ref.weight, audit: obj.audits?.[ref.id] }))
        .filter(x => x.weight > 0 && x.audit && x.audit.score !== null && x.audit.score < 1)
        .map(x => ({
          id: x.id, title: x.audit.title, score: x.audit.score,
          elements: (x.audit.details?.items || []).slice(0, 4).map(y => ({
            html: (y.node?.snippet || y.node?.selector || '').slice(0, 260),
            explanation: (y.node?.explanation || '').slice(0, 240)
          }))
        }));
      item.seoFailures = (obj.categories?.seo?.auditRefs || [])
        .map(ref => ({ id: ref.id, weight: ref.weight, audit: obj.audits?.[ref.id] }))
        .filter(x => x.weight > 0 && x.audit && x.audit.score !== null && x.audit.score < 1)
        .map(x => ({ id: x.id, title: x.audit.title, score: x.audit.score }));
      item.opportunities = Object.entries(obj.audits || {})
        .filter(([k,v]) => v.details?.overallSavingsMs > 150 && v.score !== null && v.score < 0.9)
        .map(([k,v]) => ({ id:k, title:v.title, estimatedSavingsMs:Math.round(v.details.overallSavingsMs) }))
        .sort((a,b)=>b.estimatedSavingsMs-a.estimatedSavingsMs).slice(0,6);
    } catch(err) { item.completed=false; item.error=String(err); }
  } else {
    item.error = [p.error?.message, p.stderr?.slice(-1000), p.stdout?.slice(-400)].filter(Boolean).join(' | ').slice(0,1800);
  }
  report.lighthouse.push(item);
  console.log('LIGHTHOUSE', JSON.stringify(item));
}
writeFileSync(join(OUT, 'report.json'), JSON.stringify(report,null,2));
let md = '# 민재 헤어 모바일 실브라우저 / Lighthouse 점검\n\n';
md += '검사: '+report.auditedAt+' (UTC)\n\n';
md += '## 모바일 렌더링\n\n| 페이지 | HTTP | 예약 버튼 | 실제 이미지 | 가로 넘침 | JS 오류 |\n|---|---:|---|---|---:|---:|\n';
for (const x of report.targets) {
  md += '| '+x.name+' | '+(x.http??'-')+' | '+(x.hasMobileBooking?'표시':'미표시')+' | '+(x.visibleImages??'-')+'/'+(x.totalImages??'-')+' | '+(x.horizontalOverflowPx??'-')+'px | '+x.jsErrors.length+' |\n';
}
md += '\n## Lighthouse 실험실 측정\n\n| 페이지 | Performance | SEO | 접근성 | LCP | CLS | TBT |\n|---|---:|---:|---:|---|---|---|\n';
for (const x of report.lighthouse) {
  const s=x.scores||{};
  md += '| '+x.name+' | '+(s.performance??'-')+' | '+(s.seo??'-')+' | '+(s.accessibility??'-')+' | '+(x['largest-contentful-paint']?.displayValue??'-')+' | '+(x['cumulative-layout-shift']?.displayValue??'-')+' | '+(x['total-blocking-time']?.displayValue??'-')+' |\n';
  if (!x.completed) md += '\n**'+x.name+' Lighthouse 검사 오류:** '+x.error+'\n';
}
md += '\n## 측정의 한계\n\n'+report.limitations.map(x=>'- '+x).join('\n')+'\n';
writeFileSync(join(OUT,'report.md'),md);
console.log(md);
if(!report.targets.some(x=>x.status==='rendered')) process.exitCode=1;
