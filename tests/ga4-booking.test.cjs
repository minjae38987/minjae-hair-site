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

test('Explicit QA link marks booking events but unmarked visits remain unclassified', () => {
  const sent = [];
  let handler;
  const storage = new Map();
  const sessionStorage = {
    setItem(k,v){storage.set(k,v);},
    getItem(k){return storage.get(k) || null;},
    removeItem(k){storage.delete(k);}
  };
  const window = {
    location:{ pathname:'/minjae-hair-site/', search:'?analytics_qa=1' },
    sessionStorage, gtag:(...args)=>sent.push(args)
  };
  const anchor={
    href:'https://m.booking.naver.com/booking/13/bizes/1512690/items/8096768',
    closest(q){ return q==='a[href]' ? this : null; }
  };
  const document = {
    baseURI:'https://minjae38987.github.io/minjae-hair-site/',
    addEventListener:(name,fn)=>{if(name==='click')handler=fn;},
    dispatchEvent:()=>{}
  };
  vm.runInNewContext(tracking,{document,window,URL,URLSearchParams,CustomEvent:class{}});
  handler({target:anchor});
  assert.equal(sent[0][2].traffic_validation_status,'qa_marked');
  assert.equal(sent[0][0],'event');
  assert.equal(sent[0][1],'naver_booking_click');
  window.location.search='';
  handler({target:anchor});
  assert.equal(sent[1][2].traffic_validation_status,'qa_marked');
  window.location.search='?analytics_qa=0';
  handler({target:anchor});
  assert.equal(sent[2][2].traffic_validation_status,'unclassified');
  assert.equal(storage.has('minjae_analytics_qa_v1'),false);
  window.location.search='';
  handler({target:anchor});
  assert.equal(sent[3][2].traffic_validation_status,'unclassified');
});

test('Consent revoked suppresses GA4 booking click even when marked QA', () => {
  let handler;
  const sent=[];
  const window={
    location:{pathname:'/',search:'?analytics_qa=1'},
    sessionStorage:{setItem(){},getItem(){return null;},removeItem(){}},
    'ga-disable-G-HJ7ZN6WJWH':true,
    gtag:(...args)=>sent.push(args)
  };
  const anchor={
    href:'https://m.booking.naver.com/booking/13/bizes/1512690/items/8096768',
    closest(q){return q==='a[href]' ? this : null;}
  };
  const document={
    baseURI:'https://minjae38987.github.io/minjae-hair-site/',
    addEventListener:(name,fn)=>{if(name==='click')handler=fn;},
    dispatchEvent:()=>{}
  };
  vm.runInNewContext(tracking,{document,window,URL,URLSearchParams,CustomEvent:class{}});
  handler({target:anchor});
  assert.equal(sent.length,0);
});
