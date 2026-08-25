from pathlib import Path

qa=Path('.github/qa/train-recette-e2e.mjs')
s=qa.read_text(encoding='utf-8')

anchor="function makeState(meId, withOwnExchange=false){"
if 'function makeAuthoritativeSchedule()' not in s:
    block="""function makeAuthoritativeSchedule(){
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
"""
    if anchor not in s: raise SystemExit('makeState anchor missing')
    s=s.replace(anchor,block+anchor,1)

old="return {ok:true,me:{id:current.id,pseudo:current.pseudo,rank:current.rank,avatar:current.avatar,active:true},roster:clone(roster),state:clone(state),version,updatedAt:new Date().toISOString(),serverTime:new Date().toISOString()};"
new="return {ok:true,me:{id:current.id,pseudo:current.pseudo,rank:current.rank,avatar:current.avatar,active:true},roster:clone(roster),state:clone(state),schedule:clone(makeAuthoritativeSchedule()),version,updatedAt:new Date().toISOString(),serverTime:new Date().toISOString()};"
if old in s:
    s=s.replace(old,new,1)
elif new not in s:
    raise SystemExit('snapshot return anchor missing')

boot_old="""    assert.ok(s.calls.some(c=>c.path==='/api/presence/heartbeat'));
    assert.deepEqual(s.errors,[]);"""
boot_new="""    assert.ok(s.calls.some(c=>c.path==='/api/presence/heartbeat'));
    const authoritative=await s.page.evaluate(()=>window.__WFGG_SERVER_SCHEDULE__||[]);
    assert.ok(authoritative.some(x=>x.date==='2026-09-15'&&x.driverId==='u4'&&x.driverClass==='officer'),'planning serveur non chargé dans le frontend');
    assert.deepEqual(s.errors,[]);"""
if boot_old in s:
    s=s.replace(boot_old,boot_new,1)
elif boot_new not in s:
    raise SystemExit('boot assertion anchor missing')

pub_old="""  await test('Bourse : publication → apparition immédiate → retrait',async()=>{
    const s=await makeSession(browser,'R4');
    await s.page.evaluate(()=>window.W.publishMarketExchange('2026-09-15','driver-officer'));"""
pub_new="""  await test('Bourse : planning serveur autoritaire → publication → apparition → retrait',async()=>{
    const s=await makeSession(browser,'R4');
    // This date deliberately conflicts with the old local generator. Opening
    // the exchange modal proves schedule() is reading the server snapshot.
    await s.page.evaluate(()=>window.W.openExchange('2026-09-15','driver'));
    await s.page.waitForTimeout(80);
    const modalText=await s.page.locator('#modal').innerText();
    assert.match(modalText,/15/,'la date autoritaire doit être reconnue par openExchange');
    await s.page.evaluate(()=>window.W.publishMarketExchange('2026-09-15','driver-officer'));"""
if pub_old in s:
    s=s.replace(pub_old,pub_new,1)
elif pub_new not in s:
    raise SystemExit('publication QA anchor missing')

qa.write_text(s,encoding='utf-8')

# Extended suite snapshots also get an authoritative schedule so all screens
# exercise the production path rather than silently falling back to local math.
ext=Path('.github/qa/train-recette-extended.mjs')
e=ext.read_text(encoding='utf-8')
if 'function authoritativeSchedule()' not in e:
    a="function state(meId){return {"
    b="""function authoritativeSchedule(){return [
  {date:'2026-08-29',driverId:'u4',vipId:'u3a',driverClass:'officer',r3Cycle:0},
  {date:'2026-08-31',driverId:'u5',vipId:'u3b',driverClass:'officer',r3Cycle:0},
  {date:'2026-09-04',driverId:'u4',vipId:'u2',driverClass:'officer',r3Cycle:1},
  {date:'2026-09-15',driverId:'u4',vipId:'u1',driverClass:'officer',r3Cycle:2},
  {date:'2026-09-17',driverId:'u3a',vipId:'u3b',driverClass:'r3',r3Cycle:2}
];}
"""
    if a not in e: raise SystemExit('extended state anchor missing')
    e=e.replace(a,b+a,1)
old_ext="return {ok:true,me:{id:u.id,pseudo:u.pseudo,rank:u.rank,avatar:u.avatar,active:true},roster:clone(rows),state:clone(st),version,updatedAt:new Date().toISOString(),serverTime:new Date().toISOString()};"
new_ext="return {ok:true,me:{id:u.id,pseudo:u.pseudo,rank:u.rank,avatar:u.avatar,active:true},roster:clone(rows),state:clone(st),schedule:clone(authoritativeSchedule()),version,updatedAt:new Date().toISOString(),serverTime:new Date().toISOString()};"
if old_ext in e:
    e=e.replace(old_ext,new_ext,1)
elif new_ext not in e:
    raise SystemExit('extended snapshot anchor missing')
ext.write_text(e,encoding='utf-8')

wf=Path('.github/workflows/train-recette.yml')
w=wf.read_text(encoding='utf-8')
w=w.replace("echo 'QA revision: browser-v5-production-worker'","echo 'QA revision: browser-v6-authoritative-exchange'")
w=w.replace("grep -q 'wfgg_bridge=v13' frontend/_worker.js","grep -q 'wfgg_bridge=v14' frontend/_worker.js")
w=w.replace("- name: Wait for Cloudflare preview v13","- name: Wait for Cloudflare preview v14")
w=w.replace("wfgg_bridge=v13","wfgg_bridge=v14")
w=w.replace("bridge=v13","bridge=v14")
w=w.replace("waiting_for_v13","waiting_for_v14")
if "WFGG_TRAIN_AUTHORITATIVE_SCHEDULE_V1" not in w:
    w=w.replace("grep -q 'WFGG_TRAIN_EXCHANGE_OWN_CANCEL_V2' frontend/_worker.js","grep -q 'WFGG_TRAIN_EXCHANGE_OWN_CANCEL_V2' frontend/_worker.js\n          grep -q 'WFGG_TRAIN_AUTHORITATIVE_SCHEDULE_V1' frontend/_worker.js")
wf.write_text(w,encoding='utf-8')
print('AUTHORITATIVE_EXCHANGE_FRONTEND_QA=OK')
