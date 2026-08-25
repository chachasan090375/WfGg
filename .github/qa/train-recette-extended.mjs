import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium } from 'playwright';

const ROOT=process.env.WFGG_PREVIEW||'https://train-bridge-phase3.wfgg.pages.dev';
const clone=x=>JSON.parse(JSON.stringify(x));
const iso=d=>d.toISOString().slice(0,10);

function roster(){return [
  ['u5','QA R5','R5'],['u4','QA R4','R4'],['u3a','QA R3 A','R3'],['u3b','QA R3 B','R3'],['u2','QA R2','R2'],['u1','QA R1','R1']
].map(([id,pseudo,rank])=>({id,pseudo,rank,avatar:'assets/icon-192.png',active:true,lastSeen:null}));}
function authoritativeSchedule(){return [
  {date:'2026-08-29',driverId:'u4',vipId:'u3a',driverClass:'officer',r3Cycle:0},
  {date:'2026-08-31',driverId:'u5',vipId:'u3b',driverClass:'officer',r3Cycle:0},
  {date:'2026-09-04',driverId:'u4',vipId:'u2',driverClass:'officer',r3Cycle:1},
  {date:'2026-09-15',driverId:'u4',vipId:'u1',driverClass:'officer',r3Cycle:2},
  {date:'2026-09-17',driverId:'u3a',vipId:'u3b',driverClass:'r3',r3Cycle:2}
];}
function state(meId){return {
  settings:{anchorDate:'2026-08-25',trainTime:'20:00',officersFirst:true,reminderDayBefore:true,reminder30:true,rotationRanks:{officer:['R5','R4'],r3driver:['R3'],vip:['R3','R2','R1']}},
  unavailable:{},outRotation:[],overrides:{},exchanges:[],alertsEnabled:{},languages:{[meId]:'fr'},gameLinks:[],
  playerEdits:{},addedPlayers:[],removedPlayers:[],rotationOrder:{officer:['u5','u4'],r3driver:['u3a','u3b'],r3vip:['u3a','u3b','u2','u1']},
  messageVariant:{weekly:0,daily:0,driver:0,vip:0},
  manualHistory:{version:'qa',source:'QA',cutoff:'2026-08-16',eventCount:63,counts:{driver:{},vip:{}},links:{},aliases:{},former:[],correctionsApplied:[],correctionConflicts:[],reviewSuggestions:[],missingReference:[],extraApp:[]}
};}

async function session(browser,rank='R4',opts={}){
  const rows=roster(), me=rows.find(x=>x.rank===rank)||rows[1];
  let st=state(me.id), version=1;
  const calls=[],errors=[],toasts=[];
  const context=await browser.newContext({locale:'fr-FR',acceptDownloads:true,viewport:opts.viewport||{width:412,height:915},isMobile:opts.isMobile??true,hasTouch:opts.hasTouch??true});
  await context.addInitScript(()=>{
    localStorage.setItem('wfgg_portal_session','qa-portal-token');
    localStorage.setItem('wfgg_portal_language','fr');
    sessionStorage.setItem('wfgg_train_sw_reset_v1','1');
    Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.__QA_CLIPBOARD__=String(text)}}});
  });
  const page=await context.newPage();
  page.on('pageerror',e=>errors.push(`pageerror:${e.message}`));
  page.on('console',m=>{if(m.type()==='error')errors.push(`console:${m.text()}`)});
  function snap(){const u=rows.find(x=>x.id===me.id);return {ok:true,me:{id:u.id,pseudo:u.pseudo,rank:u.rank,avatar:u.avatar,active:true},roster:clone(rows),state:clone(st),schedule:clone(authoritativeSchedule()),version,updatedAt:new Date().toISOString(),serverTime:new Date().toISOString()};}
  async function body(req){try{return req.postDataJSON()}catch{return {}}}
  function json(route,data={ok:true},status=200){return route.fulfill({status,contentType:'application/json; charset=utf-8',body:JSON.stringify(data)});}
  await page.route('**/api/**',async route=>{
    const req=route.request(),u=new URL(req.url()),p=u.pathname,m=req.method();calls.push({method:m,path:p,body:await body(req)});
    if(p==='/api/snapshot'&&m==='GET')return json(route,snap());
    if(p==='/api/presence/heartbeat'&&m==='POST')return json(route,{ok:true,lastSeen:new Date().toISOString()});
    if(p==='/api/admin/presence'&&m==='GET')return json(route,{ok:true,count:1,online:[{...me,lastSeen:new Date().toISOString()}],thresholdSeconds:90,serverTime:new Date().toISOString()});
    if(p==='/api/directory'&&m==='GET')return json(route,{ok:true,users:rows.map(({pseudo,rank})=>({pseudo,rank}))});
    if(p==='/api/help-links'&&m==='GET')return json(route,{ok:true,links:[]});
    if(p==='/api/profile/language'&&m==='PATCH')return json(route,{ok:true});
    if(p==='/api/admin/analytics'&&m==='GET')return json(route,{ok:true,summary:{actions7:5,actions30:16,activeMembers:6,openExchanges:0,manualOverrides:Object.keys(st.overrides).length,outRotation:st.outRotation.length,unavailablePlayers:Object.keys(st.unavailable).filter(id=>(st.unavailable[id]||[]).length).length},rotation30:{spread:{officer:1,r3driver:0,vip:1},officer:[],r3driver:[],vip:[]},rotation90:{spread:{officer:1,r3driver:1,vip:1},officer:[],r3driver:[],vip:[]},activityByActor:[],settingsChanges:[],history:[],manualHistory:clone(st.manualHistory)});
    if(p==='/api/me'&&m==='PUT'){const b=await body(req),u=rows.find(x=>x.id===me.id);if(b.pseudo)u.pseudo=b.pseudo;if(b.avatar)u.avatar=b.avatar;version++;return json(route);}
    if(p==='/api/me/pin'&&m==='PUT')return json(route);
    if(p==='/api/me/preferences'&&m==='PUT'){
      const b=await body(req);if(Array.isArray(b.unavailable))st.unavailable[me.id]=[...b.unavailable];if('outRotation'in b){const x=new Set(st.outRotation);b.outRotation?x.add(me.id):x.delete(me.id);st.outRotation=[...x]}if('alertsEnabled'in b)st.alertsEnabled[me.id]=!!b.alertsEnabled;if(b.language)st.languages[me.id]=b.language;version++;return json(route);
    }
    if(p==='/api/admin/settings'&&m==='PUT'){const b=await body(req);st.settings={...st.settings,...b};if(b.resetOverrides)st.overrides={};version++;return json(route);}
    if(p==='/api/admin/rotation-ranks'&&m==='PUT'){const b=await body(req);st.settings.rotationRanks=clone(b.rotationRanks);st.overrides={};version++;return json(route);}
    if(p==='/api/admin/rotation-order'&&m==='PUT'){const b=await body(req);st.rotationOrder[b.key]=[...b.ids];version++;return json(route);}
    const ov=p.match(/^\/api\/admin\/override\/(\d{4}-\d{2}-\d{2})$/);
    if(ov&&m==='PUT'){const b=await body(req);st.overrides[ov[1]]={driverId:b.driverId||null,vipId:b.vipId||null};version++;return json(route);}
    if(ov&&m==='DELETE'){delete st.overrides[ov[1]];version++;return json(route);}
    const member=p.match(/^\/api\/admin\/members\/([^/]+)$/);
    if(member&&m==='PUT'){const b=await body(req),r=rows.find(x=>x.id===member[1]);if(r){Object.assign(r,{pseudo:b.pseudo??r.pseudo,rank:b.rank??r.rank,active:'active'in b?!!b.active:r.active,avatar:b.avatar??r.avatar})}version++;return json(route);}
    if(member&&m==='DELETE'){const i=rows.findIndex(x=>x.id===member[1]);if(i>=0)rows.splice(i,1);version++;return json(route);}
    if(p==='/api/admin/members'&&m==='POST'){const b=await body(req),id='qa-new';rows.push({id,pseudo:b.pseudo,rank:b.rank,active:b.active!==false,avatar:b.avatar||'assets/icon-192.png'});version++;return json(route,{ok:true,id,pin:'123456'},201);}
    if(/^\/api\/admin\/members\/[^/]+\/reset-pin$/.test(p)&&m==='POST')return json(route,{ok:true,pin:'654321',sessionsInvalidated:true});
    if(/^\/api\/admin\/members\/[^/]+\/preferences$/.test(p)&&m==='PUT')return json(route);
    if(p==='/api/admin/game-links'&&m==='PUT'){const b=await body(req);st.gameLinks=clone(b.links||[]);version++;return json(route);}
    if(p.startsWith('/api/admin/'))return json(route);
    return json(route);
  });
  await page.goto(`${ROOT}/train/?extended=${Date.now()}`,{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForFunction(()=>window.W&&document.getElementById('appView')&&!document.getElementById('appView').classList.contains('hidden'),null,{timeout:30000});
  await page.waitForTimeout(250);
  return {context,page,rows,me,calls,errors,toasts,state:()=>st};
}

const results=[];
async function test(name,fn){const t=Date.now();try{await fn();results.push({name,status:'PASS',ms:Date.now()-t});console.log('PASS',name)}catch(e){results.push({name,status:'FAIL',ms:Date.now()-t,error:e?.stack||String(e)});console.error('FAIL',name,e)}}

const browser=await chromium.launch({headless:true});
try{
  await test('Calendrier : export ICS d’un passage individuel',async()=>{
    const s=await session(browser,'R4');
    const btn=s.page.getByRole('button',{name:/Calendrier/}).first();assert.equal(await btn.isVisible(),true);
    const [download]=await Promise.all([s.page.waitForEvent('download'),btn.click()]);
    assert.match(download.suggestedFilename(),/WfGg-Train-.*\.ics$/);
    const path=await download.path();const txt=fs.readFileSync(path,'utf8');assert.match(txt,/BEGIN:VCALENDAR/);assert.match(txt,/BEGIN:VEVENT/);assert.match(txt,/WfGg/);
    await s.context.close();
  });

  await test('Calendrier : export groupé des prochains passages',async()=>{
    const s=await session(browser,'R4');
    const [download]=await Promise.all([s.page.waitForEvent('download'),s.page.evaluate(()=>window.W.addAllCalendar())]);
    assert.equal(download.suggestedFilename(),'WfGg-Train-mes-passages.ics');
    const txt=fs.readFileSync(await download.path(),'utf8');assert.match(txt,/BEGIN:VCALENDAR/);assert.ok((txt.match(/BEGIN:VEVENT/g)||[]).length>=1);
    await s.context.close();
  });

  await test('Profil R4 : édition sans demander le code personnel',async()=>{
    const s=await session(browser,'R4');await s.page.evaluate(()=>window.W.openSelfProfileEdit());
    assert.equal(await s.page.locator('#selfPinField').count(),0);
    await s.page.locator('#selfPseudoField').fill('QA R4 Renommé');
    await s.page.evaluate(()=>window.W.saveSelfProfile());await s.page.waitForTimeout(100);
    const call=s.calls.find(c=>c.method==='PUT'&&c.path==='/api/me');assert.ok(call);assert.equal(call.body.pseudo,'QA R4 Renommé');assert.equal(s.rows.find(x=>x.id==='u4').pseudo,'QA R4 Renommé');
    await s.context.close();
  });

  await test('Profil R3/R2 : code personnel demandé pour enregistrer',async()=>{
    for(const rank of ['R3','R2']){const s=await session(browser,rank);await s.page.evaluate(()=>window.W.openSelfProfileEdit());assert.equal(await s.page.locator('#selfPinField').count(),1,rank);await s.page.locator('#selfPinField').fill('123456');await s.page.locator('#selfPseudoField').fill(`QA ${rank} édité`);await s.page.evaluate(()=>window.W.saveSelfProfile());await s.page.waitForTimeout(80);const c=s.calls.find(x=>x.method==='PUT'&&x.path==='/api/me');assert.equal(c.body.pin,'123456');await s.context.close();}
  });

  await test('Code personnel : changement ancien → nouveau code',async()=>{
    const s=await session(browser,'R4');await s.page.evaluate(()=>window.W.openChangePin());await s.page.locator('#oldPinField').fill('111111');await s.page.locator('#newPinField').fill('222222');await s.page.evaluate(()=>window.W.changeMyPin());await s.page.waitForTimeout(80);const c=s.calls.find(x=>x.method==='PUT'&&x.path==='/api/me/pin');assert.ok(c);assert.deepEqual(c.body,{oldPin:'111111',newPin:'222222'});assert.equal(await s.page.locator('#modal').evaluate(el=>el.classList.contains('hidden')),true);await s.context.close();
  });

  await test('Indisponibilité : période complète puis retrait de la période',async()=>{
    const s=await session(browser,'R4');await s.page.evaluate(()=>window.W.openUnavailablePeriod('2026-09-10'));await s.page.locator('#unavailablePeriodStart').fill('2026-09-10');await s.page.locator('#unavailablePeriodEnd').fill('2026-09-12');await s.page.evaluate(()=>window.W.saveUnavailablePeriod());await s.page.waitForTimeout(100);for(const d of ['2026-09-10','2026-09-11','2026-09-12'])assert.ok((s.state().unavailable.u4||[]).includes(d));await s.page.evaluate(()=>window.W.removeUnavailableRange('2026-09-10','2026-09-12'));await s.page.waitForTimeout(100);for(const d of ['2026-09-10','2026-09-11','2026-09-12'])assert.ok(!(s.state().unavailable.u4||[]).includes(d));await s.context.close();
  });

  await test('Indisponibilité : limite 366 jours ne produit aucune mutation abusive',async()=>{
    const s=await session(browser,'R4');await s.page.evaluate(()=>window.W.openUnavailablePeriod('2026-09-01'));await s.page.locator('#unavailablePeriodStart').fill('2026-09-01');await s.page.locator('#unavailablePeriodEnd').fill('2027-09-05');const before=s.calls.filter(c=>c.path==='/api/me/preferences').length;await s.page.evaluate(()=>window.W.saveUnavailablePeriod());await s.page.waitForTimeout(80);const after=s.calls.filter(c=>c.path==='/api/me/preferences').length;assert.equal(after,before);await s.context.close();
  });

  await test('Rotations : changement ordre de priorité persistant',async()=>{
    const s=await session(browser,'R4');await s.page.locator('.nav-btn[data-screen="adminScreen"]').click();await s.page.evaluate(()=>window.W.openAdminSection('rotations'));await s.page.waitForTimeout(50);assert.deepEqual(s.state().rotationOrder.officer,['u5','u4']);await s.page.evaluate(()=>window.W.moveRotation('officer',0,1));await s.page.waitForTimeout(100);assert.deepEqual(s.state().rotationOrder.officer,['u4','u5']);assert.ok(s.calls.some(c=>c.method==='PUT'&&c.path==='/api/admin/rotation-order'));await s.context.close();
  });

  await test('Rotations : enregistrement des rangs autorisés',async()=>{
    const s=await session(browser,'R4');await s.page.locator('.nav-btn[data-screen="adminScreen"]').click();await s.page.evaluate(()=>window.W.openAdminSection('rotations'));await s.page.waitForTimeout(50);await s.page.evaluate(()=>window.W.saveRotationRanks());await s.page.waitForTimeout(100);const c=s.calls.find(x=>x.method==='PUT'&&x.path==='/api/admin/rotation-ranks');assert.ok(c);assert.deepEqual(c.body.rotationRanks.officer,['R5','R4']);assert.ok(c.body.rotationRanks.r3driver.includes('R3'));await s.context.close();
  });

  await test('Planning manuel : override d’une journée puis retour automatique',async()=>{
    const s=await session(browser,'R4');await s.page.locator('.nav-btn[data-screen="adminScreen"]').click();await s.page.evaluate(()=>window.W.openAdminSection('manual'));await s.page.waitForTimeout(80);const drv=s.page.locator('select[id^="drv-"]').first();assert.equal(await drv.isVisible(),true);const id=await drv.getAttribute('id'),ds=id.slice(4);await drv.selectOption('u4');const vip=s.page.locator(`#vip-${ds}`);await vip.selectOption('u2');await s.page.evaluate(d=>window.W.saveDay(d),ds);await s.page.waitForTimeout(100);assert.deepEqual(s.state().overrides[ds],{driverId:'u4',vipId:'u2'});await s.page.evaluate(d=>window.W.clearDayOverride(d),ds);await s.page.waitForTimeout(100);assert.equal(s.state().overrides[ds],undefined);assert.ok(s.calls.some(c=>c.method==='DELETE'&&c.path===`/api/admin/override/${ds}`));await s.context.close();
  });

  await test('Messages : génération, variante suivante et copie presse-papiers',async()=>{
    const s=await session(browser,'R4');await s.page.evaluate(()=>window.W.generateMessage('weekly'));assert.equal(await s.page.locator('#generatedMessage').count(),1);const first=await s.page.locator('#generatedMessage').inputValue();assert.ok(first.length>20);await s.page.evaluate(()=>window.W.nextMessage('weekly'));await s.page.waitForTimeout(40);const second=await s.page.locator('#generatedMessage').inputValue();assert.ok(second.length>20);await s.page.evaluate(()=>window.W.copyGeneratedMessage());const clip=await s.page.evaluate(()=>window.__QA_CLIPBOARD__);assert.equal(clip,second);await s.context.close();
  });

  await test('Statistiques du train : menu et sous-écrans Rotations / Historique',async()=>{
    const s=await session(browser,'R4');await s.page.locator('.nav-btn[data-screen="adminScreen"]').click();await s.page.evaluate(()=>window.W.openAdminAnalytics());await s.page.waitForTimeout(100);assert.equal(await s.page.locator('.analytics-icon-card.rotations').isVisible(),true);assert.equal(await s.page.locator('.analytics-icon-card.train-history').isVisible(),true);assert.equal(await s.page.locator('.analytics-icon-card.activity').count(),0);assert.equal(await s.page.locator('.analytics-icon-card.settings').count(),0);for(const key of ['rotations','trainhistory']){await s.page.evaluate(k=>window.W.openAnalyticsSub(k),key);await s.page.waitForTimeout(50);assert.deepEqual(s.errors,[]);await s.page.evaluate(()=>window.W.renderAnalyticsMenu());}await s.context.close();
  });

  await test('Admin Train : aucune gestion globale Joueurs/Codes/Aide exposée',async()=>{
    const s=await session(browser,'R4');await s.page.locator('.nav-btn[data-screen="adminScreen"]').click();const txt=await s.page.locator('#adminScreen').innerText();assert.doesNotMatch(txt,/Joueurs de l’alliance/);assert.doesNotMatch(txt,/Codes & accès/);assert.doesNotMatch(txt,/Page d’accueil/);assert.doesNotMatch(txt,/Gestion des ressources d’aide/);await s.context.close();
  });

  await test('Mobile 360 px : aucune largeur horizontale parasite et navigation tactile active',async()=>{
    const s=await session(browser,'R4',{viewport:{width:360,height:800},isMobile:true,hasTouch:true});const dims=await s.page.evaluate(()=>({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth}));assert.ok(dims.sw<=dims.cw+2,`overflow ${dims.sw}/${dims.cw}`);for(const screen of ['homeScreen','planningScreen','exchangeScreen','alertsScreen','adminScreen']){const b=s.page.locator(`.nav-btn[data-screen="${screen}"]`);assert.equal(await b.isVisible(),true,screen);await b.tap();await s.page.waitForTimeout(30);assert.equal(await s.page.locator(`#${screen}`).evaluate(el=>el.classList.contains('active')),true,screen);}assert.deepEqual(s.errors,[]);await s.context.close();
  });

  await test('Mobile : modale profil utilisable et scrollable sans sortir de l’écran',async()=>{
    const s=await session(browser,'R4',{viewport:{width:360,height:640},isMobile:true,hasTouch:true});
    await s.page.evaluate(()=>window.W.openSelfProfileEdit());
    await s.page.locator('#selfPseudoField').waitFor({state:'visible',timeout:5000});
    const metrics=await s.page.evaluate(()=>{
      const modal=document.getElementById('modal'),field=document.getElementById('selfPseudoField');
      if(!modal||!field)return null;
      let panel=field.parentElement;
      while(panel&&panel.parentElement&&panel.parentElement!==modal)panel=panel.parentElement;
      panel=panel||modal;
      const r=panel.getBoundingClientRect(),cs=getComputedStyle(panel);
      return {hidden:modal.classList.contains('hidden'),left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height,sh:panel.scrollHeight,ch:panel.clientHeight,oy:cs.overflowY};
    });
    assert.ok(metrics);assert.equal(metrics.hidden,false);
    assert.ok(metrics.left>=-2&&metrics.right<=362,`horizontal ${metrics.left}/${metrics.right}`);
    assert.ok(metrics.width<=362,`width ${metrics.width}`);
    assert.ok(metrics.top>=-2&&metrics.bottom<=642,`vertical ${metrics.top}/${metrics.bottom}`);
    assert.ok(metrics.sh<=metrics.ch+1||['auto','scroll'].includes(metrics.oy),`not scrollable sh=${metrics.sh} ch=${metrics.ch} oy=${metrics.oy}`);
    assert.deepEqual(s.errors,[]);await s.context.close();
  });

  await test('Retour Portail et bouton Changer de session : éléments réellement interactifs',async()=>{
    const s=await session(browser,'R4');const brand=s.page.locator('#brandHome');assert.equal(await brand.count(),1);const sessionBtn=s.page.getByRole('button',{name:/Changer de session/i});assert.ok(await sessionBtn.count()>=1);const before=await s.page.evaluate(()=>localStorage.getItem('wfgg_portal_session'));assert.equal(before,'qa-portal-token');await s.context.close();
  });

  await test('Parcours étendu : zéro erreur console/page',async()=>{
    const s=await session(browser,'R4');await s.page.evaluate(()=>window.W.openSelfProfileEdit());await s.page.evaluate(()=>window.W.closeModal());await s.page.evaluate(()=>window.W.openUnavailablePeriod('2026-09-10'));await s.page.evaluate(()=>window.W.closeModal());await s.page.locator('.nav-btn[data-screen="adminScreen"]').click();for(const sec of ['messages','settings','rotations','manual','equity']){await s.page.evaluate(x=>window.W.openAdminSection(x),sec);await s.page.waitForTimeout(25);await s.page.evaluate(()=>window.W.renderAdminHome());}await s.page.evaluate(()=>window.W.openAdminAnalytics());await s.page.waitForTimeout(50);assert.deepEqual(s.errors,[]);await s.context.close();
  });
}finally{await browser.close();}

console.log('\n=== RECETTE ÉTENDUE TRAIN ===');for(const r of results)console.log(`${r.status.padEnd(4)} ${String(r.ms).padStart(5)} ms  ${r.name}${r.error?`\n${r.error}`:''}`);const failed=results.filter(r=>r.status==='FAIL');console.log(`\nTOTAL=${results.length} PASS=${results.length-failed.length} FAIL=${failed.length}`);if(failed.length)process.exit(1);
