import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';

const folder='naver-booking-funnel-results';
mkdirSync(folder,{recursive:true});
const url='https://m.booking.naver.com/booking/13/bizes/1512690/items/8096768?theme=place&tab=book&lang=ko&area=pll';
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const ctx=await browser.newContext({viewport:{width:390,height:844},locale:'ko-KR',timezoneId:'Asia/Seoul',userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'});
const page=await ctx.newPage();
const report={checkedAt:new Date().toISOString(),target:url,policy:'PUBLIC VIEW ONLY: no log-in, personal information, calendar slot selection, reservation finalization, payment, or modifications',sections:[],warnings:[]};
const challenge=t=>/보안 확인을 완료해 주세요|비정상적인 접근|captcha|자동입력 방지/.test(t);
async function take(label){
 const body=await page.locator('body').innerText({timeout:7000}).catch(()=>'');
 const item={label,url:page.url(),visibleText:body.slice(0,5800),securityChallenge:challenge(body)};
 report.sections.push(item);
 await page.screenshot({path:folder+'/'+label+'.png',fullPage:false,timeout:6000}).catch(()=>{});
 console.log('NAVER_BOOKING_STAGE '+JSON.stringify({label,challenge:item.securityChallenge,url:item.url,excerpt:body.slice(0,3800)}));
 return body;
}
try{
 const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:25000});
 report.status=response?.status()??null;
 await page.waitForTimeout(2600);
 await take('01-initial');
 // Opening the product menu tabs cannot create or finalize a booking.
 for(const tab of ['컷','펌','컬러']){
   try{
     const t=page.getByText(tab,{exact:true}).first();
     if(await t.count()) {
       await t.click({timeout:3500});
       await page.waitForTimeout(450);
       const txt=await take('02-category-'+({컷:'cut',펌:'perm',컬러:'color'}[tab]));
       report['menu_'+tab]=(txt.match(/시술 메뉴를 선택해 주세요([\s\S]{0,3400})/)?.[1]||'').slice(0,3400);
     } else report.warnings.push('Missing category tab: '+tab);
   }catch(e){report.warnings.push('Failed tab '+tab+': '+String(e).slice(0,160));}
 }
 // Date navigation does not create a reservation. Inspect only enabled calendar dates and visible time labels.
 report.calendarDates=[];
 for(const day of [9,10,11,12,16,17,18,23,24,25]){
   try{
     const btn=page.getByRole('button',{name:String(day),exact:true}).first();
     if(!(await btn.count())){report.calendarDates.push({day,status:'date-button-not-found'});continue;}
     if(await btn.isDisabled()){report.calendarDates.push({day,status:'disabled'});continue;}
     await btn.click({timeout:3500});
     await page.waitForTimeout(850);
     const body=await page.locator('body').innerText().catch(()=>'');
     const beforeMenu=body.split('시술 메뉴를 선택해 주세요')[0]||'';
     const windowText=beforeMenu.slice(Math.max(0,beforeMenu.indexOf('날짜와 시간을 선택해 주세요'))).slice(-800);
     const matches=[...windowText.matchAll(/\b([0-9]{1,2}:[0-9]{2})\b/g)].map(m=>m[1]);
     const controls=await page.locator('button.btn_time').evaluateAll(nodes=>nodes.map(b=>({label:(b.innerText||'').trim(),disabled:b.disabled,ariaDisabled:b.getAttribute('aria-disabled'),className:(b.className||'').toString().slice(0,110)}))).catch(()=>[]);
     const slotDebug=day===9||day===10||day===16 ? await page.getByText('11:00',{exact:true}).first().evaluate(el=>({tag:el.tagName,html:el.parentElement?.outerHTML.slice(0,1250),ancestor:el.parentElement?.parentElement?.outerHTML.slice(0,1700)})).catch(()=>null) : null;
     report.calendarDates.push({day,status:'enabled',timeLabels:[...new Set(matches)],timeControls:controls,slotDebug,timeText:windowText.slice(-500),securityChallenge:challenge(body)});
     console.log('NAVER_BOOKING_DATE '+JSON.stringify(report.calendarDates[report.calendarDates.length-1]));
   }catch(e){report.calendarDates.push({day,status:'incomplete',error:String(e).slice(0,180)});}
 }
 // Do not select an appointment slot. Try only the next-stage UI with a sample cut menu selection.
 try{
   const c=page.getByText('컷',{exact:true}).first(); if(await c.count()) await c.click({timeout:3500});
   const target=page.getByText('남성커트[D]',{exact:false}).first();
   if(await target.count()){
     await target.click({timeout:4000});
     await page.waitForTimeout(500);
     await take('03-cut-selected');
   }else report.warnings.push('Cut item not located for non-finalizing navigation');
   const next=page.getByText('다음단계',{exact:true}).first();
   if(await next.count()){
     await next.click({timeout:3500});
     await page.waitForTimeout(1000);
     const txt=await take('04-next-step');
     report.nextStageReached=!challenge(txt)&&/날짜|시간|선택|예약|인원/.test(txt);
     report.dateTokens=[...new Set((txt.match(/11월\s*\d{1,2}일|\d{4}\.\s*\d{1,2}\.\s*\d{1,2}|월요일|화요일|수요일|목요일|금요일|토요일|일요일/g)||[]))].slice(0,24);
   }else report.warnings.push('Next stage control missing or disabled');
 }catch(e){report.warnings.push('Non-finalizing next-stage navigation: '+String(e).slice(0,200));}
 // Collect only visible calendar labels and button metadata, without clicking time slots or confirming a booking.
 report.visibleControls=await page.locator('button').evaluateAll(nodes=>nodes.slice(0,100).map(x=>({label:(x.innerText||x.getAttribute('aria-label')||'').trim().slice(0,70),disabled:x.disabled,ariaLabel:x.getAttribute('aria-label')})).filter(x=>x.label||x.ariaLabel)).catch(()=>[]);
 console.log('NAVER_BOOKING_CONTROLS '+JSON.stringify(report.visibleControls.slice(0,55)));
} catch(e){
 report.warnings.push('Top-level page error: '+String(e).slice(0,320));
} finally{
 writeFileSync(folder+'/result.json',JSON.stringify(report,null,2));
 const summary=['# 민재 디자이너 네이버 예약 고객 화면 검수','', '실행 시각 (UTC): '+report.checkedAt,'',
 '비로그인 모바일 공개 화면만 검사. 실제 예약, 고객 정보 입력, 결제, 최종 단계 진행 없음.',
 '','## 단계별 접근',...report.sections.map(x=>'- '+x.label+' : '+(x.securityChallenge?'보안제한':'화면 접근')+' / '+x.url),
 '', '## 컷 메뉴',report.menu_컷||'확보하지 못함','',
 '## 펌 메뉴',report.menu_펌||'확보하지 못함','',
 '## 컬러 메뉴',report.menu_컬러||'확보하지 못함','',
 '## 예약 날짜/시간 단계',report.nextStageReached?'일부 화면 도달':'도달 확인 불가',
 '','확인된 날짜 토큰: '+(report.dateTokens||[]).join(', '),
 '','## 한계',...report.warnings.map(x=>'- '+x),
 '','**공개 UI 접근이 정상이어도 실제 예약 가능 슬롯의 충분성·할인 계산·최종 결제 완료까지 검증했다는 뜻이 아닙니다.**'];
 writeFileSync(folder+'/summary.md',summary.join('\n')+'\n');
 await browser.close();
}
