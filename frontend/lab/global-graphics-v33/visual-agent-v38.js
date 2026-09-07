(()=>{
'use strict';

/* WfGg V38 — on-device visual semantic agent.
   - Zero-shot image classification in Chrome with Transformers.js + CLIP.
   - Persists semantic labels in IndexedDB so an asset is not re-analysed on every session.
   - Runs progressively in the background and yields to foreground browsing.
   - Adds semantic query/filter semantics to the existing search bar.
   - Classifies 2D/raster previews automatically; current 3D canvases are classified opportunistically.
*/

const VERSION='38.0';
const API='/api/v33';
const DB_NAME='wfgg-visual-agent-v38';
const DB_VERSION=1;
const STORE='semantics';
const STATE_KEY='wfgg-visual-agent-v38-state';
const PAGE=80;
const MODEL='Xenova/clip-vit-base-patch32';
const TRANSFORMERS_URL='https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.2.0/+esm';
const MODEL_DELAY_MS=2200;
const ITEM_GAP_MS=120;
const USER_IDLE_MS=900;

const LABELS=[
  'vehicle','tank','armored vehicle','car','truck','motorcycle','drone','aircraft','helicopter',
  'human character','face portrait','robot character','animal',
  'weapon','gun','missile','turret',
  'building','base structure','environment scenery','map terrain',
  'game item','equipment object','user interface icon','game badge','button interface',
  'explosion','smoke','fire','particle effect',
  'texture atlas','UV texture map','sprite sheet','material texture','normal map',
  'background image','other game object'
];

const TERM_ALIASES=new Map([
  ['vehicle','vehicle'],['vehicles','vehicle'],['véhicule','vehicle'],['vehicule','vehicle'],['véhicules','vehicle'],['vehicules','vehicle'],
  ['tank','tank'],['char','tank'],['chars','tank'],['armored','armored vehicle'],['blindé','armored vehicle'],['blinde','armored vehicle'],
  ['car','car'],['cars','car'],['voiture','car'],['voitures','car'],
  ['truck','truck'],['camion','truck'],['camions','truck'],['drone','drone'],['drones','drone'],
  ['aircraft','aircraft'],['avion','aircraft'],['avions','aircraft'],['helicopter','helicopter'],['hélicoptère','helicopter'],['helicoptere','helicopter'],
  ['character','character'],['characters','character'],['personnage','character'],['personnages','character'],['hero','character'],['héros','character'],['heros','character'],
  ['portrait','portrait'],['face','portrait'],['visage','portrait'],['robot','robot'],
  ['weapon','weapon'],['weapons','weapon'],['arme','weapon'],['armes','weapon'],['gun','gun'],['fusil','gun'],['missile','missile'],['turret','turret'],['tourelle','turret'],
  ['building','building'],['buildings','building'],['bâtiment','building'],['batiment','building'],['base','building'],['structure','building'],
  ['ui','ui'],['icon','ui'],['icone','ui'],['icône','ui'],['badge','ui'],['button','ui'],['bouton','ui'],
  ['effect','effect'],['effects','effect'],['effet','effect'],['effets','effect'],['explosion','explosion'],['smoke','smoke'],['fumée','smoke'],['fumee','smoke'],['fire','fire'],['feu','fire'],
  ['texture','texture'],['textures','texture'],['atlas','texture'],['uv','texture'],['material','texture'],['materiau','texture'],['matériau','texture'],['sprite','sprite sheet'],
  ['item','object'],['objet','object'],['object','object'],['equipment','object'],['équipement','object'],['equipement','object'],
  ['environment','environment'],['environnement','environment'],['scenery','environment'],['background','environment'],['map','map'],['carte','map'],['terrain','map']
]);

const GROUPS={
  vehicle:new Set(['vehicle','tank','armored vehicle','car','truck','motorcycle','drone','aircraft','helicopter']),
  character:new Set(['human character','face portrait','robot character','animal']),
  weapon:new Set(['weapon','gun','missile','turret']),
  building:new Set(['building','base structure']),
  environment:new Set(['environment scenery','map terrain','background image']),
  ui:new Set(['user interface icon','game badge','button interface']),
  effect:new Set(['explosion','smoke','fire','particle effect']),
  texture:new Set(['texture atlas','UV texture map','sprite sheet','material texture','normal map']),
  object:new Set(['game item','equipment object','other game object'])
};

let db=null;
let semanticMap=new Map();
let classifier=null;
let classifierPromise=null;
let agentPaused=false;
let agentRunning=false;
let agentPill=null;
let modelState='idle';
let lastActivity=Date.now();
let searchSpecs=[];
let advancedSpec='';
let minConfidence=0;
let state={offset:0,total:0,scanned:0,visual:0,metadata:0,technical:0,failed:0,completed:false,model:MODEL};

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const norm=s=>String(s??'').trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');
const pathOf=a=>String(a?.asset_path||a?.logical_name||a?.alias_name||'').replace(/\\/g,'/').toLowerCase();
const dimOf=a=>String(a?.dimension_class||'').toLowerCase();
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[c]));

function loadState(){try{const x=JSON.parse(localStorage.getItem(STATE_KEY)||'{}');if(x&&x.model===MODEL)state={...state,...x};}catch{}}
function saveState(){try{localStorage.setItem(STATE_KEY,JSON.stringify(state));}catch{}}
loadState();

function openDb(){
  return new Promise((resolve,reject)=>{
    const req=indexedDB.open(DB_NAME,DB_VERSION);
    req.onupgradeneeded=()=>{const d=req.result;if(!d.objectStoreNames.contains(STORE))d.createObjectStore(STORE,{keyPath:'stable_id'});};
    req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error||new Error('IndexedDB unavailable'));
  });
}
function loadAllRecords(){
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(STORE,'readonly'),req=tx.objectStore(STORE).getAll();
    req.onsuccess=()=>{for(const r of (req.result||[]))semanticMap.set(r.stable_id,r);resolve(req.result||[]);};req.onerror=()=>reject(req.error);
  });
}
function putRecord(rec){
  semanticMap.set(rec.stable_id,rec);
  return new Promise((resolve,reject)=>{const tx=db.transaction(STORE,'readwrite');tx.objectStore(STORE).put(rec);tx.oncomplete=()=>resolve(rec);tx.onerror=()=>reject(tx.error);});
}

function groupForLabel(label){for(const [g,set] of Object.entries(GROUPS))if(set.has(label))return g;return 'object';}
function subtypeFor(label,group){
  if(group==='vehicle')return label==='vehicle'?'vehicle':label;
  if(group==='character')return label==='face portrait'?'portrait':label.replace(' character','');
  if(group==='building')return label==='base structure'?'base':'building';
  if(group==='ui')return label.includes('icon')?'icon':label.includes('badge')?'badge':'button';
  if(group==='texture')return label;
  return label;
}
function makeRecord(a,label,score,source,extra={}){
  const group=groupForLabel(label);return {
    stable_id:a.stable_id,label,category:group,subtype:subtypeFor(label,group),score:Number(score||0),source,
    asset_path:String(a.asset_path||''),dimension:String(a.dimension_class||''),updated_at:Date.now(),...extra
  };
}
function technicalLabel(a){
  const p=pathOf(a),tail=p.split('/').pop()||'';
  if(/\/(texture|textures|pbr|materials?)\//.test(p)||/(?:^|[_-])(normal|nrm|albedo|diffuse|basecolor|rough|metal|spec|mask|ao)(?:[_-]|\.)/.test(tail))return 'material texture';
  if(/\/(uv|atlas)\//.test(p)||/sprite.?sheet|spritesheet|flipbook/.test(p))return 'sprite sheet';
  return '';
}
function metadataGuess(a){
  const p=norm(pathOf(a)+' '+String(a?.family||'')+' '+String(a?.visual_role||'')+' '+String(a?.subject||''));
  const checks=[
    [/\b(tank|char|armored|blinde)\b/,'tank'],[/\b(vehicle|vehicule|car|cars)\b/,'vehicle'],[/\b(truck|camion)\b/,'truck'],[/\b(drone|uav)\b/,'drone'],
    [/\b(aircraft|plane|avion)\b/,'aircraft'],[/\b(helicopter|helico)\b/,'helicopter'],[/\b(character|hero|heros|audie|murphy)\b/,'human character'],
    [/\b(weapon|gun|rifle|arme)\b/,'weapon'],[/\b(missile)\b/,'missile'],[/\b(turret|tourelle)\b/,'turret'],[/\b(building|base|structure)\b/,'building'],
    [/\b(icon|itemicon|badge|ui)\b/,'user interface icon'],[/\b(explosion|smoke|fumee|fire|effect|vfx|particle)\b/,'particle effect']
  ];
  for(const [re,label] of checks)if(re.test(p))return label;return 'other game object';
}

async function ensureClassifier(){
  if(classifier)return classifier;if(classifierPromise)return classifierPromise;
  classifierPromise=(async()=>{
    modelState='loading';updatePill();
    const mod=await import(TRANSFORMERS_URL);
    const options={dtype:'q8'};if(navigator.gpu)options.device='webgpu';
    try{classifier=await mod.pipeline('zero-shot-image-classification',MODEL,options);modelState=options.device==='webgpu'?'webgpu':'wasm';}
    catch(first){
      console.warn('V38_WEBGPU_MODEL_FAIL',first);classifier=await mod.pipeline('zero-shot-image-classification',MODEL,{device:'wasm',dtype:'q8'});modelState='wasm';
    }
    updatePill();return classifier;
  })().catch(e=>{modelState='error';classifierPromise=null;updatePill();throw e;});
  return classifierPromise;
}

async function classifyUrl(a,url,source='clip-raster'){
  const pipe=await ensureClassifier();
  const out=await pipe(url,LABELS,{hypothesis_template:'This is a game image of {}.'});
  const best=(out||[])[0];if(!best)throw new Error('no-classification');
  const top=(out||[]).slice(0,5).map(x=>({label:String(x.label),score:Number(x.score)}));
  const rec=makeRecord(a,String(best.label),Number(best.score),source,{top});await putRecord(rec);state.visual++;return rec;
}
async function classifyBlob(a,blob,source){const u=URL.createObjectURL(blob);try{return await classifyUrl(a,u,source);}finally{URL.revokeObjectURL(u);}}

function shouldVisualClassify(a){
  const d=dimOf(a),p=pathOf(a);if(d==='3d'||d.includes('composant 3d'))return false;
  if(/\/animation\//.test(p)||p.endsWith('.anim'))return false;
  return true;
}
async function classifyAsset(a){
  if(!a?.stable_id||semanticMap.has(a.stable_id))return;
  const tech=technicalLabel(a);if(tech){await putRecord(makeRecord(a,tech,.99,'technical-rule'));state.technical++;return;}
  if(!shouldVisualClassify(a)){
    const label=metadataGuess(a);await putRecord(makeRecord(a,label,.28,'metadata-provisional'));state.metadata++;return;
  }
  try{
    const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),35000);
    const r=await fetch(API+'/render?id='+encodeURIComponent(a.stable_id),{signal:ctl.signal,cache:'force-cache'});clearTimeout(timer);
    if(!r.ok)throw new Error('render '+r.status);const blob=await r.blob();if(!blob.size)throw new Error('empty-render');
    await classifyBlob(a,blob,'clip-raster');
  }catch(e){
    const label=metadataGuess(a);await putRecord(makeRecord(a,label,.22,'metadata-fallback',{error:String(e?.message||e).slice(0,120)}));state.metadata++;state.failed++;
  }
}

function ensurePill(){
  if(agentPill?.isConnected)return agentPill;const bar=document.querySelector('.bar');if(!bar)return null;
  agentPill=document.createElement('button');agentPill.type='button';agentPill.className='pill';agentPill.title='Agent IA visuel local. Appuyer pour pause/reprise.';
  agentPill.onclick=()=>{agentPaused=!agentPaused;updatePill();if(!agentPaused)runAgent();};bar.appendChild(agentPill);updatePill();return agentPill;
}
function updatePill(){
  const p=ensurePill();if(!p)return;const total=state.total||0,done=semanticMap.size,pct=total?Math.min(100,Math.round(done*100/total)):0;
  if(modelState==='loading'){p.textContent='🧠 Agent visuel · chargement IA…';return;}
  if(modelState==='error'){p.textContent=`🧠 Index visuel ${done.toLocaleString('fr-FR')} · IA indisponible`;return;}
  if(state.completed)p.textContent=`🧠 Index visuel ${done.toLocaleString('fr-FR')} · terminé`;
  else if(agentPaused)p.textContent=`⏸ Agent visuel ${done.toLocaleString('fr-FR')}/${total?total.toLocaleString('fr-FR'):'…'} · ${pct}%`;
  else p.textContent=`🧠 Agent visuel ${done.toLocaleString('fr-FR')}/${total?total.toLocaleString('fr-FR'):'…'} · ${pct}%`;
  p.title=`V38 ${modelState}. ${state.visual} analyses IA · ${state.metadata} préclassements · ${state.technical} textures techniques.`;
}

async function runAgent(){
  if(agentRunning||agentPaused||state.completed||!db)return;agentRunning=true;ensurePill();
  try{
    let offset=Math.max(0,Number(state.offset||0));
    while(!agentPaused){
      while(document.hidden||Date.now()-lastActivity<USER_IDLE_MS){await sleep(400);if(agentPaused)return;}
      const p=new URLSearchParams({render_availability:'local-renderable',limit:String(PAGE),offset:String(offset)});
      const r=await fetch(API+'/search?'+p,{cache:'no-store'}),d=await r.json();if(!r.ok)throw new Error(d.message||d.error||'agent-search-failed');
      const list=d.items||[];state.total=Number(d.total||state.total||0);updatePill();
      if(!list.length){state.completed=true;state.offset=0;saveState();updatePill();break;}
      for(const a of list){
        if(agentPaused)return;while(document.hidden||Date.now()-lastActivity<USER_IDLE_MS)await sleep(350);
        if(!semanticMap.has(a.stable_id))await classifyAsset(a);
        state.scanned++;if(state.scanned%5===0){saveState();updatePill();}
        await sleep(ITEM_GAP_MS);
      }
      offset=Number(d.offset||offset)+list.length;state.offset=offset;saveState();updatePill();
      console.info('V38_VISUAL_AGENT_PROGRESS',semanticMap.size+'/'+state.total,'offset='+offset,'model='+modelState);
      if(!d.hasMore||offset>=state.total){state.completed=true;state.offset=0;saveState();updatePill();break;}
    }
  }catch(e){console.warn('V38_VISUAL_AGENT_ERROR',e);state.failed++;saveState();modelState=modelState==='loading'?'error':modelState;updatePill();setTimeout(()=>{agentRunning=false;if(!agentPaused)runAgent();},8000);return;}
  finally{agentRunning=false;}
}

function parseTerms(raw){
  const parser=window.WFGGMultiKeywordV372?.parse;if(parser)return parser(raw);
  const out=[];String(raw||'').replace(/"([^"]+)"|'([^']+)'|([^\s,;]+)/g,(_,a,b,c)=>{out.push(a||b||c);return _;});return out;
}
function semanticTerm(term){const n=norm(term);return TERM_ALIASES.get(n)||'';}
function semanticSpecsFromUi(){
  const terms=parseTerms(document.querySelector('#q')?.value||''),specs=[];
  for(const t of terms){const s=semanticTerm(t);if(s)specs.push(s);}
  if(advancedSpec)specs.push(advancedSpec);return [...new Set(specs)];
}
function recordTags(rec){
  if(!rec)return new Set();const s=new Set([rec.label,rec.category,rec.subtype]);
  for(const x of (rec.top||[]).slice(0,5))if(Number(x.score)>=.10)s.add(String(x.label));return s;
}
function specMatchRec(rec,spec){
  if(!rec)return false;if(minConfidence&&Number(rec.score||0)<minConfidence&&rec.source.startsWith('clip'))return false;
  const tags=recordTags(rec);if(tags.has(spec))return true;
  if(GROUPS[spec])return rec.category===spec;
  if(spec==='character')return rec.category==='character';if(spec==='portrait')return rec.subtype==='portrait'||tags.has('face portrait');
  if(spec==='ui')return rec.category==='ui';if(spec==='effect')return rec.category==='effect';if(spec==='texture')return rec.category==='texture';if(spec==='object')return rec.category==='object';
  if(spec==='environment')return rec.category==='environment';if(spec==='map')return tags.has('map terrain');
  return false;
}
function metadataSpecMatch(a,spec){
  const p=norm(pathOf(a)+' '+String(a?.family||'')+' '+String(a?.visual_role||'')+' '+String(a?.subject||''));
  const pats={vehicle:/\b(vehicle|cars?|tank|uav|drone|truck|car)\b/,tank:/\b(tank|armored|char)\b/,car:/\b(car|cars)\b/,truck:/\b(truck)\b/,drone:/\b(drone|uav)\b/,aircraft:/\b(aircraft|plane)\b/,helicopter:/\b(helicopter|helico)\b/,character:/\b(character|hero)\b/,weapon:/\b(weapon|gun|rifle|missile|turret)\b/,building:/\b(building|base|structure)\b/,ui:/\b(ui|icon|itemicon|badge)\b/,effect:/\b(effect|vfx|particle|explosion|smoke|fire)\b/,texture:/\b(texture|pbr|material|atlas|uv)\b/};
  return !!(pats[spec]?.test(p));
}
function assetMatchesSpecs(a,specs){
  if(!specs.length)return true;const rec=semanticMap.get(a?.stable_id);
  return specs.every(spec=>specMatchRec(rec,spec)||(!rec&&metadataSpecMatch(a,spec))||((rec?.source||'').startsWith('metadata')&&metadataSpecMatch(a,spec)));
}

function installAdvancedFilters(){
  const body=document.querySelector('#advancedDialog .modal-body');if(!body||document.querySelector('#visual_semantic_type'))return;
  const label=document.createElement('label');label.innerHTML='Type visuel IA<select id="visual_semantic_type"><option value="">Tous</option><option value="vehicle">Véhicules</option><option value="tank">Chars</option><option value="character">Personnages</option><option value="weapon">Armes</option><option value="building">Bâtiments</option><option value="ui">UI / icônes</option><option value="effect">Effets</option><option value="texture">Textures</option><option value="object">Objets</option><option value="environment">Décors</option></select>';
  const conf=document.createElement('label');conf.innerHTML='Confiance IA minimale<select id="visual_semantic_conf"><option value="0">Toutes</option><option value="0.35">35 %</option><option value="0.5">50 %</option><option value="0.65">65 %</option></select>';
  const note=body.querySelector('.modal-note');body.insertBefore(label,note||null);body.insertBefore(conf,note||null);
  label.querySelector('select').addEventListener('change',e=>{advancedSpec=e.target.value;});conf.querySelector('select').addEventListener('change',e=>{minConfidence=Number(e.target.value||0);});
}

function installSearchIntegration(){
  if(typeof params!=='function'||typeof preparePageItems!=='function')return false;
  if(params.__wfggV38)return true;
  const baseParams=params;params=function(){
    const p=baseParams(),terms=parseTerms(document.querySelector('#q')?.value||'');
    const semanticIndexes=new Set();terms.forEach((t,i)=>{if(semanticTerm(t))semanticIndexes.add(i);});
    searchSpecs=semanticSpecsFromUi();
    if(!semanticIndexes.size&&!advancedSpec)return p;
    const lexical=terms.filter((_,i)=>!semanticIndexes.has(i));
    const resolver=window.WFGGSearchCorrelation?.resolveHeroQuery;const heroIdx=new Set();
    if(typeof resolver==='function')lexical.forEach((t,i)=>{if(resolver(t))heroIdx.add(i);});
    const lexicalNoHero=lexical.filter((_,i)=>!heroIdx.has(i));
    p.delete('q');p.delete('keywords');if(lexicalNoHero.length)p.set('keywords',lexicalNoHero.map(x=>/\s/.test(x)?'"'+x+'"':x).join(' '));
    return p;
  };params.__wfggV38=true;
  const basePrepare=preparePageItems;preparePageItems=function(raw){const base=basePrepare(raw);const specs=semanticSpecsFromUi();searchSpecs=specs;return specs.length?base.filter(a=>assetMatchesSpecs(a,specs)):base;};
  if(typeof activeFilters==='function'){
    const baseActive=activeFilters;activeFilters=function(){const out=baseActive();const specs=semanticSpecsFromUi();if(specs.length)out.unshift({id:'visual_semantic',label:'IA visuelle '+specs.join(' + ')});return out;};
  }
  return true;
}

function cardBadge(rec){
  if(!rec)return '';const pct=Math.round(Number(rec.score||0)*100);const prefix=rec.source.startsWith('clip')?'🧠':'◇';
  const label=(rec.category==='vehicle'&&rec.subtype!=='vehicle'?rec.subtype:rec.category)||rec.label;
  return `${prefix} ${label} · ${pct}%`;
}
function installCardBadges(){
  if(typeof renderList!=='function'||renderList.__wfggV38)return false;const base=renderList;
  renderList=function(){base();const cards=[...document.querySelectorAll('#results .card')];cards.forEach((card,i)=>{const a=items[i],rec=semanticMap.get(a?.stable_id);if(!rec||card.querySelector('[data-v38-sem]'))return;const s=document.createElement('span');s.dataset.v38Sem='1';s.className='avail';s.textContent=cardBadge(rec);s.title=`${rec.label} · source ${rec.source}`;card.appendChild(s);});};renderList.__wfggV38=true;return true;
}
function installMetaBadge(){
  if(typeof renderMeta!=='function'||renderMeta.__wfggV38)return false;const base=renderMeta;
  renderMeta=function(a,m=null){base(a,m);const rec=semanticMap.get(a?.stable_id),meta=document.querySelector('#meta');if(rec&&meta&&!meta.querySelector('[data-v38-sem]')){const s=document.createElement('div');s.dataset.v38Sem='1';s.className='meta-block';s.innerHTML=`<b>Analyse visuelle IA</b><br>${esc(rec.category)} · ${esc(rec.subtype)} · ${Math.round(rec.score*100)} %<br><span class="hint">${esc(rec.source)}</span>`;meta.appendChild(s);}};renderMeta.__wfggV38=true;return true;
}

let visibleTimer=0;
async function classifyCurrentVisible(){
  const a=window.currentAsset||currentAsset;if(!a?.stable_id)return;const existing=semanticMap.get(a.stable_id);if(existing?.source?.startsWith('clip')&&existing.score>=.2)return;
  const stage=document.querySelector('#stage');if(!stage)return;
  const canvas=stage.querySelector('.v33modelcanvas,canvas');const img=stage.querySelector('#assetImg,img');
  try{
    if(canvas&&canvas.width&&canvas.height){
      const blob=await new Promise(res=>canvas.toBlob(res,'image/png'));if(blob){await classifyBlob(a,blob,'clip-current-3d');renderList?.();renderMeta?.(a,currentRenderMeta||null);updatePill();return;}
    }
    if(img?.src){const r=await fetch(img.src,{cache:'force-cache'});if(r.ok){await classifyBlob(a,await r.blob(),'clip-current-2d');renderList?.();renderMeta?.(a,currentRenderMeta||null);updatePill();}}
  }catch(e){console.debug('V38_CURRENT_VISIBLE_FAIL',a.stable_id,e);}
}
function installStageObserver(){
  const stage=document.querySelector('#stage');if(!stage||stage.dataset.v38Observer)return;stage.dataset.v38Observer='1';
  new MutationObserver(()=>{clearTimeout(visibleTimer);visibleTimer=setTimeout(classifyCurrentVisible,900);}).observe(stage,{childList:true,subtree:true});
}

async function boot(){
  try{db=await openDb();await loadAllRecords();}catch(e){console.warn('V38_IDB_FAIL',e);return;}
  ensurePill();installAdvancedFilters();
  const install=()=>{const a=installSearchIntegration(),b=installCardBadges(),c=installMetaBadge();installAdvancedFilters();installStageObserver();if(!(a&&b&&c))setTimeout(install,180);};install();
  document.addEventListener('pointerdown',()=>{lastActivity=Date.now();},{passive:true});document.addEventListener('keydown',()=>{lastActivity=Date.now();},{passive:true});
  window.WFGGVisualAgentV38={version:VERSION,state:()=>({...state,indexed:semanticMap.size,paused:agentPaused,modelState}),pause:()=>{agentPaused=true;updatePill();},resume:()=>{agentPaused=false;updatePill();runAgent();},get:id=>semanticMap.get(id)||null,match:assetMatchesSpecs,reclassifyCurrent:classifyCurrentVisible};
  console.info('V38_VISUAL_AGENT ready indexed='+semanticMap.size+' model='+MODEL+' webgpu='+(navigator.gpu?'YES':'NO'));
  setTimeout(()=>{if(!agentPaused)runAgent();},MODEL_DELAY_MS);
}
boot();
})();
