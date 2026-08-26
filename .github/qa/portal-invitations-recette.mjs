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

  await page.waitForFunction(()=>document.querySelector('#inviteMessage')?.dataset.lastwarAlliance==='v2');
  const safe=await page.evaluate(()=>window.WFGG_LASTWAR_CHAT_SAFE_TEST);
  assert.equal(safe.MODE,'alliance-notice-v2');
  assert.equal(safe.PORTAL_URL,'https://wfgg.pages.dev/');
  assert.ok(safe.ALLIANCE_NOTICE.includes('https://wfgg.pages.dev/'));
  assert.match(safe.ALLIANCE_NOTICE,/Nouveau portail WfGg/i);
  assert.match(safe.ALLIANCE_NOTICE,/bureau R4\/R5/i);
  for(const name of ['Metatouk','Ogie Ogilthorpe 7','ValFada','Shockwave XY','Sab93fr','εlο ツ','cat 49','Flawene','El Tonton','Le Ced83','SnooPsy']) assert.ok(!safe.ALLIANCE_NOTICE.includes(name),`named thanks leaked into alliance notification ${name}`);
  for(const code of ['111111','222222','333333']) assert.ok(!safe.ALLIANCE_NOTICE.includes(code),'personal code leaked into alliance notification');

  const allianceUi=page.locator('#inviteAllianceNotice');
  await allianceUi.waitFor({state:'visible'});
  assert.equal(await allianceUi.inputValue(),safe.ALLIANCE_NOTICE);
  assert.ok(await page.locator('#inviteAllianceCopy').isVisible());
  assert.match(await page.locator('#inviteAllianceCopy').innerText(),/notification d’alliance/i);

  const r4=await page.evaluate(()=>window.WFGG_LASTWAR_CHAT_SAFE_TEST.buildMessage('Alpha R4','R4','111111'));
  assert.ok(r4.includes('Alpha R4'));
  assert.ok(!r4.includes('wfgg.pages.dev'),'portal domain leaked into private message');
  assert.ok(!r4.includes('pages . dev'),'broken portal domain leaked into private message');
  assert.ok(!r4.includes('https://'),'URL scheme leaked into private message');
  assert.match(r4,/notifications d’alliance/i);
  assert.ok(r4.includes('Inter-Saison'));
  assert.ok(r4.includes('111111'));
  assert.match(r4,/bureau R4\/R5/i);
  for(const name of ['Metatouk','Ogie Ogilthorpe 7','ValFada','Shockwave XY','Sab93fr','εlο ツ','εlα ツ','εlo ツ','cat 49','Flawene','El Tonton','Le Ced83','SnooPsy']) assert.ok(!r4.includes(name),`named thanks leaked ${name}`);
  assert.ok(r4.includes('Ton rang R4'));
  assert.ok(r4.includes('Joueurs & accès'));
  assert.ok(r4.includes('réinitialisation des codes'));
  const emoji=/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;
  assert.ok(emoji.test(r4),'emoji expected in private invitation');

  const variants=await page.evaluate(()=>[
    ['Delta','R3','444444'],['Echo','R3','555555'],['Foxtrot','R3','666666'],['Golf','R3','777777'],['Hotel','R3','888888']
  ].map(([p,r,c])=>window.WFGG_LASTWAR_CHAT_SAFE_TEST.buildMessage(p,r,c)));
  const normalized=variants.map((m,i)=>m.replace(['Delta','Echo','Foxtrot','Golf','Hotel'][i],'JOUEUR').replace(/\d{6}/g,'CODE'));
  assert.ok(new Set(normalized).size>=4,'player messages are not varied enough');

  const displayed=await page.locator('#inviteMessage').inputValue();
  assert.equal(displayed,r4,'the UI must expose one complete private message');
  assert.equal(await page.locator('[data-lastwar-safe-controls]').count(),0,'old multi-block controls must be absent');
  assert.equal(await page.locator('#inviteCopySent').isDisabled(),false,'copy + mark sent must work directly on the private message');
  const meta=await page.locator('[data-lastwar-alliance-meta]').textContent();
  assert.match(meta,/Message privé/);
  assert.match(meta,/avec emoji/);
  assert.match(meta,/notifications d’alliance/);

  await page.locator('#inviteToggleSent').click();
  const storage1=await page.evaluate(()=>JSON.stringify({...localStorage}));
  assert.ok(!storage1.includes('111111'),'personal code persisted in localStorage');
  assert.ok(!storage1.includes('222222'),'personal code persisted in localStorage');
  assert.ok(!storage1.includes('333333'),'personal code persisted in localStorage');

  await page.locator('#inviteNext').click();
  await page.waitForFunction(()=>document.querySelector('#inviteMessage')?.dataset.lastwarAlliance==='v2');
  const r3=await page.locator('#inviteMessage').inputValue();
  assert.ok(r3.includes('Bravo R3'));
  assert.ok(r3.includes('222222'));
  assert.match(r3,/notifications d’alliance/i);
  assert.ok(!r3.includes('wfgg.pages.dev'));
  assert.ok(!r3.includes('pages . dev'));
  assert.ok(!r3.includes('Ton rang R3'));
  assert.ok(!r3.includes('outils du bureau'));
  assert.ok(emoji.test(r3));

  await page.locator('#inviteNext').click();
  await page.waitForFunction(()=>document.querySelector('#inviteMessage')?.dataset.lastwarAlliance==='v2');
  const r5=await page.locator('#inviteMessage').inputValue();
  assert.ok(r5.includes('Charlie R5'));
  assert.ok(r5.includes('333333'));
  assert.ok(r5.includes('Ton rang R5'));
  assert.ok(r5.includes('leadership'));
  assert.match(r5,/notifications d’alliance/i);
  assert.ok(!r5.includes('wfgg.pages.dev'));
  assert.ok(!r5.includes('pages . dev'));
  assert.ok(emoji.test(r5));

  const metrics=await page.evaluate(()=>({innerWidth,scrollWidth:(document.scrollingElement||document.documentElement).scrollWidth}));
  assert.ok(metrics.scrollWidth<=metrics.innerWidth+1,`mobile overflow ${JSON.stringify(metrics)}`);

  console.log('WFGG_PORTAL_INVITATIONS_XLSX_RECETTE=PASS');
  await context.close();
} finally {await browser.close();}
