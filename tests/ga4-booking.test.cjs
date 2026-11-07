const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const root = require('node:path').resolve(__dirname, '..');
const tracking = readFileSync(require('node:path').join(root,'assets/booking-analytics.js'),'utf8');
const consent = readFileSync(require('node:path').join(root,'assets/ga4-consent.js'),'utf8');
const html = [
  'index.html',
  'styles/mens-leaf-cut-before-after/index.html',
  'styles/mens-leaf-volume-perm/index.html',
  'styles/mens-down-perm-guide/index.html'
];
test('All four pages load consent and booking scripts', () => {
  for (const page of html) {
    const source = readFileSync(require('node:path').join(root,page),'utf8');
    assert.match(source,/assets\/booking-analytics\.js/);
    assert.match(source,/assets\/ga4-consent\.js/);
    assert.ok(source.indexOf('booking-analytics.js') < source.indexOf('ga4-consent.js'));
  }
  assert.match(consent,/G-HJ7ZN6WJWH/);
});
test('Booking click tracking is consent gated and distinguishes placements', () => {
  let handler, emitted = [], sent = [], flags = {};
  const doc = {
    baseURI:'https://minjae38987.github.io/minjae-hair-site/',
    addEventListener: (name,cb) => { if(name==='click') handler=cb; },
    dispatchEvent: e => emitted.push(e)
  };
  const ctx = {
    document:doc, window:{location:{pathname:'/styles/mens-leaf-volume-perm/'}, ...flags},
    URL, CustomEvent:class {constructor(type,opts){this.type=type;this.detail=opts.detail;} }
  };
  vm.runInNewContext(tracking,ctx);
  function click(selector) {
    const anchor = {
      href:'https://m.booking.naver.com/booking/13/bizes/1512690/items/8096768',
      closest(q) {
        if(q==='a[href]') return this;
        if(q==='.mobile-booking-cta') return selector==='mobile_sticky' ? {} : null;
        if(q==='header, nav') return selector==='header' ? {} : null;
        if(q==='#home, .hero') return selector==='hero' ? {} : null;
        if(q==='#visit, .contact, .cta') return selector==='content_cta' ? {} : null;
        if(q==='main, article, aside') return selector==='article_cta' ? {} : null;
        return null;
      }
    };
    handler({target:anchor});
  }
  click('hero');
  assert.equal(emitted.length,1);
  assert.equal(emitted[0].detail.booking_button_location,'hero');
  assert.equal(emitted[0].detail.page_path,'/styles/mens-leaf-volume-perm/');
  ctx.window.gtag=(...args)=>sent.push(args);
  for(const location of ['header','mobile_sticky','content_cta','article_cta']) click(location);
  assert.deepEqual(sent.map(x=>x[2].booking_button_location), ['header','mobile_sticky','content_cta','article_cta']);
  ctx.window['ga-disable-G-HJ7ZN6WJWH']=true;
  click('hero');
  assert.equal(sent.length,4);
  assert.equal(emitted.length,6);
});
