import { chromium } from 'playwright';
import fs from 'node:fs';
const out='lumi-public-render';
fs.mkdirSync(out,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const context=await browser.newContext({viewport:{width:390,height:844},locale:'ko-KR',timezoneId:'Asia/Seoul'});
const page=await context.newPage();
const audit={target:'https://chatbot-service.lumi.ing/',readOnly:true,createdAt:new Date().toISOString(),screens:[],warnings:[]};
async function capture(label){
 const text=(await page.locator('body').innerText({timeout:8000}).catch(()=>'' )).slice(0,4000);
 const elements=await page.evaluate(()=>({
  inputs:[...document.querySelectorAll('input')].slice(0,30).map(e=>({type:e.type,placeholder:e.getAttribute('placeholder'),name:e.getAttribute('name')?.slice(0,40),autocomplete:e.getAttribute('autocomplete')})),
  buttons:[...document.querySelectorAll('button,[role="button"]')].slice(0,40).map(e=>({text:e.innerText?.trim().slice(0,70),ariaLabel:e.getAttribute('aria-label')?.slice(0,70)})),
  links:[...document.querySelectorAll('a[href]')].slice(0,25).map(e=>({text:e.innerText?.trim().slice(0,50),external:!!e.href&&!e.href.startsWith(location.origin)})),
  appRoot:!!document.querySelector('#root')
 })).catch(()=>({}));
 await page.screenshot({path:out+'/'+label+'.png',fullPage:false}).catch(()=>{});
 const entry={label,urlHost:new URL(page.url()).host,title:await page.title().catch(()=>''),bodyExcerpt:text,elements};
 audit.screens.push(entry);
 console.log('LUMI_PUBLIC_SCREEN '+JSON.stringify(entry));
}
try{
 const res=await page.goto(audit.target,{waitUntil:'domcontentloaded',timeout:30000});
 audit.status=res?.status()??null;
 await page.waitForTimeout(3500);
 await capture('01-open');
 // Public UI only. Do not fill forms, submit login, contact APIs, or bypass authentication.
 const login=page.getByRole('button',{name:/로그인|log\s*in|sign\s*in/i}).first();
 if(await login.count() && await login.isVisible()){
   await login.click({timeout:5000});
   await page.waitForTimeout(900);
   await capture('02-public-login-dialog');
 } else audit.warnings.push('No immediately visible login button. Public initial screen captured only.');
}catch(e){audit.warnings.push(String(e).slice(0,250));}
finally{
 fs.writeFileSync(out+'/result.json',JSON.stringify(audit,null,2));
 console.log('LUMI_PUBLIC_RESULT '+JSON.stringify({status:audit.status,screens:audit.screens.length,warnings:audit.warnings}));
 await browser.close();
}