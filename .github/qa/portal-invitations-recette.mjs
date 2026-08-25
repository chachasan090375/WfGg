import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const ROOT=process.env.WFGG_PREVIEW||'https://portal-invitations-v18.wfgg.pages.dev';
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
  await page.locator('#inviteCsvInput').setInputFiles({
    name:'qa-members.csv',
    mimeType:'text/csv',
    buffer:Buffer.from('Pseudo;Rang;Code personnel\nAlpha R4;R4;111111\nBravo R3;R3;222222\nCharlie R5;R5;333333\n','utf8')
  });
  await page.locator('#inviteMessage').waitFor({state:'visible'});
  assert.match(await page.locator('#inviteFileMeta').textContent(),/3 joueurs chargés/);

  const r4=await page.locator('#inviteMessage').inputValue();
  assert.ok(r4.includes('Alpha R4'));
  assert.ok(r4.includes('https://wfgg.pages.dev/'));
  assert.ok(r4.includes('111111'));
  for(const name of ['Metatouk','Ogie Ogilthorpe 7','ValFada','Shockwave XY','Sab93fr','εlα ツ','cat 49','Flawene']) assert.ok(r4.includes(name),`missing thanks ${name}`);
  for(const name of ['El Tonton','Le Ced83','SnooPsy']) assert.ok(!r4.includes(name),`excluded thanks leaked ${name}`);
  assert.ok(r4.includes('Ton statut de R4'));
  assert.ok(r4.includes("fonctions d'administration réservées au bureau"));
  assert.ok(r4.includes('Joueurs & accès'));
  assert.ok(r4.includes('réinitialisation des codes personnels'));

  await page.locator('#inviteToggleSent').click();
  const storage1=await page.evaluate(()=>JSON.stringify({...localStorage}));
  assert.ok(!storage1.includes('111111'),'personal code persisted in localStorage');
  assert.ok(!storage1.includes('222222'),'personal code persisted in localStorage');
  assert.ok(!storage1.includes('333333'),'personal code persisted in localStorage');

  await page.locator('#inviteNext').click();
  const r3=await page.locator('#inviteMessage').inputValue();
  assert.ok(r3.includes('Bravo R3'));
  assert.ok(r3.includes('222222'));
  assert.ok(!r3.includes('Ton statut de R3'));
  assert.ok(!r3.includes("fonctions d'administration réservées au bureau"));

  await page.locator('#inviteNext').click();
  const r5=await page.locator('#inviteMessage').inputValue();
  assert.ok(r5.includes('Charlie R5'));
  assert.ok(r5.includes('333333'));
  assert.ok(r5.includes('Ton statut de R5'));
  assert.ok(r5.includes('accès de leadership'));

  const metrics=await page.evaluate(()=>({innerWidth,scrollWidth:(document.scrollingElement||document.documentElement).scrollWidth}));
  assert.ok(metrics.scrollWidth<=metrics.innerWidth+1,`mobile overflow ${JSON.stringify(metrics)}`);

  console.log('WFGG_PORTAL_INVITATIONS_RECETTE=PASS');
  await context.close();
} finally {await browser.close();}
