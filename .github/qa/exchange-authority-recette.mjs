import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const ROOT=process.env.WFGG_PREVIEW||'https://exchange-fix.wfgg.pages.dev';
const iso=d=>d.toISOString().slice(0,10);
const add=(d,n)=>{const x=new Date(d);x.setUTCDate(x.getUTCDate()+n);return x};
const today=new Date();
const d1=iso(add(today,1)), d2=iso(add(today,2)), d3=iso(add(today,3)), d4=iso(add(today,4));

const roster=[
  {id:'u4',pseudo:'QA Moi',rank:'R4',avatar:'assets/icon-192.png',active:true},
  {id:'u5',pseudo:'QA Autre',rank:'R5',avatar:'assets/icon-192.png',active:true},
  {id:'u3',pseudo:'QA R3',rank:'R3',avatar:'assets/icon-192.png',active:true},
  {id:'u2',pseudo:'QA R2',rank:'R2',avatar:'assets/icon-192.png',active:true}
];
let state={
  settings:{anchorDate:'2030-01-01',trainTime:'20:00',officersFirst:true,reminderDayBefore:true,reminder30:true,rotationRanks:{officer:['R5','R4'],r3driver:['R3'],vip:['R3','R2','R1']}},
  unavailable:{},outRotation:[],overrides:{},
  exchanges:[
    {id:'other-open',fromId:'u5',fromDate:d2,roleKey:'driver-officer',status:'open',created:new Date().toISOString()},
    {id:'orphan-open',fromId:'missing-user',fromDate:d4,roleKey:'vip',status:'open',created:new Date().toISOString()}
  ],
  alertsEnabled:{},languages:{u4:'fr'},gameLinks:[],playerEdits:{},addedPlayers:[],removedPlayers:[],
  rotationOrder:{officer:['u5','u4'],r3driver:['u3'],r3vip:['u3','u2']},
  messageVariant:{weekly:0,daily:0,driver:0,vip:0},manualHistory:{counts:{driver:{},vip:{}},links:{},former:[]}
};
const serverSchedule=[
  {date:d1,driverId:'u4',vipId:'u3',driverClass:'officer',r3Cycle:0},
  {date:d2,driverId:'u5',vipId:'u2',driverClass:'officer',r3Cycle:0},
  {date:d3,driverId:'u4',vipId:'u3',driverClass:'officer',r3Cycle:0},
  {date:d4,driverId:'u5',vipId:'u4',driverClass:'officer',r3Cycle:0}
];
let version=1;
const calls=[];
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({locale:'fr-FR',viewport:{width:412,height:915},isMobile:true,hasTouch:true});
await context.addInitScript(()=>{
  localStorage.setItem('wfgg_portal_session','qa-portal-token');
  localStorage.setItem('wfgg_portal_language','fr');
  localStorage.setItem('wfgg_portal_language_source','profile');
  sessionStorage.setItem('wfgg_train_sw_reset_v1','1');
  sessionStorage.setItem('wfgg_train_snapshot_seed_reload_v1','1');
});
const page=await context.newPage();
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
function snap(){return {ok:true,me:roster[0],roster,state:JSON.parse(JSON.stringify(state)),schedule:JSON.parse(JSON.stringify(serverSchedule)),scheduleSource:'server-v1',version,updatedAt:new Date().toISOString(),serverTime:new Date().toISOString()}}
await page.route('**/api/**',async route=>{
  const req=route.request(),u=new URL(req.url()),p=u.pathname,m=req.method();
  let body={};try{body=req.postDataJSON()||{}}catch{}
  calls.push({method:m,path:p,body});
  const json=(data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  if(p==='/api/snapshot'&&m==='GET')return json(snap());
  if(p==='/api/presence/heartbeat'&&m==='POST')return json({ok:true,lastSeen:new Date().toISOString()});
  if(p==='/api/exchanges'&&m==='POST'){
    state.exchanges.push({id:'mine-open',fromId:'u4',fromDate:body.fromDate,roleKey:body.roleKey,status:'open',created:new Date().toISOString()});
    version++;
    return json({ok:true});
  }
  if(p==='/api/exchanges/mine-open'&&m==='DELETE'){
    state.exchanges.find(x=>x.id==='mine-open').status='cancelled';version++;return json({ok:true});
  }
  return json({ok:true});
});

try{
  await page.goto(`${ROOT}/train/?exchange_authority=1`,{waitUntil:'domcontentloaded',timeout:45000});
  await page.locator('#appView:not(.hidden)').waitFor({timeout:30000});

  // L'ancien calcul local part de 2030 et ne peut pas produire d1 : voir d1 prouve l'usage du planning serveur.
  await page.locator('#homeScreen').getByText(/Ton prochain train/).waitFor();
  const homeText=await page.locator('#homeScreen').innerText();
  assert.match(homeText,/CONDUCTEUR/);
  assert.equal(await page.locator('#homeScreen .exchange-btn').count()>0,true,'server assignment must expose exchange action');

  await page.locator('.nav-btn[data-screen="exchangeScreen"]').click();
  await page.locator('#exchangeScreen').getByText('QA Autre').waitFor();
  await page.locator('#exchangeScreen').getByText('Joueur indisponible').waitFor();
  assert.match(await page.locator('#exchangeScreen').innerText(),/Je propose une de mes dates/);

  await page.locator('.nav-btn[data-screen="homeScreen"]').click();
  await page.locator('#homeScreen .exchange-btn').first().click();
  await page.getByRole('button',{name:'Publier ma demande'}).click();
  await page.waitForTimeout(300);

  const pub=calls.find(x=>x.method==='POST'&&x.path==='/api/exchanges');
  assert.ok(pub,'exchange publish request missing');
  assert.equal(pub.body.fromDate,d1,'publish must use server-assigned date');
  assert.equal(pub.body.roleKey,'driver-officer','publish must use server role key');

  await page.locator('.nav-btn[data-screen="exchangeScreen"]').click();
  const exchangeText=await page.locator('#exchangeScreen').innerText();
  assert.match(exchangeText,/Mes demandes/);
  assert.match(exchangeText,/Retirer mon annonce/);
  assert.equal(errors.length,0,`browser errors: ${errors.join(' | ')}`);
  console.log('EXCHANGE_AUTHORITY_RECETTE=OK');
  console.log(`server_dates=${d1},${d2},${d3},${d4}`);
} finally {
  await browser.close();
}
