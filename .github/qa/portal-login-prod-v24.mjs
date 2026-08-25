import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const browser=await chromium.launch({headless:true});
try{
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,locale:'fr-FR'});
  const page=await context.newPage();
  await page.goto(`https://wfgg.pages.dev/?login_prod_v24=${Date.now()}`,{waitUntil:'domcontentloaded',timeout:60000});
  await page.locator('#authView').waitFor({state:'visible',timeout:15000});
  const input=page.locator('#authCode');
  await input.waitFor({state:'visible'});
  await page.waitForFunction(()=>document.querySelector('#authCode')?.dataset.mobileAuthGuard==='v1');
  const hit=await input.evaluate(el=>{const r=el.getBoundingClientRect();const top=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return {topId:top?.id||'',disabled:el.disabled,readOnly:el.readOnly,guard:el.dataset.mobileAuthGuard||'',readyState:document.readyState};});
  console.log('PROD_LOGIN_INFO',JSON.stringify(hit));
  assert.equal(hit.topId,'authCode');
  assert.equal(hit.disabled,false);
  assert.equal(hit.readOnly,false);
  assert.equal(hit.guard,'v1');
  await input.tap({timeout:5000});
  assert.equal(await page.evaluate(()=>document.activeElement?.id||''),'authCode');
  await page.keyboard.type('123456');
  assert.equal(await input.inputValue(),'123456');
  console.log('WFGG_PRODUCTION_MOBILE_LOGIN_V24=PASS');
  await context.close();
} finally {await browser.close();}
