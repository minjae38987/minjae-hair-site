import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
const out='naver-audit-results';
fs.mkdirSync(out,{recursive:true});
const urls=[
 ['minjae','https://m.booking.naver.com/booking/13/bizes/1512690/items/8096768?theme=place&tab=details&lang=ko&area=pll'],
 ['mande_dogyeom','https://m.booking.naver.com/booking/13/bizes/1179861/items/8008395?theme=place&tab=details&lang=ko&area=ple'],
 ['mande_junseon','https://m.booking.naver.com/booking/13/bizes/1179861/items/6334851?theme=place&tab=details&lang=ko&area=ple'],
 ['mande_jiho','https://m.booking.naver.com/booking/13/bizes/1179861/items/6333038?theme=place&tab=details&lang=ko&area=ple'],
 ['iron_hyemin','https://m.booking.naver.com/booking/13/bizes/1264884/items/6783456?theme=place&tab=details&lang=ko&area=ple'],
 ['iron_dongwoo','https://m.booking.naver.com/booking/13/bizes/1264884/items/8045486?theme=place&tab=details&lang=ko&area=ple'],
 ['iron_seonho','https://m.booking.naver.com/booking/13/bizes/1264884/items/8045412?theme=place&tab=details&lang=ko&area=ple'],
 ['view_yura','https://m.booking.naver.com/booking/13/bizes/217940/items/3007996?theme=place&tab=details&lang=ko&area=ple'],
 ['view_seyeon','https://m.booking.naver.com/booking/13/bizes/217940/items/3007979?theme=place&tab=details&lang=ko&area=ple']
]
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const report=[];
try{
 for(const [name,url] of urls){
   const ctx=await browser.newContext({viewport:{width:390,height:844},locale:'ko-KR',timezoneId:'Asia/Seoul',userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'});
   const page=await ctx.newPage();const failed=[];
   page.on('requestfailed',req=>{if(failed.length<8)failed.push({domain:new URL(req.url()).hostname,reason:req.failure()?.errorText});});
   const entry={name,url,access:'unknown'};
   try{
     const res=await page.goto(url,{waitUntil:'domcontentloaded',timeout:35000});
     await page.waitForTimeout(4500);
     entry.status=res?.status()||null;entry.finalUrl=page.url();
     entry.title=(await page.title()).slice(0,160);
     const body=(await page.locator('body').innerText({timeout:12000}).catch(()=>''));entry.textLength=body.length;
     entry.securityChallenge=/보안 확인을 완료해 주세요|가상으로 제작된|실제 영수증 사진이 아닙니다/.test(body);
     entry.visibleExcerpt=body.replace(/\\s+/g,' ').slice(0,4800);
     entry.access=body.length>100?'rendered':'limited';
     entry.flags={
       hasShop:body.includes('에이점헤어'),
       hasDesigner:body.includes('민재'),
       hasBooking:body.includes('예약'),
       hasPrice:body.includes('원'),
       hasReview:body.includes('리뷰'),
       hasCaptcha:/자동입력|비정상적인 접근|접근이 제한|captcha|로봇|보안문자/i.test(body)
     };
     const relevant=await page.locator('a[href]').evaluateAll(nodes=>nodes.filter(a=>/에이점헤어|민재|예약|지도/.test(a.innerText||'')).slice(0,12).map(a=>({text:(a.innerText||'').slice(0,65),href:(a.href||'').slice(0,180)}))).catch(()=>[]);
     entry.relevantLinks=relevant;
     const normalized=body.replace(/\\s+/g,' ');
     for(const term of ['인기 스타일리스트','인기스타일리스트','인기 미용실','인기스타일']){
       const k=normalized.indexOf(term);if(k>=0) entry['section_'+term]=normalized.slice(Math.max(0,k-250),k+2400);
     }
     entry.stylistBookingLinks=await page.locator('a[href*="m.booking.naver.com/booking/"]').evaluateAll(nodes=>nodes.slice(0,25).map(a=>({text:(a.innerText||'').trim().slice(0,120),href:a.href.slice(0,160)}))).catch(()=>[]);
     entry.topText=normalized.slice(0,5400);
     if(name.startsWith('search_')) {
       entry.placeCards=await page.locator('a[href*="m.place.naver.com/hairshop/"]').evaluateAll(nodes=>nodes.slice(0,15).map(a=>({name:(a.innerText||'').trim().slice(0,75),url:a.href.split('?')[0]}))).catch(()=>[]);
       entry.ourPlaceVisible=entry.placeCards.some(a=>a.url.includes('/2074303770'));
     }
     if(name==='booking_menu') {
       entry.serviceExcerpt=body.slice(0,3200);
       // Read-only: open the publicly displayed perm category, do not select a time or book.
       const permTab=page.getByText('펌',{exact:true}).first();
       if(await permTab.count()){
         await permTab.click({timeout:7000}).catch(()=>{});
         await page.waitForTimeout(1200);
         const permText=await page.locator('body').innerText().catch(()=> '');
         const menuStart=permText.indexOf('시술 메뉴를 선택해 주세요');
         entry.permMenuExcerpt=(menuStart>=0?permText.slice(menuStart):permText).slice(0,2600);
         entry.partialDownPermListed=/부분\s*다운펌|다운펌\s*25,?000|25,?000원/.test(entry.permMenuExcerpt);
       }
     }
     await page.screenshot({path:path.join(out,name+'.png'),fullPage:false,timeout:14000}).catch(()=>{});
   }catch(error){entry.access='error';entry.error=String(error).slice(0,500);}
   entry.failedRequests=failed;
   report.push(entry);
   console.log('NAVER_PUBLIC_AUDIT '+JSON.stringify(entry));
   await ctx.close();
 }
}finally{await browser.close();}
fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({checkedAt:new Date().toISOString(),results:report},null,2));
console.log('NAVER_PUBLIC_AUDIT_SUMMARY '+JSON.stringify(report.map(x=>({name:x.name,status:x.status,access:x.access,flags:x.flags,finalUrl:x.finalUrl}))));
