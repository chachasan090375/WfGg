import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const ROOT=process.env.WFGG_PREVIEW||'https://wfgg.pages.dev';
const browser=await chromium.launch({headless:true});
try{
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,locale:'fr-FR'});
  const page=await context.newPage();
  page.on('pageerror',err=>console.log('PAGEERROR',err.message));
  await page.goto(`${ROOT}/?login_field_debug=${Date.now()}`,{waitUntil:'domcontentloaded',timeout:60000});
  await page.locator('#authView').waitFor({state:'visible',timeout:15000});
  const input=page.locator('#authCode');
  await input.waitFor({state:'visible',timeout:10000});
  const info=await input.evaluate(el=>{
    const r=el.getBoundingClientRect();
    const top=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
    const cs=getComputedStyle(el);
    return {disabled:el.disabled,readOnly:el.readOnly,pointerEvents:cs.pointerEvents,topId:top?.id||'',topTag:top?.tagName||'',readyState:document.readyState};
  });
  console.log('LOGIN_FIELD_INFO',JSON.stringify(info));
  assert.equal(info.disabled,false);
  assert.equal(info.readOnly,false);
  assert.equal(info.pointerEvents,'auto');
  assert.equal(info.topId,'authCode');
  await input.tap({timeout:5000});
  await page.waitForTimeout(150);
  assert.equal(await page.evaluate(()=>document.activeElement?.id||''),'authCode');
  console.log('WFGG_LOGIN_FIELD_INTERACTION=PASS');
  await context.close();
} finally {await browser.close();}
