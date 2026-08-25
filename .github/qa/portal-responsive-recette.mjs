import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const ROOT = process.env.WFGG_PREVIEW || 'https://portal-responsive-v17.wfgg.pages.dev';
const TRAIN = 'wfgg-train.chachasan090375.workers.dev';
const viewports = [
  {width:360,height:800,name:'360x800'},
  {width:390,height:844,name:'390x844'},
  {width:412,height:915,name:'412x915'}
];

const today = new Date();
const iso = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const plus = n => { const d=new Date(today); d.setDate(d.getDate()+n); return iso(d); };

const roster = [
  {id:'u5',pseudo:'QA R5',rank:'R5',active:true},
  {id:'u4',pseudo:'QA Mobile R4 au nom volontairement assez long',rank:'R4',active:true},
  {id:'u3',pseudo:'QA R3 avec pseudo long',rank:'R3',active:true},
  {id:'u2',pseudo:'QA R2',rank:'R2',active:true},
  {id:'u1',pseudo:'QA R1',rank:'R1',active:true}
];

function mePayload(){
  return {
    user:{id:'u4',player_name:'QA Mobile R4',display_name:'QA Mobile R4',language:'fr',profile_completed:true,avatar_url:null},
    membership:{rank:'R4',officer_title:'WARLORD'},
    alliance:{name:'WfGg',server:'992',logo_url:null},
    system:{role:'MEMBER'},
    permissions:{can_admin_members:true},
    portal_settings:{welcome_text:'Choisissez votre espace WfGg.',guides_title:'Guides',guides_url:'/guides/',train_title:'Train',train_url:'/train/'}
  };
}

function trainSnapshot(){
  return {
    ok:true,
    me:{id:'u4',pseudo:'QA Mobile R4',rank:'R4',active:true},
    roster,
    state:{manualHistory:{cutoff:'2026-08-16',counts:{driver:{},vip:{}},links:{}}},
    schedule:[
      {date:plus(1),driverId:'u4',driverClass:'officer',vipId:'u3'},
      {date:plus(2),driverId:'u3',driverClass:'r3',vipId:'u4'},
      {date:plus(3),driverId:'u5',driverClass:'officer',vipId:'u2'}
    ]
  };
}

function analytics(){
  return {
    ok:true,
    summary:{actions7:18,actions30:74,activeMembers:5},
    activityByActor:[
      {id:'u4',pseudo:'QA Mobile R4 au nom volontairement assez long',rank:'R4',total:31,players:9,exchanges:8,members:7,settings:7},
      {id:'u3',pseudo:'QA R3 avec pseudo long',rank:'R3',total:22,players:8,exchanges:10,members:2,settings:2}
    ],
    historyActive:roster.map((u,i)=>({id:u.id,driver:i,vip:i+1,driverLast:plus(-i-1),vipLast:plus(-i-2)}))
  };
}

async function mockPortal(page){
  await page.route('**/api/**', async route=>{
    const req=route.request();
    const url=new URL(req.url());
    const p=url.pathname;
    const ok=(body,status=200)=>route.fulfill({status,contentType:'application/json; charset=utf-8',body:JSON.stringify(body)});

    if(url.hostname===TRAIN){
      if(p==='/api/snapshot') return ok(trainSnapshot());
      if(p==='/api/admin/analytics') return ok(analytics());
      return ok({ok:true});
    }

    if(p==='/api/me') return ok(mePayload());
    if(p==='/api/me/sessions') return ok({sessions:[
      {current:true,user_agent:'Mozilla/5.0 (Linux; Android 16; très longue chaîne de test responsive) AppleWebKit/537.36 Chrome/151.0.0.0 Mobile Safari/537.36',last_seen_at:new Date().toISOString()},
      {current:false,user_agent:'Mozilla/5.0 (Linux; Android 10; second appareil avec une description volontairement longue)',last_seen_at:new Date(Date.now()-86400000).toISOString()}
    ]});
    if(p==='/api/admin/members') return ok({members:roster.map((u,i)=>({id:u.id,player_name:u.pseudo,display_name:u.pseudo,rank:u.rank,active:true,last_login_at:new Date(Date.now()-i*3600000).toISOString(),officer_title:u.rank==='R4'?'WARLORD':null,system_role:null}))});
    if(p==='/api/logout') return ok({ok:true});
    return ok({ok:true,...mePayload()});
  });
}

async function assertNoHorizontalOverflow(page,label){
  const metrics = await page.evaluate(()=>{
    const root=document.scrollingElement||document.documentElement;
    const visible = sel => {
      const el=document.querySelector(sel);
      if(!el) return null;
      const cs=getComputedStyle(el);
      if(cs.display==='none'||cs.visibility==='hidden') return null;
      const r=el.getBoundingClientRect();
      return {sel,left:r.left,right:r.right,width:r.width};
    };
    return {
      innerWidth:window.innerWidth,
      scrollWidth:root.scrollWidth,
      bodyScrollWidth:document.body.scrollWidth,
      app:visible('#app'),
      portal:visible('#portalView'),
      settings:visible('.settings-panel'),
      members:visible('.members-page'),
      modal:visible('.modal-sheet')
    };
  });
  assert.ok(metrics.scrollWidth<=metrics.innerWidth+1,`${label}: root overflow ${JSON.stringify(metrics)}`);
  assert.ok(metrics.bodyScrollWidth<=metrics.innerWidth+1,`${label}: body overflow ${JSON.stringify(metrics)}`);
  for(const box of [metrics.app,metrics.portal,metrics.settings,metrics.members,metrics.modal].filter(Boolean)){
    assert.ok(box.left>=-1 && box.right<=metrics.innerWidth+1,`${label}: ${box.sel} outside viewport ${JSON.stringify(metrics)}`);
  }
  await page.evaluate(()=>window.scrollTo({left:99999,top:window.scrollY,behavior:'auto'}));
  await page.waitForTimeout(30);
  const x=await page.evaluate(()=>window.scrollX);
  assert.ok(Math.abs(x)<=1,`${label}: horizontal scroll possible x=${x}`);
}

async function authenticatedPage(browser,vp){
  const context=await browser.newContext({viewport:{width:vp.width,height:vp.height},isMobile:true,hasTouch:true,locale:'fr-FR'});
  await context.addInitScript(()=>{
    localStorage.setItem('wfgg_portal_session','qa-mobile-token');
    localStorage.setItem('wfgg_portal_language','fr');
    localStorage.setItem('wfgg_portal_language_source','profile');
  });
  const page=await context.newPage();
  await mockPortal(page);
  await page.goto(`${ROOT}/?responsive_qa=${Date.now()}`,{waitUntil:'domcontentloaded',timeout:60000});
  await page.locator('#portalView').waitFor({state:'visible',timeout:30000});
  return {context,page};
}

const browser=await chromium.launch({headless:true});
try{
  for(const vp of viewports){
    const authContext=await browser.newContext({viewport:{width:vp.width,height:vp.height},isMobile:true,hasTouch:true,locale:'fr-FR'});
    const authPage=await authContext.newPage();
    await authPage.goto(`${ROOT}/?responsive_auth=${Date.now()}`,{waitUntil:'domcontentloaded',timeout:60000});
    await authPage.locator('#authView').waitFor({state:'visible',timeout:30000});
    await assertNoHorizontalOverflow(authPage,`${vp.name} auth`);
    await authContext.close();

    const {context,page}=await authenticatedPage(browser,vp);
    await assertNoHorizontalOverflow(page,`${vp.name} accueil`);

    await page.locator('#profileChip').click();
    await page.locator('[data-action="profile"]').click();
    await page.locator('#settingsOverlay').waitFor({state:'visible'});
    await page.locator('#profileTrainRotationHost').waitFor({state:'visible'});
    await assertNoHorizontalOverflow(page,`${vp.name} profil`);

    await page.locator('#openSessionHistory').click();
    await page.locator('#sessionList').waitFor({state:'visible'});
    await assertNoHorizontalOverflow(page,`${vp.name} historique connexions`);
    await page.locator('#backProfileSettings').click();

    for(const tab of ['alliance','members','statistics','application','rights']){
      await page.locator(`[data-settings-tab="${tab}"]`).click();
      await page.waitForTimeout(tab==='statistics'?180:60);
      await assertNoHorizontalOverflow(page,`${vp.name} paramètres/${tab}`);
    }

    await page.locator('[data-settings-tab="members"]').click();
    await page.locator('#openMembersButton').click();
    await page.locator('#membersView').waitFor({state:'visible'});
    await page.locator('.member-row').first().waitFor({state:'visible'});
    await assertNoHorizontalOverflow(page,`${vp.name} joueurs`);

    await page.locator('[data-action="add-member"]').click();
    await page.locator('.modal-sheet').waitFor({state:'visible'});
    await assertNoHorizontalOverflow(page,`${vp.name} modal joueur`);
    await context.close();

    console.log(`PASS ${vp.name} responsive portal views`);
  }
  console.log('WFGG_PORTAL_RESPONSIVE_RECETTE=PASS');
} finally {
  await browser.close();
}
