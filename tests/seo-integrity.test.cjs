const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const domain = 'https://minjae38987.github.io/minjae-hair-site/';
const files = [
  'index.html',
  'styles/mens-leaf-cut-before-after/index.html',
  'styles/mens-leaf-volume-perm/index.html',
  'styles/mens-down-perm-guide/index.html'
];
const sitemap = readFileSync(path.join(root, 'sitemap.xml'), 'utf8');
const get = (source, regex) => source.match(regex)?.[1] || '';
const expectedUrl = file => file === 'index.html' ? domain : domain + file.replace(/index\.html$/, '');
test('Sitemap contains precisely the four canonical site URLs with valid modification dates', () => {
  const urls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m => m[1]);
  assert.equal(urls.length, files.length);
  assert.equal(new Set(urls).size, urls.length);
  for (const file of files) {
    const canonical = expectedUrl(file);
    assert.ok(urls.includes(canonical), 'Sitemap missing: ' + canonical);
  }
  for (const date of sitemap.matchAll(/<lastmod>([^<]+)<\/lastmod>/g)) {
    assert.match(date[1], /^\d{4}-\d{2}-\d{2}$/);
    assert.ok(!Number.isNaN(Date.parse(date[1])), 'Invalid lastmod date');
  }
});
test('Each indexable page has unique title, meta description, matching canonical and social URL', () => {
  const titles = new Set();
  const descriptions = new Set();
  for (const file of files) {
    const html = readFileSync(path.join(root, file), 'utf8');
    const title = get(html, /<title>([^<]+)<\/title>/);
    const description = get(html, /<meta name="description" content="([^"]+)"/);
    const canonical = get(html, /<link rel="canonical" href="([^"]+)"/);
    const socialUrl = get(html, /<meta property="og:url" content="([^"]+)"/);
    assert.ok(title.length >= 15, 'Missing/descriptive title: ' + file);
    assert.ok(description.length >= 35, 'Missing/descriptive description: ' + file);
    assert.ok(!titles.has(title), 'Duplicate title: ' + file);
    assert.ok(!descriptions.has(description), 'Duplicate description: ' + file);
    titles.add(title);
    descriptions.add(description);
    assert.equal(canonical, expectedUrl(file), 'Wrong canonical: ' + file);
    assert.equal(socialUrl, canonical, 'Open Graph URL does not match canonical: ' + file);
    assert.equal((html.match(/<h1(?:\s|>)/g) || []).length, 1, 'Expected one H1: ' + file);
    assert.doesNotMatch(html, /<meta\s+name="robots"\s+content="[^"]*noindex/i);
  }
});
test('Every style guide has valid WebPage and two-step BreadcrumbList schema', () => {
  for (const file of files.slice(1)) {
    const html = readFileSync(path.join(root, file), 'utf8');
    const schemas = [...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map(m => JSON.parse(m[1]));
    const nodes = schemas.flatMap(x => x['@graph'] || [x]);
    const webPage = nodes.find(x => x['@type'] === 'WebPage');
    const breadcrumb = nodes.find(x => x['@type'] === 'BreadcrumbList');
    assert.ok(webPage, 'Missing WebPage: ' + file);
    assert.ok(breadcrumb, 'Missing breadcrumb: ' + file);
    assert.equal(webPage.url, expectedUrl(file));
    assert.equal(webPage.breadcrumb['@id'], expectedUrl(file) + '#breadcrumb');
    assert.equal(breadcrumb.itemListElement.length, 2);
    assert.equal(breadcrumb.itemListElement[0].item, domain);
    assert.equal(breadcrumb.itemListElement[1].item, expectedUrl(file));
  }
});
test('Sitemap URL is listed in project robots document', () => {
  const robots = readFileSync(path.join(root, 'robots.txt'), 'utf8');
  assert.ok(robots.includes('Sitemap: ' + domain + 'sitemap.xml'));
});

test('Instagram gallery defers all embeds until requested or visible', () => {
  const html = readFileSync(path.join(root, 'index.html'), 'utf8');
  const embeds = [...html.matchAll(/<iframe[^>]*instagram\.com\/reel\/[^>]+>/g)].map(m => m[0]);
  assert.equal(embeds.length, 10, 'Expected ten gallery reel embeds');
  for (const iframe of embeds) {
    assert.match(iframe, /data-src="https:\/\/www\.instagram\.com\/reel\//);
    assert.doesNotMatch(iframe, /\ssrc=/, 'Instagram iframe loads before viewport');
    assert.match(iframe, /loading="lazy"/);
  }
  assert.match(html, /IntersectionObserver/);
});

test('Home haircut guidance provides distinct user-first help and crawlable style links', () => {
  const html = readFileSync(path.join(root, 'index.html'), 'utf8');
  const start = html.indexOf('id="mens-cut-consultation"');
  const end = html.indexOf('id="seo-styles"', start);
  assert.ok(start > 0 && end > start, 'Missing haircut choice guide');
  const section = html.slice(start, end);
  assert.match(section, /서울대입구 남자 커트/);
  assert.match(section, /옆머리가 뜨는 경우/);
  assert.match(section, /앞머리가 쉽게 가라앉는 경우/);
  assert.match(section, /긴 머리를 정리하는 경우/);
  for (const slug of ['mens-down-perm-guide','mens-leaf-volume-perm','mens-leaf-cut-before-after']) {
    assert.ok(section.includes('href="styles/'+slug+'/'), 'Missing contextual style link: '+slug);
  }
  assert.match(section, /m\.booking\.naver\.com\/booking\//);
});

test('Portfolio images use same-origin GitHub Pages paths and keep accessible alternative text', () => {
  let imageCount = 0;
  for (const file of files) {
    const html = readFileSync(path.join(root, file), 'utf8');
    assert.ok(!html.includes('raw.githubusercontent.com/minjae38987/minjae-hair-site/main/blogger-media/'), 'Raw GitHub image host remains: '+file);
    const images = [...html.matchAll(/<img\b[^>]*>/g)].map(m=>m[0]);
    for (const img of images) {
      imageCount++;
      const src = img.match(/\bsrc="([^"]+)"/)?.[1];
      assert.ok(src?.startsWith(domain+'blogger-media/'), 'Image should use first-party URL: '+file);
      assert.match(img, /\balt="[^"]+"/, 'Image should have meaningful alt text');
      assert.match(img, /\bwidth="\d+"/);
      assert.match(img, /\bheight="\d+"/);
    }
  }
  assert.ok(imageCount >= 6, 'Expected existing portfolio images');
});
