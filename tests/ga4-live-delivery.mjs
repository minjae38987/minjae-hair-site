import { chromium } from 'playwright';

const BASE = 'https://minjae38987.github.io/minjae-hair-site/';
const ID = 'G-ZZWKEPMY3W';
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ko-KR' });
const page = await context.newPage();
const calls = [];
const errors = [];
const googleLoads = [];
page.on('pageerror', e => errors.push(e.message));
page.on('request', req => {
  const url = req.url();
  if (/googletagmanager\.com\/gtag\/js/.test(url)) googleLoads.push(url);
});
await page.route('**/*', async route => {
  const url = new URL(route.request().url());
  // Prevent any synthetic test hits from reaching actual GA4.
  if (/(^|\.)google-analytics\.com$/.test(url.hostname) &&
      /\/(g\/)?collect|\/j\/collect|\/r\/collect/.test(url.pathname)) {
    calls.push({path: url.pathname, measurementId: url.searchParams.get('tid'), eventName: url.searchParams.get('en')});
    await route.fulfill({status:204,body:''});
  } else {
    await route.continue();
  }
});
try {
  const response = await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 45000 });
  if (response.status() !== 200) throw new Error('Public homepage HTTP '+response.status());
  await page.waitForSelector('.analytics-choice', {timeout:15000});
  const initial = await page.evaluate(() => ({
    scripts: Array.from(document.scripts).map(s=>s.src).filter(x=>x.includes('googletagmanager.com/gtag/js')),
    choice: localStorage.getItem('minjae_analytics_choice_v1')
  }));
  if (initial.scripts.length) throw new Error('Privacy failure: GA script loaded before consent');
  await page.locator('.analytics-choice [data-accept]').click();
  await page.waitForFunction(() => typeof window.gtag === 'function', {timeout:15000});
  await page.waitForTimeout(7000);
  const afterAccept = await page.evaluate(() => ({
    choice: localStorage.getItem('minjae_analytics_choice_v1'),
    config: (window.dataLayer||[]).filter(x=>x[0]==='config').map(x=>x[1]),
    script: Array.from(document.scripts).map(s=>s.src).filter(x=>x.includes('googletagmanager.com/gtag/js'))
  }));
  await page.locator('a[href*="m.booking.naver.com/booking/"]').first().click();
  await page.waitForTimeout(5000);
  const dataLayer = await page.evaluate(() => (window.dataLayer||[]).filter(x=>x[0]==='event').map(x=>({event:x[1],details:x[2]})));
  const result={publicStatus:response.status(),initial,afterAccept,googleLoads,calls,dataLayer,errors};
  console.log('LIVE GA4 DIAGNOSTICS '+JSON.stringify(result,null,2));
  if (!afterAccept.config.includes(ID)) throw new Error('Unexpected GA4 config ID');
  if (!dataLayer.some(x=>x.event==='naver_booking_click')) throw new Error('Booking event not added to gtag data layer');
  if (!googleLoads.some(x=>x.includes(ID))) throw new Error('Google tag script not requested');
  if (!calls.some(x=>x.measurementId===ID && x.eventName==='page_view')) throw new Error('No GA4 page_view delivery request observed');
  if (!calls.some(x=>x.measurementId===ID && x.eventName==='naver_booking_click')) throw new Error('No GA4 booking-click delivery request observed');
  if (errors.length) console.warn('Browser JavaScript errors',errors);
} finally {
  await browser.close();
}
