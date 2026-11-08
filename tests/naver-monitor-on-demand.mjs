import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';

const BASE = 'https://search.naver.com/search.naver?query=';
const ownPlaceId = '2074303770';
const keywords = [
  '서울대입구역 미용실', '서울대입구 남자머리', '서울대입구 남자 커트',
  '서울대입구 다운펌', '서울대입구 남자 펌',
  '서울대입구 시스루댄디컷', '서울대입구 드롭컷',
  '서울대입구 리프컷', '서울대입구 필러스컷'
];
const stylists = [
  ['민재','1512690','8096768'],
  ['맨드살롱 도겸','1179861','8008395'],
  ['맨드살롱 준선','1179861','6334851'],
  ['맨드살롱 지호','1179861','6333038'],
  ['아이언맨즈 동우','1264884','8045486']
];
const output = 'naver-monitor-output';
mkdirSync(output,{recursive:true});
const time = new Date().toISOString();
const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
const result = { measuredAt:time, context:'GitHub-hosted anonymous Korean mobile Chromium. A single observation, not official rank or traffic statistics.', searches:[], stylists:[] };
const errors = [];

async function visit(url, read) {
  const context = await browser.newContext({
    viewport:{width:390,height:844},locale:'ko-KR',timezoneId:'Asia/Seoul',
    userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
  });
  try {
    const page = await context.newPage();
    const response = await page.goto(url,{waitUntil:'domcontentloaded',timeout:25000});
    await page.waitForTimeout(1800);
    const text = await page.locator('body').innerText().catch(()=>'');
    const challenged = /보안 확인을 완료해 주세요|비정상적인 접근|captcha|자동입력 방지/i.test(text);
    const status = response?.status() ?? null;
    const data = challenged ? {} : await read(page,text);
    return {httpStatus:status,challenged,accessible:status===200 && !challenged && text.length>120,...data};
  } catch(e) {
    return {httpStatus:null,challenged:false,accessible:false,error:String(e).slice(0,220)};
  } finally {await context.close();}
}
try {
  for (const keyword of keywords) {
    const url = BASE + encodeURIComponent(keyword);
    const observation = await visit(url, async (page,text) => {
      const raw = await page.locator('a[href*="m.place.naver.com/hairshop/"]').evaluateAll(links=>links.map(a=>({
        href:a.href.split('?')[0],label:(a.innerText||'').trim().slice(0,90)
      })));
      const seen = new Set();
      const cards = raw.filter(x=>{
        const m=x.href.match(/\/hairshop\/(\d+)$/);
        if(!m||!x.label||seen.has(m[1]))return false;
        seen.add(m[1]);return true;
      }).map(x=>({name:x.label,placeId:x.href.match(/\/hairshop\/(\d+)$/)[1]}));
      const ownCardIndex = cards.findIndex(x=>x.placeId===ownPlaceId);
      const ownMentions = [...text.matchAll(/에이점헤어/g)].length;
      return {capturedPlaceCards:cards.length,initialCards:cards.slice(0,7),
        ownPlaceCardObserved:ownCardIndex>=0,ownCardOrderIfObserved:ownCardIndex<0?null:ownCardIndex+1,
        ownMentionsInAllResults:ownMentions};
    });
    result.searches.push({keyword,...observation});
    console.log('NAVER_MONITOR_SEARCH '+JSON.stringify({keyword,accessible:observation.accessible,ownPlaceCardObserved:observation.ownPlaceCardObserved,capturedPlaceCards:observation.capturedPlaceCards}));
    if(!observation.accessible) errors.push(keyword);
  }
  for (const [name,businessId,itemId] of stylists) {
    const url='https://m.booking.naver.com/booking/13/bizes/'+businessId+'/items/'+itemId+'?tab=details&lang=ko';
    const observation=await visit(url,async (_page,text)=>{
      const count=(expr)=>{const m=text.match(expr);return m?Number(m[1].replaceAll(',','')):null;};
      const styleInfo=count(/스타일 정보\s*([\d,]+)/);
      return {
        recentStylingDisplay:count(/최근\s*([\d,]+)건 스타일링/),
        reviewDisplay:count(/리뷰\s*([\d,]+)/),
        styleInfoCount:styleInfo,
        returnVisitBadge:/재방문 많은/.test(text),
        visibleStyleLabels:(text.match(/최근\s*[\d,]+건 스타일링([\s\S]{0,140})/)?.[1]||'').slice(0,120)
      };
    });
    if (observation.accessible && (observation.recentStylingDisplay===null || observation.reviewDisplay===null || observation.styleInfoCount===null)) {
      observation.accessible=false;
      observation.error='Rendered page lacked one or more required public metrics; omitted rather than counted as zero.';
    }
    result.stylists.push({name,...observation});
    console.log('NAVER_MONITOR_STYLIST '+JSON.stringify({name,accessible:observation.accessible,recentStylingDisplay:observation.recentStylingDisplay,reviewDisplay:observation.reviewDisplay,styleInfoCount:observation.styleInfoCount}));
    if(!observation.accessible) errors.push(name);
  }
}finally{await browser.close();}
writeFileSync(output+'/observation.json',JSON.stringify(result,null,2));
const rows = [
  '# 네이버 플레이스 공개 데이터 수동 관측',
  '',
  '측정 시각 (UTC): '+time,
  '',
  '주의: 단일 익명 모바일 GitHub 실행 환경의 공개 화면. 공식 네이버 순위, 검색량, 고객 실제 노출률, 매출 또는 예약 전환율을 의미하지 않습니다.',
  '',
  '## 검색어별 플레이스 카드',
  '',
  '| 검색어 | 접근 | 관측된 카드 수 | 에이점헤어 카드 | 앞부분 경쟁 매장 |',
  '|---|---|---:|---|---|',
  ...result.searches.map(r=>'| '+r.keyword+' | '+(r.accessible?'성공':'제한/오류')+' | '+(r.capturedPlaceCards??'-')+' | '+(r.accessible?(r.ownPlaceCardObserved?'관측('+r.ownCardOrderIfObserved+')':'관측 범위 내 미발견'):'판단 불가')+' | '+(r.initialCards||[]).slice(0,3).map(x=>x.name.replace(/\s+/g,' ').slice(0,25)).join(', ')+' |'),
  '',
  '## 디자이너 공개 예약 카드',
  '',
  '| 디자이너 | 접근 | 최근 스타일링 표시 | 리뷰 표시 | 스타일 정보 | 재방문 표시 |',
  '|---|---|---:|---:|---:|---|',
  ...result.stylists.map(r=>'| '+r.name+' | '+(r.accessible?'성공':'제한/오류')+' | '+(r.recentStylingDisplay??'-')+' | '+(r.reviewDisplay??'-')+' | '+(r.styleInfoCount??'-')+' | '+(r.returnVisitBadge?'표시':'미표시/미확인')+' |'),
  '',
  '접근 제한 및 오류: '+(errors.length?errors.join(', '):'관측되지 않음'),
  '',
  '검사 대상은 공개 페이지뿐입니다. 자동 로그인, 보안 확인 우회, 리뷰 작성, 예약 진행, 업체정보 수정은 수행하지 않았습니다.'
];
writeFileSync(output+'/report.md',rows.join('\n')+'\n');
writeFileSync(output+'/search-cards.csv',['keyword,accessible,own_place_observed,captured_cards',...result.searches.map(r=>[JSON.stringify(r.keyword),r.accessible,r.ownPlaceCardObserved??'',r.capturedPlaceCards??''].join(','))].join('\n')+'\n');
console.log('NAVER_MONITOR_RESULT '+JSON.stringify({checked:result.searches.length+result.stylists.length,failed:errors.length}));
