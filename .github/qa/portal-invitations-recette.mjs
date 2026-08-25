import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const ROOT=process.env.WFGG_PREVIEW||'http://127.0.0.1:4173';
const XLSX_FIXTURE=process.env.WFGG_XLSX_FIXTURE||'/tmp/qa-members.xlsx';
const me={
  user:{id:'qa-r4',player_name:'QA R4',display_name:'QA R4',language:'fr',profile_completed:true,avatar_url:null},
  membership:{rank:'R4',officer_title:'WARLORD'},
  alliance:{name:'WfGg',server:'992',logo_url:null},
  system:{role:'MEMBER'},
  permissions:{can_admin_members:true},
  portal_settings:{welcome_text:'Choisissez votre espace WfGg.',guides_title:'Guides',guides_url:'/guides/',train_title:'Train',train_url:'/train/'}
};
const browser=await chromium.launch({headless:true});
try{
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,locale:'fr-FR'});
  await context.addInitScript(()=>{
    localStorage.setItem('wfgg_portal_session','qa-invitations-token');
    localStorage.setItem('wfgg_portal_language','fr');
    localStorage.setItem('wfgg_portal_language_source','profile');
  });
  const page=await context.newPage();
  await page.route('**/api/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(me)}));
  await page.goto(`${ROOT}/?qa_invites=${Date.now()}`,{waitUntil:'domcontentloaded',timeout:60000});
  await page.locator('#portalView').waitFor({state:'visible',timeout:30000});
  await page.locator('[data-action="settings"]').click();
  await page.locator('#settingsOverlay').waitFor({state:'visible'});
  const tab=page.locator('[data-invitations-tab]');
  await tab.waitFor({state:'visible',timeout:10000});
  await tab.click();

  const input=page.locator('#inviteCsvInput');
  await input.waitFor({state:'attached'});
  await page.waitForFunction(()=>document.querySelector('#inviteCsvInput')?.dataset.xlsxSupport==='v1');
  assert.equal(await input.getAttribute('accept'),null,'Android picker must not filter files by MIME type');
  assert.equal(await input.getAttribute('data-android-filefix'),'v1','Android picker guard missing');
  assert.equal(await input.getAttribute('data-xlsx-support'),'v1','XLSX local parser guard missing');
  assert.match(await page.locator('.invite-file-button').innerText(),/CSV \/ Excel/);

  await input.setInputFiles(XLSX_FIXTURE);
  await page.locator('#inviteMessage').waitFor({state:'visible',timeout:15000});
  assert.match(await page.locator('#inviteFileMeta').textContent(),/3 joueurs chargés/);
  assert.match(await page.locator('#inviteFileMeta').textContent(),/qa-members\.xlsx/);
  assert.ok(await page.locator('#inviteError').evaluate(el=>el.classList.contains('hidden')),'XLSX import displayed an error');

  await page.waitForFunction(()=>document.querySelector('#inviteMessage')?.dataset.lastwarSafe==='v1');
  const safe=await page.evaluate(()=>window.WFGG_LASTWAR_CHAT_SAFE_TEST);
  assert.equal(safe.MAX_CHARS,240);
  const r4blocks=await page.evaluate(()=>window.WFGG_LASTWAR_CHAT_SAFE_TEST.buildBlocks('Alpha R4','R4','111111'));
  assert.ok(r4blocks.length>=4);
  assert.ok(r4blocks.every(x=>x.length<=240),JSON.stringify(r4blocks.map(x=>x.length)));
  const r4=r4blocks.join('\n');
  assert.ok(r4.includes('Alpha R4'));
  assert.ok(r4.includes('wfgg.pages.dev'));
  assert.ok(!r4.includes('https://'),'Last War mode must avoid full URL scheme');
  assert.ok(r4.includes("investissement durant toute l'Inter-Saison"));
  assert.ok(r4.includes('111111'));
  for(const name of ['Metatouk','Ogie Ogilthorpe 7','ValFada','Shockwave XY','Sab93fr','εlο ツ','cat 49','Flawene']) assert.ok(r4.includes(name),`missing thanks ${name}`);
  assert.ok(!r4.includes('εlα ツ'),'old alpha alias leaked into invitation');
  assert.ok(!r4.includes('εlo ツ'),'Latin-o alias leaked into invitation');
  for(const name of ['El Tonton','Le Ced83','SnooPsy']) assert.ok(!r4.includes(name),`excluded thanks leaked ${name}`);
  assert.ok(r4.includes('Ton rang R4'));
  assert.ok(r4.includes('Joueurs & accès'));
  assert.ok(r4.includes('réinitialisation des codes'));
  const emoji=/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;
  assert.ok(r4blocks.every(x=>!emoji.test(x)),'Unicode emoji leaked into Last War blocks');

  const first=await page.locator('#inviteMessage').inputValue();
  assert.ok(first.length<=240);
  assert.ok(first.includes('Alpha R4'));
  assert.equal(await page.locator('#inviteCopySent').isDisabled(),true,'mark-sent copy must wait for final block');
  const meta=await page.locator('[data-lastwar-safe-meta]').textContent();
  assert.match(meta,/Bloc 1\//);
  assert.match(meta,/sans emoji/);
  for(let i=1;i<r4blocks.length;i++)await page.locator('[data-lastwar-safe-next]').click();
  assert.equal(await page.locator('#inviteCopySent').isDisabled(),false,'final block must allow copy + mark sent');
  assert.match(await page.locator('#inviteMessage').inputValue(),/111111/);

  await page.locator('#inviteToggleSent').click();
  const storage1=await page.evaluate(()=>JSON.stringify({...localStorage}));
  assert.ok(!storage1.includes('111111'),'personal code persisted in localStorage');
  assert.ok(!storage1.includes('222222'),'personal code persisted in localStorage');
  assert.ok(!storage1.includes('333333'),'personal code persisted in localStorage');

  await page.locator('#inviteNext').click();
  await page.waitForFunction(()=>document.querySelector('#inviteMessage')?.dataset.lastwarSafe==='v1');
  const r3blocks=await page.evaluate(()=>window.WFGG_LASTWAR_CHAT_SAFE_TEST.buildBlocks('Bravo R3','R3','222222'));
  const r3=r3blocks.join('\n');
  assert.ok(r3blocks.every(x=>x.length<=240));
  assert.ok(r3.includes('Bravo R3'));
  assert.ok(r3.includes('222222'));
  assert.ok(!r3.includes('Ton rang R3'));
  assert.ok(!r3.includes('outils du bureau'));

  await page.locator('#inviteNext').click();
  await page.waitForFunction(()=>document.querySelector('#inviteMessage')?.dataset.lastwarSafe==='v1');
  const r5blocks=await page.evaluate(()=>window.WFGG_LASTWAR_CHAT_SAFE_TEST.buildBlocks('Charlie R5','R5','333333'));
  const r5=r5blocks.join('\n');
  assert.ok(r5blocks.every(x=>x.length<=240));
  assert.ok(r5.includes('Charlie R5'));
  assert.ok(r5.includes('333333'));
  assert.ok(r5.includes('Ton rang R5'));
  assert.ok(r5.includes('leadership R5'));

  const metrics=await page.evaluate(()=>({innerWidth,scrollWidth:(document.scrollingElement||document.documentElement).scrollWidth}));
  assert.ok(metrics.scrollWidth<=metrics.innerWidth+1,`mobile overflow ${JSON.stringify(metrics)}`);

  console.log('WFGG_PORTAL_INVITATIONS_XLSX_RECETTE=PASS');
  await context.close();
} finally {await browser.close();}
