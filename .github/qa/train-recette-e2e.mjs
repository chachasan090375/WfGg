import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const ROOT = process.env.WFGG_PREVIEW || 'https://train-bridge-phase3.wfgg.pages.dev';
const DIRECT = 'portal-auth-phase1-wfgg-train.chachasan090375.workers.dev';

const expectedExports = [
  'addCalendar','addAllCalendar','toggleAlerts','changeWeek','openExchange','publishMarketExchange',
  'cancelMarketExchange','pickMyDateForMarket','executeMarketSwap','markUnavailable','showUnavailableChoice',
  'openUnavailableDayPicker','saveUnavailableDayFromPicker','openUnavailablePeriod','syncUnavailablePeriodMin',
  'saveUnavailablePeriod','saveUnavailableDay','removeUnavailableRange','removeUnavailable','showUnavailable',
  'toggleRotation','showRotationStatus','openProfileInfo','goAlerts','closeAndOpenExchange','closeModal',
  'saveAdminSettings','saveDay','clearDayOverride','adminToggleRotation','filterMembers','searchMembers',
  'openMemberForm','saveMemberForm','deleteMember','renderRotationOrder','moveRotation','generateMessage',
  'nextMessage','copyGeneratedMessage','openAdminSection','renderAdminHome','openSelfProfileEdit',
  'saveSelfProfile','saveRotationRanks','copyText','resetMemberPin','downloadGeneratedCodesCsv',
  'clearGeneratedCodes','changeLanguage','setPortalLanguage','showPortal','showTrainEntry','showPortalHelp',
  'openPortalResource','togglePresenceList','refreshAdminPresence','openGuidePortal','openGameHelp','openGameLink',
  'addGameLinkDraft','removeGameLinkDraft','saveGameLinks','openAdminAnalytics','renderAnalyticsMenu',
  'openAnalyticsSub','renderTrainHistory','setAnalyticsRotationDays','setAnalyticsRotationPool',
  'setAnalyticsRotationSort','setAnalyticsActivitySort','setAnalyticsSettingsFilter','setAnalyticsFilter',
  'setAnalyticsHistorySort','setAnalyticsSearch','openChangePin','changeMyPin'
];

function clone(x){ return JSON.parse(JSON.stringify(x)); }
function makeRoster(){
  return [
    ['u5','QA R5','R5'],['u4','QA R4','R4'],['u3a','QA R3 A','R3'],['u3b','QA R3 B','R3'],
    ['u2','QA R2','R2'],['u1','QA R1','R1']
  ].map(([id,pseudo,rank])=>({id,pseudo,rank,avatar:'assets/icon-192.png',active:true,lastSeen:null}));
}
function makeAuthoritativeSchedule(){
  // Intentionally differs from the historical local generator. In particular,
  // 2026-09-15 is forced to u4 Conducteur A although the old alternating
  // browser generator would classify that offset as an R3-driver day.
  return [
    {date:'2026-08-29',driverId:'u4',vipId:'u3a',driverClass:'officer',r3Cycle:0},
    {date:'2026-08-31',driverId:'u5',vipId:'u3b',driverClass:'officer',r3Cycle:0},
    {date:'2026-09-04',driverId:'u4',vipId:'u2',driverClass:'officer',r3Cycle:1},
    {date:'2026-09-15',driverId:'u4',vipId:'u1',driverClass:'officer',r3Cycle:2},
    {date:'2026-09-17',driverId:'u3a',vipId:'u3b',driverClass:'r3',r3Cycle:2}
  ];
}
function makeState(meId, withOwnExchange=false){
  const exchanges=[];
  if(withOwnExchange){
    exchanges.push({id:'ex-own',fromId:meId,fromDate:'2026-08-29',roleKey:meId==='u4'?'driver-officer':'vip',status:'open',created:'2026-08-25T10:00:00.000Z'});
  }
  exchanges.push({id:'ex-other',fromId:'u5',fromDate:'2026-08-31',roleKey:'driver-officer',status:'open',created:'2026-08-25T09:00:00.000Z'});
  return {
    settings:{anchorDate:'2026-08-25',trainTime:'20:00',officersFirst:true,reminderDayBefore:true,reminder30:true,
      rotationRanks:{officer:['R5','R4'],r3driver:['R3'],vip:['R3','R2','R1']}},
    unavailable:{},outRotation:[],overrides:{},exchanges,alertsEnabled:{},languages:{[meId]:'fr'},gameLinks:[],
    playerEdits:{},addedPlayers:[],removedPlayers:[],rotationOrder:{officer:['u5','u4'],r3driver:['u3a','u3b'],r3vip:['u3a','u3b','u2','u1']},
    messageVariant:{weekly:0,daily:0,driver:0,vip:0},
    manualHistory:{version:'qa',eventCount:63,cutoff:'2026-08-16',counts:{driver:{},vip:{}},links:{},former:[],correctionsApplied:[],correctionConflicts:[],missingReference:[],extraApp:[]}
  };
}

async function makeSession(browser, rank='R4', {withOwnExchange=false}={}){
  const roster=makeRoster();
  const me=roster.find(x=>x.rank===rank) || roster[1];
  let state=makeState(me.id,withOwnExchange);
  let version=1;
  const calls=[];
  const errors=[];
  const context=await browser.newContext({locale:'fr-FR',acceptDownloads:true});
  await context.addInitScript(()=>{
    localStorage.setItem('wfgg_portal_session','qa-portal-token');
    localStorage.setItem('wfgg_portal_language','fr');
    localStorage.setItem('wfgg_portal_language_source','profile');
    sessionStorage.setItem('wfgg_train_sw_reset_v1','1');
  });
  const page=await context.newPage();
  page.on('pageerror',e=>errors.push(`pageerror: ${e.message}`));
  page.on('console',m=>{ if(m.type()==='error') errors.push(`console: ${m.text()}`); });

  function snapshot(){
    const current=roster.find(x=>x.id===me.id);
    return {ok:true,me:{id:current.id,pseudo:current.pseudo,rank:current.rank,avatar:current.avatar,active:true},roster:clone(roster),state:clone(state),schedule:clone(makeAuthoritativeSchedule()),version,updatedAt:new Date().toISOString(),serverTime:new Date().toISOString()};
  }
  async function body(req){ try{return req.postDataJSON();}catch{return {};}}

  await page.route('**/api/**', async route=>{
    const req=route.request();
    const url=new URL(req.url());
    const p=url.pathname, method=req.method();
    calls.push({method,path:p,url:req.url()});
    const ok=(data={ok:true},status=200)=>route.fulfill({status,contentType:'application/json; charset=utf-8',body:JSON.stringify(data)});

    if(p==='/api/snapshot' && method==='GET') return ok(snapshot());
    if(p==='/api/presence/heartbeat' && method==='POST') return ok({ok:true,lastSeen:new Date().toISOString()});
    if(p==='/api/admin/presence' && method==='GET') return ok({ok:true,count:1,online:[{...me,lastSeen:new Date().toISOString()}],thresholdSeconds:90,serverTime:new Date().toISOString()});
    if(p==='/api/directory' && method==='GET') return ok({ok:true,users:roster.map(({pseudo,rank})=>({pseudo,rank}))});
    if(p==='/api/help-links' && method==='GET') return ok({ok:true,links:[]});
    if(p==='/api/admin/analytics' && method==='GET') return ok({ok:true,summary:{actions7:4,actions30:12,activeMembers:6,openExchanges:state.exchanges.filter(x=>x.status==='open').length},rotation30:{spread:{officer:0,r3driver:0,vip:0},officer:[],r3driver:[],vip:[]},rotation90:{spread:{officer:0,r3driver:0,vip:0},officer:[],r3driver:[],vip:[]},activityByActor:[],settingsChanges:[],history:[],manualHistory:clone(state.manualHistory)});
    if(p==='/api/profile/language' && method==='PATCH') return ok({ok:true});

    if(p==='/api/exchanges' && method==='POST'){
      const b=await body(req); const id=`ex-${Date.now()}`;
      state.exchanges.push({id,fromId:me.id,fromDate:b.fromDate,roleKey:b.roleKey,status:'open',created:new Date().toISOString()}); version++;
      return ok({ok:true,id},201);
    }
    const cancel=p.match(/^\/api\/exchanges\/([^/]+)$/);
    if(cancel && method==='DELETE'){
      const x=state.exchanges.find(e=>e.id===decodeURIComponent(cancel[1])); if(x){x.status='cancelled';x.closed=new Date().toISOString();} version++;
      return ok({ok:true});
    }
    const accept=p.match(/^\/api\/exchanges\/([^/]+)\/accept$/);
    if(accept && method==='POST'){
      const b=await body(req); const x=state.exchanges.find(e=>e.id===decodeURIComponent(accept[1]));
      if(x){x.status='accepted';x.toId=me.id;x.swapWithDate=b.myDate;x.closed=new Date().toISOString();} version++;
      return ok({ok:true});
    }
    if(p==='/api/me/preferences' && method==='PUT'){
      const b=await body(req);
      if('alertsEnabled' in b) state.alertsEnabled[me.id]=!!b.alertsEnabled;
      if('outRotation' in b){ const set=new Set(state.outRotation); b.outRotation?set.add(me.id):set.delete(me.id); state.outRotation=[...set]; }
      if(Array.isArray(b.unavailable)) state.unavailable[me.id]=[...b.unavailable];
      if(b.language) state.languages[me.id]=b.language;
      version++; return ok({ok:true});
    }
    if(p==='/api/me' && method==='PUT'){
      const b=await body(req), row=roster.find(x=>x.id===me.id); if(b.pseudo) row.pseudo=b.pseudo; if(b.avatar) row.avatar=b.avatar; version++; return ok({ok:true});
    }
    if(p==='/api/me/pin' && method==='PUT') return ok({ok:true});
    if(p==='/api/admin/settings' && method==='PUT'){
      const b=await body(req); state.settings={...state.settings,...b}; if(b.resetOverrides) state.overrides={}; version++; return ok({ok:true});
    }
    if(p==='/api/admin/rotation-ranks' && method==='PUT'){
      const b=await body(req); state.settings.rotationRanks=clone(b.rotationRanks); state.overrides={}; version++; return ok({ok:true});
    }
    if(p==='/api/admin/rotation-order' && method==='PUT'){
      const b=await body(req); state.rotationOrder[b.key]=[...b.ids]; version++; return ok({ok:true});
    }
    const ov=p.match(/^\/api\/admin\/override\/(\d{4}-\d{2}-\d{2})$/);
    if(ov && method==='PUT'){ const b=await body(req); state.overrides[ov[1]]={driverId:b.driverId||null,vipId:b.vipId||null};version++;return ok({ok:true}); }
    if(ov && method==='DELETE'){ delete state.overrides[ov[1]];version++;return ok({ok:true}); }
    if(p.startsWith('/api/admin/')) return ok({ok:true});
    return ok({ok:true});
  });

  await page.goto(`${ROOT}/train/?qa=${Date.now()}`,{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForFunction(()=>window.W && document.getElementById('appView') && !document.getElementById('appView').classList.contains('hidden'),null,{timeout:30000});
  await page.waitForTimeout(300);
  return {context,page,roster,me,state:()=>state,calls,errors};
}

const results=[];
async function test(name,fn){
  const started=Date.now();
  try{ await fn(); results.push({name,status:'PASS',ms:Date.now()-started}); console.log(`PASS ${name}`); }
  catch(e){ results.push({name,status:'FAIL',ms:Date.now()-started,error:e?.stack||String(e)}); console.error(`FAIL ${name}\n${e?.stack||e}`); }
}

const browser=await chromium.launch({headless:true});
try{
  await test('Boot Portail → Train et absence d’erreur JavaScript',async()=>{
    const s=await makeSession(browser,'R4',{withOwnExchange:true});
    assert.equal(await s.page.locator('#appView').isVisible(),true);
    assert.ok(s.calls.some(c=>c.path==='/api/snapshot'));
    assert.ok(s.calls.some(c=>c.path==='/api/presence/heartbeat'));
    const authoritative=await s.page.evaluate(()=>window.__WFGG_SERVER_SCHEDULE__||[]);
    assert.ok(authoritative.some(x=>x.date==='2026-09-15'&&x.driverId==='u4'&&x.driverClass==='officer'),'planning serveur non chargé dans le frontend');
    assert.deepEqual(s.errors,[]);
    await s.context.close();
  });

  await test('Contrat des actions frontend exportées',async()=>{
    const s=await makeSession(browser,'R4');
    const missing=await s.page.evaluate(list=>list.filter(k=>typeof window.W?.[k]!=='function'),expectedExports);
    assert.deepEqual(missing,[]);
    await s.context.close();
  });

  await test('Navigation Moi / Planning / Échanges / Alertes / Admin',async()=>{
    const s=await makeSession(browser,'R4');
    const nav=await s.page.locator('.nav-btn:not(.hidden)').evaluateAll(nodes=>nodes.map(n=>({screen:n.dataset.screen,text:n.textContent.trim()})));
    assert.ok(nav.length>=5,JSON.stringify(nav));
    for(const item of nav){
      await s.page.locator(`.nav-btn[data-screen="${item.screen}"]`).click();
      await s.page.waitForTimeout(60);
      assert.equal(await s.page.locator(`#${item.screen}`).evaluate(el=>el.classList.contains('active')),true,`screen ${item.screen}`);
    }
    assert.deepEqual(s.errors,[]);
    await s.context.close();
  });

  await test('Droits UI : Admin visible seulement pour R4/R5',async()=>{
    for(const rank of ['R5','R4','R3','R2','R1']){
      const s=await makeSession(browser,rank);
      const admin=s.page.locator('.nav-btn[data-screen="adminScreen"]');
      const visible=await admin.isVisible().catch(()=>false);
      assert.equal(visible,['R5','R4'].includes(rank),`Admin ${rank}`);
      await s.context.close();
    }
  });

  await test('Bourse : une demande ouverte personnelle est visible et retirable dans Mes demandes',async()=>{
    const s=await makeSession(browser,'R4',{withOwnExchange:true});
    await s.page.locator('.nav-btn[data-screen="exchangeScreen"]').click();
    await s.page.waitForTimeout(100);
    const buttons=s.page.getByRole('button',{name:'Retirer mon annonce'});
    assert.ok(await buttons.count()>=2,'Le bouton doit être présent dans la liste générale ET Mes demandes');
    await buttons.last().click();
    await s.page.waitForTimeout(150);
    assert.ok(s.calls.some(c=>c.method==='DELETE'&&c.path==='/api/exchanges/ex-own'));
    assert.equal(s.state().exchanges.find(x=>x.id==='ex-own').status,'cancelled');
    assert.deepEqual(s.errors,[]);
    await s.context.close();
  });

  await test('Bourse : planning serveur autoritaire → publication → apparition → retrait',async()=>{
    const s=await makeSession(browser,'R4');
    // This date deliberately conflicts with the old local generator. Opening
    // the exchange modal proves schedule() is reading the server snapshot.
    await s.page.evaluate(()=>window.W.openExchange('2026-09-15','driver'));
    await s.page.waitForTimeout(80);
    const modalText=await s.page.locator('#modal').innerText();
    assert.match(modalText,/15/,'la date autoritaire doit être reconnue par openExchange');
    await s.page.evaluate(()=>window.W.publishMarketExchange('2026-09-15','driver-officer'));
    await s.page.locator('.nav-btn[data-screen="exchangeScreen"]').click();
    await s.page.waitForTimeout(100);
    const open=s.state().exchanges.find(x=>x.fromId==='u4'&&x.fromDate==='2026-09-15'&&x.status==='open');
    assert.ok(open,'annonce publiée dans le snapshot');
    assert.ok((await s.page.getByRole('button',{name:'Retirer mon annonce'}).count())>=2);
    const txt=await s.page.locator('#exchangeScreen').innerText();
    assert.match(txt,/15/);
    await s.page.getByRole('button',{name:'Retirer mon annonce'}).last().click();
    await s.page.waitForTimeout(100);
    assert.equal(s.state().exchanges.find(x=>x.id===open.id).status,'cancelled');
    await s.context.close();
  });

  await test('Bourse : acceptation d’un échange et nouvelle date enregistrée',async()=>{
    const s=await makeSession(browser,'R4');
    await s.page.evaluate(()=>window.W.executeMarketSwap('ex-other','2026-09-04'));
    await s.page.waitForTimeout(100);
    const x=s.state().exchanges.find(e=>e.id==='ex-other');
    assert.equal(x.status,'accepted'); assert.equal(x.swapWithDate,'2026-09-04');
    assert.ok(s.calls.some(c=>c.method==='POST'&&c.path==='/api/exchanges/ex-other/accept'));
    await s.context.close();
  });

  await test('Alertes personnelles : activation/désactivation synchronisée',async()=>{
    const s=await makeSession(browser,'R4');
    assert.equal(!!s.state().alertsEnabled.u4,false);
    await s.page.evaluate(()=>window.W.toggleAlerts()); await s.page.waitForTimeout(80);
    assert.equal(s.state().alertsEnabled.u4,true);
    await s.page.evaluate(()=>window.W.toggleAlerts()); await s.page.waitForTimeout(80);
    assert.equal(s.state().alertsEnabled.u4,false);
    await s.context.close();
  });

  await test('Rotation personnelle : sortie puis réactivation',async()=>{
    const s=await makeSession(browser,'R4');
    await s.page.evaluate(()=>window.W.toggleRotation()); await s.page.waitForTimeout(80);
    assert.ok(s.state().outRotation.includes('u4'));
    await s.page.evaluate(()=>window.W.toggleRotation()); await s.page.waitForTimeout(80);
    assert.ok(!s.state().outRotation.includes('u4'));
    await s.context.close();
  });

  await test('Indisponibilités : ajout et retrait',async()=>{
    const s=await makeSession(browser,'R4');
    await s.page.evaluate(()=>window.W.saveUnavailableDay('2026-09-20')); await s.page.waitForTimeout(80);
    assert.ok((s.state().unavailable.u4||[]).includes('2026-09-20'));
    await s.page.evaluate(()=>window.W.removeUnavailable('2026-09-20')); await s.page.waitForTimeout(80);
    assert.ok(!(s.state().unavailable.u4||[]).includes('2026-09-20'));
    await s.context.close();
  });

  await test('Planning : navigation semaine précédente/suivante sans erreur',async()=>{
    const s=await makeSession(browser,'R4');
    await s.page.locator('.nav-btn[data-screen="planningScreen"]').click();
    const before=await s.page.locator('#planningScreen').innerText();
    await s.page.evaluate(()=>window.W.changeWeek(1)); await s.page.waitForTimeout(40);
    const after=await s.page.locator('#planningScreen').innerText();
    assert.notEqual(before,after);
    await s.page.evaluate(()=>window.W.changeWeek(-1));
    assert.deepEqual(s.errors,[]);
    await s.context.close();
  });

  await test('Langues FR/IT/EN/ES : changement sans erreur',async()=>{
    const s=await makeSession(browser,'R4');
    for(const lang of ['it','en','es','fr']){
      await s.page.evaluate(l=>window.W.changeLanguage(l),lang); await s.page.waitForTimeout(60);
      const stored=await s.page.evaluate(()=>localStorage.getItem('wfgg_train_lang'));
      assert.equal(stored,lang);
    }
    assert.deepEqual(s.errors,[]);
    await s.context.close();
  });

  await test('Administration R4 : toutes les sections s’ouvrent sans exception',async()=>{
    const s=await makeSession(browser,'R4');
    await s.page.locator('.nav-btn[data-screen="adminScreen"]').click();
    const sections=['Messages & notifications','Paramètres du train','Rotations','Planning manuel','Contrôle d’équité','Statistiques du train'];
    for(const label of sections){
      await s.page.evaluate(()=>window.W.renderAdminHome()); await s.page.waitForTimeout(30);
      const button=s.page.getByRole('button',{name:new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'i')}).first();
      assert.equal(await button.isVisible(),true,`section ${label}`);
      await button.click(); await s.page.waitForTimeout(100);
      assert.deepEqual(s.errors,[],`erreur section ${label}: ${s.errors.join(' | ')}`);
    }
    await s.context.close();
  });

  await test('Paramètres du train : enregistrement et resynchronisation',async()=>{
    const s=await makeSession(browser,'R4');
    await s.page.locator('.nav-btn[data-screen="adminScreen"]').click();
    await s.page.evaluate(()=>window.W.openAdminSection('settings')); await s.page.waitForTimeout(50);
    const time=s.page.locator('#trainTimeAdmin'); if(await time.count()){ await time.fill('21:15'); }
    const anchor=s.page.locator('#anchorAdmin'); if(await anchor.count()){ await anchor.fill('2026-08-25'); }
    await s.page.evaluate(()=>window.W.saveAdminSettings()); await s.page.waitForTimeout(80);
    assert.equal(s.state().settings.trainTime,'21:15');
    assert.ok(s.calls.some(c=>c.method==='PUT'&&c.path==='/api/admin/settings'));
    await s.context.close();
  });

  await test('Présence : heartbeat + compteur admin',async()=>{
    const s=await makeSession(browser,'R4');
    await s.page.locator('.nav-btn[data-screen="adminScreen"]').click();
    await s.page.evaluate(()=>window.W.refreshAdminPresence()); await s.page.waitForTimeout(80);
    assert.ok(s.calls.some(c=>c.path==='/api/presence/heartbeat'));
    assert.ok(s.calls.some(c=>c.path==='/api/admin/presence'));
    await s.context.close();
  });

  await test('Logo vectoriel compact + retour Portail + changement de session présents',async()=>{
    const s=await makeSession(browser,'R4');
    const logo=s.page.locator('img[src*="wfgg-logo-mini.svg"]');
    assert.ok(await logo.count()>=1);
    const sessionButton=s.page.getByRole('button',{name:/session|changer/i});
    assert.ok((await sessionButton.count())>=1 || await s.page.locator('#installBtn').count()>=1);
    await s.context.close();
  });

  await test('Aucune erreur console/page sur le parcours R4 complet',async()=>{
    const s=await makeSession(browser,'R4',{withOwnExchange:true});
    for(const screen of ['homeScreen','planningScreen','exchangeScreen','alertsScreen','adminScreen']){
      const b=s.page.locator(`.nav-btn[data-screen="${screen}"]`); if(await b.isVisible()) {await b.click();await s.page.waitForTimeout(40);}
    }
    assert.deepEqual(s.errors,[]);
    await s.context.close();
  });
} finally {
  await browser.close();
}

console.log('\n=== RECETTE TRAIN ===');
for(const r of results) console.log(`${r.status.padEnd(4)} ${String(r.ms).padStart(5)} ms  ${r.name}${r.error?`\n${r.error}`:''}`);
const failed=results.filter(r=>r.status==='FAIL');
console.log(`\nTOTAL=${results.length} PASS=${results.length-failed.length} FAIL=${failed.length}`);
if(failed.length) process.exit(1);
