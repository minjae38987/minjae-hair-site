import { chromium } from 'playwright';

const BASE = 'https://minjae38987.github.io/minjae-hair-site/';
const ID = 'G-HJ7ZN6WJWH';
const paths = [
  '',
  'styles/mens-leaf-cut-before-after/',
  'styles/mens-leaf-volume-perm/',
  'styles/mens-down-perm-guide/'
];
const browser = await chromium.launch({headless:true, args:['--no-sandbox']});
const results = [];

try {
  for (const path of paths) {
    const context = await browser.newContext({viewport:{width:390,height:844}, locale:'ko-KR'});
    const page = await context.newPage();
    const collect = [];
    const errors = [];
    const tagResponses = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('response', res => {
      if (res.url().includes('googletagmanager.com/gtag/js')) {
        tagResponses.push({status:res.status(),url:res.url()});
      }
    });
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      // Never send test pageviews or booking clicks into real GA4.
      if (['google-analytics.com','www.google-analytics.com','region1.google-analytics.com'].includes(url.hostname) && url.pathname.endsWith('/collect')) {
        collect.push({id:url.searchParams.get('tid'),event:url.searchParams.get('en')});
        await route.fulfill({status:204,body:''});
      } else {
        await route.continue();
      }
    });
    try {
      const response = await page.goto(BASE+path,{waitUntil:'domcontentloaded',timeout:45000});
      if (response.status()!==200) throw new Error('Unexpected HTTP status '+response.status());
      await page.waitForSelector('.analytics-choice', {timeout:12000});
      const initialScriptCount = await page.evaluate(() => document.querySelectorAll('script[src*="googletagmanager.com/gtag/js"]').length);
      if (initialScriptCount!==0) throw new Error('Consent violation: tag loaded before permission');
      // Explicit rejection must persist and must not fetch Google Analytics.
      if (path === '') {
        await page.locator('.analytics-choice [data-reject]').click();
        await page.reload({waitUntil:'domcontentloaded'});
        await page.waitForSelector('.analytics-settings');
        const rejected = await page.evaluate(() => ({
          choice:localStorage.getItem('minjae_analytics_choice_v1'),
          tagCount:document.querySelectorAll('script[src*="googletagmanager.com/gtag/js"]').length,
          gtagType:typeof window.gtag
        }));
        if (rejected.choice !== 'no' || rejected.tagCount !== 0 || rejected.gtagType !== 'undefined')
          throw new Error('Refusal does not block GA4: '+JSON.stringify(rejected));
        await page.locator('.analytics-settings').click();
      }
      await page.locator('.analytics-choice [data-accept]').click();
      await page.waitForFunction(() => (window.dataLayer||[]).some(x=>x[0]==='config'),{timeout:15000});
      await page.waitForTimeout(4000);
      const config = await page.evaluate(() => (window.dataLayer||[]).filter(x=>x[0]==='config').map(x=>x[1]));
      if (!config.includes(ID)) throw new Error('Wrong tag ID: '+JSON.stringify(config));
      if (!tagResponses.some(x=>x.status===200&&x.url.includes(ID))) throw new Error('Google tag not loaded successfully: '+JSON.stringify(tagResponses));
      if (!collect.some(x=>x.id===ID&&x.event==='page_view')) throw new Error('page_view collect request not generated: '+JSON.stringify(collect));
      const booking = page.locator('a[href*="m.booking.naver.com/booking/"]').first();
      await booking.click();
      await page.waitForTimeout(1500);
      const event = await page.evaluate(() => (window.dataLayer||[]).filter(x=>x[0]==='event').map(x=>x[1]));
      if (!event.includes('naver_booking_click')) throw new Error('Booking custom event absent from dataLayer');
      if (!collect.some(x=>x.id===ID&&x.event==='naver_booking_click')) throw new Error('Booking GA4 collect request not generated');
      // Check user opt-out after an already initialized GA4 session.
      if (path === '') {
        await page.locator('.analytics-settings').click();
        await page.locator('.analytics-choice [data-reject]').click();
        await page.waitForLoadState('domcontentloaded');
        const revoked = await page.evaluate(() => ({
          choice:localStorage.getItem('minjae_analytics_choice_v1'),
          tagCount:document.querySelectorAll('script[src*="googletagmanager.com/gtag/js"]').length,
          gtagType:typeof window.gtag
        }));
        if (revoked.choice !== 'no' || revoked.tagCount !== 0 || revoked.gtagType !== 'undefined')
          throw new Error('Consent revocation does not stop GA4: '+JSON.stringify(revoked));
      }
      if (errors.length) throw new Error('JavaScript errors: '+JSON.stringify(errors));
      results.push({page:'/'+path,http:response.status(),tag:tagResponses[0].status,events:collect.map(x=>x.event),status:'PASS'});
    } finally {
      await context.close();
    }
  }
  console.log('GA4 LIVE FOUR PAGE DIAGNOSIS '+JSON.stringify(results,null,2));
} finally {
  await browser.close();
}
