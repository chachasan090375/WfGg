import assert from 'node:assert/strict';

const root=process.env.WFGG_PREVIEW||'https://wfgg.pages.dev';
const res=await fetch(`${root}/train/app.js?wfgg_bridge=v14&exchange_parity=${Date.now()}`,{headers:{'user-agent':'Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/139 Mobile Safari/537.36'}});
assert.equal(res.ok,true,`app.js HTTP ${res.status}`);
const src=await res.text();
assert.match(src,/function wfggHistorySeed\(pool, role\)/);
assert.match(src,/let cycleDrivers = new Set\(\)/);
assert.match(src,/let cycleVips = new Set\(\)/);
assert.match(src,/r3Cycle/);
assert.doesNotMatch(src,/VIP : rotation équitable entre R3, R2 et R1/);

const start=src.indexOf('    function wfggHistorySeed(pool, role)');
const end=src.indexOf('    function findAssignment(date)',start);
assert.ok(start>=0&&end>start,'schedule block not found');
const scheduleSource=src.slice(start,end);

let state={
  settings:{anchorDate:'2026-08-17',officersFirst:true,rotationRanks:{officer:['R5','R4'],r3driver:['R3'],vip:['R3','R2','R1']}},
  rotationOrder:{officer:['r5','r4'],r3driver:['r3a','r3b'],r3vip:['r3a','r3b','r2','r1']},
  outRotation:[],unavailable:{},overrides:{},manualHistory:{counts:{driver:{},vip:{}},links:{}}
};
const ROSTER=[
  {id:'r5',pseudo:'R5 QA',rank:'R5',active:true},
  {id:'r4',pseudo:'R4 QA',rank:'R4',active:true},
  {id:'r3a',pseudo:'R3 A',rank:'R3',active:true},
  {id:'r3b',pseudo:'R3 B',rank:'R3',active:true},
  {id:'r2',pseudo:'R2 QA',rank:'R2',active:true},
  {id:'r1',pseudo:'R1 QA',rank:'R1',active:true}
];
function parseISO(s){const [y,m,d]=s.split('-').map(Number);return new Date(y,m-1,d)}
function dateISO(d){return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
function addDays(d,n){const x=new Date(d);x.setDate(x.getDate()+n);return x}
function ensureRotationRankSettings(){state.settings.rotationRanks||={officer:['R5','R4'],r3driver:['R3'],vip:['R3','R2','R1']}}
function ranksForRotation(k){ensureRotationRankSettings();return [...state.settings.rotationRanks[k]]}
function isOut(id){return (state.outRotation||[]).includes(id)}
function isUnavailable(id,date){return (state.unavailable[id]||[]).includes(date)}
function activePool(ranks){return ROSTER.filter(m=>ranks.includes(m.rank)&&m.active&&!isOut(m.id))}
function orderedPool(pool,key){const order=state.rotationOrder[key]||[];const pos=Object.fromEntries(order.map((id,i)=>[id,i]));return pool.slice().sort((a,b)=>(pos[a.id]??9999)-(pos[b.id]??9999)||a.id.localeCompare(b.id))}
function pickFair(pool,date,history,exclude=[]){const filtered=pool.filter(m=>!exclude.includes(m.id)&&!isUnavailable(m.id,date));if(!filtered.length)return null;const orderIndex=Object.fromEntries(pool.map((m,i)=>[m.id,i]));return filtered.slice().sort((a,b)=>{const ha=history[a.id]||{count:0,last:'0000-00-00'},hb=history[b.id]||{count:0,last:'0000-00-00'};if(ha.count!==hb.count)return ha.count-hb.count;const lc=ha.last.localeCompare(hb.last);if(lc!==0)return lc;return (orderIndex[a.id]??9999)-(orderIndex[b.id]??9999)})[0]}
function touchHistory(history,m,date){if(!m)return;history[m.id]||={count:0,last:'0000-00-00'};history[m.id].count++;history[m.id].last=date}

// Execute the exact schedule functions served by the deployed frontend.
(0,eval)(`globalThis.__wfggScheduleFactory=(state,ROSTER,parseISO,dateISO,addDays,ensureRotationRankSettings,ranksForRotation,isOut,isUnavailable,activePool,orderedPool,pickFair,touchHistory)=>{${scheduleSource};return {generateSchedule,wfggHistorySeed};}`);
const factory=globalThis.__wfggScheduleFactory;
let F=factory(state,ROSTER,parseISO,dateISO,addDays,ensureRotationRankSettings,ranksForRotation,isOut,isUnavailable,activePool,orderedPool,pickFair,touchHistory);
let days=F.generateSchedule(6);
assert.deepEqual(days.slice(0,6).map(x=>[x.date,x.driverId,x.vipId,x.driverClass,x.r3Cycle]),[
  ['2026-08-17','r5','r3a','officer',0],
  ['2026-08-18','r3a','r3b','r3',0],
  ['2026-08-19','r4','r2','officer',0],
  ['2026-08-20','r3b','r1','r3',0],
  ['2026-08-21','r5','r2','officer',0],
  ['2026-08-22','r3a','r3b','r3',1]
]);

// Manual history must seed frontend fairness exactly like the backend.
state=structuredClone(state);
state.manualHistory={
  counts:{driver:{oldr5:{count:9,last:'2026-08-15'},oldr4:{count:0,last:'0000-00-00'}},vip:{}},
  links:{r5:'oldr5',r4:'oldr4'}
};
F=factory(state,ROSTER,parseISO,dateISO,addDays,ensureRotationRankSettings,ranksForRotation,isOut,isUnavailable,activePool,orderedPool,pickFair,touchHistory);
days=F.generateSchedule(1);
assert.equal(days[0].driverId,'r4','manual history is not seeding frontend fairness');

console.log('EXCHANGE_SCHEDULE_PARITY=PASS');
