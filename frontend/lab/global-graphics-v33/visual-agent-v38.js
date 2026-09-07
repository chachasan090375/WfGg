(()=>{
'use strict';

/* WfGg V38.1 — resilient hierarchical on-device visual agent.
   - Robust Transformers.js loader with stable/current/legacy CDN fallbacks.
   - Two-stage CLIP taxonomy: broad category -> specialised subtype.
   - Second enrichment phase adds view/style attributes after the useful base index exists.
   - Cheap image heuristics add dominant colour/aspect/transparency without extra AI passes.
   - Technical textures/sheets are rejected deterministically before expensive inference.
   - Visual records live only in IndexedDB; original Last War files are never modified.
   - A failed model load never poisons the index with fake semantic classifications.
*/

const VERSION='38.1';
const API='/api/v33';
const DB_NAME='wfgg-visual-agent-v381';
const DB_VERSION=1;
const STORE='semantics';
const STATE_KEY='wfgg-visual-agent-v381-state';
const PAGE=64;
const MODEL='Xenova/clip-vit-base-patch32';
const MODEL_DELAY_MS=1800;
const ITEM_GAP_MS=110;
const USER_IDLE_MS=850;
const RETRY_MS=15000;

// Official stable first. The old V38 pointed only to a single 4.2.0 CDN URL: if that import failed,
// the whole agent was declared unavailable. V38.1 deliberately has several independent fallbacks.
const TRANSFORMERS_SOURCES=[
  {url:'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1',kind:'modern',name:'HF 3.8.1'},
  {url:'https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.0.1',kind:'modern',name:'HF 4.0.1'},
  {url:'https://cdn.jsdelivr.net/npm/@huggingface/transformers',kind:'modern',name:'HF current'},
  {url:'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2',kind:'legacy',name:'Xenova 2.17.2'}
];

const PRIMARY=[
  ['vehicle','game vehicle'],['character','game character or person'],['animal','animal'],['vegetation','plant or vegetation'],
  ['weapon','weapon'],['building','building or structure'],['environment','environment or scenery'],['ui','user interface element'],
  ['effect','visual effect'],['texture','texture or material map'],['object','game item or prop'],['resource','resource or currency'],
  ['logo','logo, symbol or text'],['map','map or terrain'],['food','food or drink'],['other','other game object']
];
const PRIMARY_LABELS=PRIMARY.map(x=>x[1]);
const PRIMARY_TO_CATEGORY=new Map(PRIMARY.map(x=>[x[1],x[0]]));

// ~150 useful subtypes, but an image is compared only with the small list for its primary category.
const SUBTYPES={
  vehicle:['tank','armored fighting vehicle','military truck','civilian car','pickup truck','motorcycle','bicycle','drone','airplane','helicopter','boat or ship','train','artillery vehicle','construction vehicle','rocket launcher vehicle','other vehicle'],
  character:['human soldier','human civilian','hero character','face portrait','full body character','robot character','zombie or undead','monster creature','cartoon character','armored character','female character','male character','other character'],
  animal:['dog','cat','horse','bird','fish','insect','reptile','wild mammal','farm animal','fantasy animal','other animal'],
  vegetation:['flower','tree','grass','bush or shrub','leaf','crop plant','mushroom','vine','aquatic plant','other plant'],
  weapon:['rifle','pistol','machine gun','shotgun','sniper rifle','cannon','missile','rocket','turret','grenade','sword','knife','shield','ammunition','other weapon'],
  building:['military base','tower','house','factory','bunker','wall','gate','bridge','warehouse','monument','tent','platform','other building'],
  environment:['city scenery','forest scenery','desert scenery','snow scenery','mountain scenery','water or ocean','road','sky','ground surface','interior room','battlefield scenery','background scenery','other environment'],
  ui:['game icon','button','badge','frame','panel','menu','portrait icon','currency icon','progress bar','map icon','notification marker','text label','decorative UI','other interface element'],
  effect:['explosion','smoke','fire','lightning','glow','spark particles','dust particles','projectile trail','impact effect','energy effect','healing effect','weather effect','other visual effect'],
  texture:['texture atlas','UV texture map','sprite sheet','albedo or diffuse texture','normal map','roughness map','metallic map','mask texture','emission texture','environment texture','other texture'],
  object:['equipment item','crate','chest','furniture','tool','machine','collectible item','container','sign','lamp','wheel','mechanical part','decoration prop','toy','other prop'],
  resource:['coin currency','gem currency','energy resource','wood resource','metal resource','fuel resource','food resource','water resource','ticket token','medal token','card item','resource bundle','other resource'],
  logo:['game logo','faction emblem','military insignia','number or digits','written text','warning symbol','other symbol'],
  map:['world map','battle map','minimap','terrain tile','road map','building layout','isometric map','other map'],
  food:['meal','fruit','vegetable food','meat food','drink','bottle','can','snack','other food'],
  other:['mechanical object','organic object','geometric shape','container object','decorative object','unknown object']
};

const DEEP_LABELS=[
  'front view','side view','rear view','top-down view','isometric view','three-quarter view','close-up view','full object view',
  '3D rendered model','2D illustration','flat game icon','technical sheet','military style','futuristic style','damaged object','glowing object'
];

const ALIAS=new Map();
function aliases(spec,words){for(const w of words)ALIAS.set(norm(w),spec);}
aliases('category:vehicle',['vehicle','vehicles','véhicule','vehicule','véhicules','vehicules']);
aliases('subtype:tank',['tank','tanks','char','chars']);
aliases('subtype:armored fighting vehicle',['armored','armoured','blindé','blinde','blindes','blindés']);
aliases('subtype:civilian car',['car','cars','voiture','voitures']);aliases('subtype:military truck',['truck','camion','camions']);
aliases('subtype:drone',['drone','drones','uav']);aliases('subtype:airplane',['aircraft','plane','avion','avions']);aliases('subtype:helicopter',['helicopter','hélicoptère','helicoptere','hélico','helico']);
aliases('category:character',['character','characters','personnage','personnages','hero','héros','heros']);aliases('subtype:face portrait',['portrait','face','visage']);aliases('subtype:robot character',['robot','robots']);aliases('subtype:zombie or undead',['zombie','undead','mort-vivant']);
aliases('category:animal',['animal','animals','animaux']);aliases('subtype:dog',['dog','chien']);aliases('subtype:cat',['cat','chat']);aliases('subtype:bird',['bird','oiseau']);
aliases('category:vegetation',['plant','plants','plante','plantes','vegetation','végétation']);aliases('subtype:flower',['flower','flowers','fleur','fleurs']);aliases('subtype:tree',['tree','trees','arbre','arbres']);aliases('subtype:grass',['grass','herbe']);aliases('subtype:bush or shrub',['bush','shrub','buisson']);aliases('subtype:mushroom',['mushroom','champignon']);
aliases('category:weapon',['weapon','weapons','arme','armes']);aliases('subtype:rifle',['rifle','fusil']);aliases('subtype:pistol',['pistol','pistolet']);aliases('subtype:cannon',['cannon','canon']);aliases('subtype:missile',['missile','missiles']);aliases('subtype:turret',['turret','tourelle']);
aliases('category:building',['building','buildings','bâtiment','batiment','bâtiments','batiments','structure']);aliases('subtype:military base',['base']);aliases('subtype:tower',['tower','tour']);aliases('subtype:factory',['factory','usine']);aliases('subtype:bunker',['bunker']);
aliases('category:environment',['environment','environnement','scenery','décor','decor']);aliases('subtype:forest scenery',['forest','forêt','foret']);aliases('subtype:desert scenery',['desert','désert']);aliases('subtype:snow scenery',['snow','neige']);aliases('subtype:water or ocean',['water','eau','ocean','océan']);
aliases('category:ui',['ui','interface']);aliases('subtype:game icon',['icon','icons','icone','icône','icones','icônes']);aliases('subtype:button',['button','bouton']);aliases('subtype:badge',['badge']);
aliases('category:effect',['effect','effects','effet','effets','vfx']);aliases('subtype:explosion',['explosion']);aliases('subtype:smoke',['smoke','fumée','fumee']);aliases('subtype:fire',['fire','feu']);aliases('subtype:lightning',['lightning','éclair','eclair']);
aliases('category:texture',['texture','textures','material','matériau','materiau']);aliases('subtype:texture atlas',['atlas']);aliases('subtype:UV texture map',['uv']);aliases('subtype:sprite sheet',['sprite','spritesheet','sprite-sheet']);aliases('subtype:normal map',['normalmap','normal-map']);
aliases('category:object',['object','objet','item','prop']);aliases('subtype:crate',['crate','caisse']);aliases('subtype:chest',['chest','coffre']);aliases('subtype:machine',['machine']);
aliases('category:resource',['resource','ressource','currency','monnaie']);aliases('subtype:coin currency',['coin','pièce','piece']);aliases('subtype:gem currency',['gem','gemme']);aliases('subtype:energy resource',['energy','énergie','energie']);
aliases('category:logo',['logo','symbol','symbole','text','texte']);aliases('category:map',['map','carte','terrain']);aliases('category:food',['food','nourriture','drink','boisson']);
for(const c of ['red','orange','yellow','green','cyan','blue','purple','pink','brown','white','gray','black']){
  const fr={red:'rouge',orange:'orange',yellow:'jaune',green:'vert',cyan:'cyan',blue:'bleu',purple:'violet',pink:'rose',brown:'marron',white:'blanc',gray:'gris',black:'noir'}[c];aliases('attr:color:'+c,[c,fr]);
}
aliases('deep:front view',['front','face','vue-face']);aliases('deep:side view',['side','profil','profile']);aliases('deep:rear view',['rear','arrière','arriere']);aliases('deep:top-down view',['top','dessus','top-down']);aliases('deep:isometric view',['isometric','isométrique','isometrique']);

let db=null,semanticMap=new Map(),classifier=null,classifierPromise=null,agentPill=null;
let agentPaused=false,agentRunning=false,modelState='idle',modelError='',modelSource='',modelProgress=0,lastActivity=Date.now();
let advancedSpec='',minConfidence=0,visibleTimer=0;
let state={version:VERSION,model:MODEL,phase:'base',offset:0,total:0,scanned:0,visual:0,deep:0,technical:0,provisional:0,failed:0,completed:false};

function norm(s){return String(s??'').trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const pathOf=a=>String(a?.asset_path||a?.logical_name||a?.alias_name||'').replace(/\\/g,'/').toLowerCase();
const dimOf=a=>String(a?.dimension_class||'').toLowerCase();
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function loadState(){try{const x=JSON.parse(localStorage.getItem(STATE_KEY)||'{}');if(x?.version===VERSION&&x?.model===MODEL)state={...state,...x};}catch{}}
function saveState(){try{localStorage.setItem(STATE_KEY,JSON.stringify(state));}catch{}}
loadState();

function openDb(){return new Promise((resolve,reject)=>{const req=indexedDB.open(DB_NAME,DB_VERSION);req.onupgradeneeded=()=>{const d=req.result;if(!d.objectStoreNames.contains(STORE))d.createObjectStore(STORE,{keyPath:'stable_id'});};req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error||new Error('IndexedDB unavailable'));});}
function loadAllRecords(){return new Promise((resolve,reject)=>{const tx=db.transaction(STORE,'readonly'),req=tx.objectStore(STORE).getAll();req.onsuccess=()=>{for(const r of (req.result||[]))semanticMap.set(r.stable_id,r);resolve(req.result||[]);};req.onerror=()=>reject(req.error);});}
function putRecord(rec){semanticMap.set(rec.stable_id,rec);return new Promise((resolve,reject)=>{const tx=db.transaction(STORE,'readwrite');tx.objectStore(STORE).put(rec);tx.oncomplete=()=>resolve(rec);tx.onerror=()=>reject(tx.error);});}

function technicalRule(a){
  const p=pathOf(a),tail=p.split('/').pop()||'';
  if(/\/animation\//.test(p)||p.endsWith('.anim'))return {category:'other',subtype:'animation component',label:'animation component'};
  if(/\/(textures?|pbr|materials?)\//.test(p)||/(?:^|[_-])(normal|nrm|albedo|diffuse|basecolor|rough|metal|spec|mask|ao|emiss)(?:[_-]|\.)/.test(tail))return {category:'texture',subtype:'material texture',label:'material texture'};
  if(/\/(uv|atlas)\//.test(p)||/sprite.?sheet|spritesheet|flipbook/.test(p))return {category:'texture',subtype:'sprite sheet',label:'sprite sheet'};
  return null;
}
function metadataProvisional(a){
  const p=norm(pathOf(a)+' '+String(a?.family||'')+' '+String(a?.visual_role||'')+' '+String(a?.subject||''));
  const checks=[
    [/\b(tank|armored|blinde)\b/,'vehicle','tank'],[/\b(vehicle|cars?|uav|drone|truck)\b/,'vehicle','other vehicle'],[/\b(character|hero|audie|murphy)\b/,'character','hero character'],
    [/\b(weapon|gun|rifle|missile|turret)\b/,'weapon','other weapon'],[/\b(building|base|bunker|factory)\b/,'building','other building'],[/\b(icon|itemicon|badge|ui)\b/,'ui','game icon'],[/\b(explosion|smoke|fire|effect|vfx|particle)\b/,'effect','other visual effect']
  ];
  for(const [re,category,subtype] of checks)if(re.test(p))return {category,subtype,label:subtype};
  return {category:'other',subtype:'unknown object',label:'other game object'};
}
function recordBase(a,category,subtype,score,source,extra={}){return {schema:2,stable_id:a.stable_id,category,subtype,label:subtype,score:Number(score||0),source,asset_path:String(a.asset_path||''),dimension:String(a.dimension_class||''),attributes:[],deep_labels:[],updated_at:Date.now(),...extra};}

async function importAndBuildClassifier(){
  let last=null;
  for(const src of TRANSFORMERS_SOURCES){
    try{
      console.info('V38_1_IMPORT_TRY',src.name,src.url);const mod=await import(src.url);
      if(mod.env){try{mod.env.allowLocalModels=false;mod.env.allowRemoteModels=true;}catch{}}
      const progress_callback=p=>{try{if(Number.isFinite(p?.progress)){modelProgress=Math.round(p.progress);updatePill();}}catch{}};
      const attempts=[];
      if(src.kind==='modern'){
        if(navigator.gpu)attempts.push({name:'webgpu-q8',options:{device:'webgpu',dtype:'q8',progress_callback}});
        attempts.push({name:'wasm-q8',options:{device:'wasm',dtype:'q8',progress_callback}});
        attempts.push({name:'wasm-default',options:{device:'wasm',progress_callback}});
      }else attempts.push({name:'wasm-legacy-quantized',options:{quantized:true,progress_callback}});
      for(const att of attempts){
        try{
          console.info('V38_1_PIPELINE_TRY',src.name,att.name);const pipe=await mod.pipeline('zero-shot-image-classification',MODEL,att.options);
          modelSource=src.name+' '+att.name;modelState=att.name.startsWith('webgpu')?'webgpu':'wasm';modelError='';modelProgress=100;updatePill();
          console.info('V38_1_MODEL_READY',modelSource);return pipe;
        }catch(e){last=e;console.warn('V38_1_PIPELINE_FAIL',src.name,att.name,String(e?.message||e));}
      }
    }catch(e){last=e;console.warn('V38_1_IMPORT_FAIL',src.name,String(e?.message||e));}
  }
  throw last||new Error('Aucune source Transformers.js disponible');
}
async function ensureClassifier(){
  if(classifier)return classifier;if(classifierPromise)return classifierPromise;
  modelState='loading';modelError='';modelProgress=0;updatePill();
  classifierPromise=importAndBuildClassifier().then(x=>(classifier=x,x)).catch(e=>{modelState='error';modelError=String(e?.message||e).slice(0,240);classifierPromise=null;updatePill();throw e;});
  return classifierPromise;
}

function topN(out,n=5){return (out||[]).slice(0,n).map(x=>({label:String(x.label),score:Number(x.score)}));}
async function clip(url,labels,template){const pipe=await ensureClassifier();return await pipe(url,labels,{hypothesis_template:template});}
function categoryFromPrimary(label){return PRIMARY_TO_CATEGORY.get(String(label))||'other';}

function colorName(r,g,b){
  const max=Math.max(r,g,b),min=Math.min(r,g,b),d=max-min,light=(max+min)/510;if(max<38)return 'black';if(min>220&&d<25)return 'white';if(d<24)return 'gray';
  let h=0;if(d){if(max===r)h=((g-b)/d)%6;else if(max===g)h=(b-r)/d+2;else h=(r-g)/d+4;h*=60;if(h<0)h+=360;}
  if(light<.28&&h>15&&h<55)return 'brown';if(h<15||h>=345)return 'red';if(h<45)return 'orange';if(h<70)return 'yellow';if(h<165)return 'green';if(h<195)return 'cyan';if(h<255)return 'blue';if(h<300)return 'purple';if(h<345)return 'pink';return 'red';
}
async function cheapVisualAttributes(blob){
  try{
    const bmp=await createImageBitmap(blob),w=bmp.width,h=bmp.height,c=document.createElement('canvas');c.width=32;c.height=32;const x=c.getContext('2d',{willReadFrequently:true});x.drawImage(bmp,0,0,32,32);bmp.close?.();const d=x.getImageData(0,0,32,32).data;
    let rs=0,gs=0,bs=0,n=0,transparent=0;for(let i=0;i<d.length;i+=4){if(d[i+3]<40){transparent++;continue;}const lum=.299*d[i]+.587*d[i+1]+.114*d[i+2];if(lum<10)continue;rs+=d[i];gs+=d[i+1];bs+=d[i+2];n++;}
    const attrs=[];if(n)attrs.push('color:'+colorName(rs/n,gs/n,bs/n));const ar=w/Math.max(1,h);attrs.push(ar>1.35?'wide':ar<.74?'tall':'square-ish');if(transparent>180)attrs.push('transparent-background');return attrs;
  }catch{return [];}
}

async function classifyBlob(a,blob,source='clip-raster',deep=false){
  const attrs=await cheapVisualAttributes(blob),u=URL.createObjectURL(blob);
  try{
    const prim=await clip(u,PRIMARY_LABELS,'This game image mainly shows {}.');const bestP=prim?.[0];if(!bestP)throw new Error('classification primaire vide');
    const category=categoryFromPrimary(bestP.label),subs=SUBTYPES[category]||SUBTYPES.other;
    const sub=await clip(u,subs,'This game image shows {}.');const bestS=sub?.[0]||{label:subs[0],score:0};
    const combined=.42*Number(bestP.score||0)+.58*Number(bestS.score||0);
    const rec=recordBase(a,category,String(bestS.label),combined,source,{primary_label:String(bestP.label),primary_score:Number(bestP.score||0),top_primary:topN(prim,5),top_subtypes:topN(sub,6),attributes:attrs,deep_done:false});
    if(deep){const out=await clip(u,DEEP_LABELS,'This game asset is shown as {}.');rec.deep_labels=topN(out,5);rec.deep_done=true;for(const z of rec.deep_labels.slice(0,3))if(z.score>=.16)rec.attributes.push('deep:'+z.label);}
    await putRecord(rec);state.visual++;if(deep)state.deep++;return rec;
  }finally{URL.revokeObjectURL(u);}
}

function is3D(a){const d=dimOf(a),p=pathOf(a);return d==='3d'||d.includes('composant 3d')||p.endsWith('.prefab')||p.endsWith('.fbx');}
async function fetchRenderBlob(a,timeout=35000){
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),timeout);try{const r=await fetch(API+'/render?id='+encodeURIComponent(a.stable_id),{signal:ctl.signal,cache:'force-cache'});if(!r.ok)throw new Error('render '+r.status);const b=await r.blob();if(!b.size)throw new Error('empty-render');return b;}finally{clearTimeout(timer);}
}
async function classifyAsset(a,deep=false){
  if(!a?.stable_id)return null;const existing=semanticMap.get(a.stable_id);
  if(existing&&(!deep||existing.deep_done))return existing;
  const tech=technicalRule(a);if(tech){if(!existing){const rec=recordBase(a,tech.category,tech.subtype,.99,'technical-rule',{deep_done:true});await putRecord(rec);state.technical++;return rec;}return existing;}
  if(is3D(a)){
    if(!existing){const m=metadataProvisional(a),rec=recordBase(a,m.category,m.subtype,.24,'metadata-provisional',{deep_done:false,provisional:true});await putRecord(rec);state.provisional++;return rec;}return existing;
  }
  let blob;try{blob=await fetchRenderBlob(a);}catch(e){if(!existing){const m=metadataProvisional(a),rec=recordBase(a,m.category,m.subtype,.18,'metadata-render-failed',{deep_done:false,provisional:true,error:String(e?.message||e).slice(0,120)});await putRecord(rec);state.provisional++;return rec;}return existing;}
  // If CLIP/model loading fails here, propagate the error. Do not save a fake semantic answer.
  return await classifyBlob(a,blob,deep?'clip-deep-raster':'clip-raster',deep);
}

function ensurePill(){
  if(agentPill?.isConnected)return agentPill;const bar=document.querySelector('.bar');if(!bar)return null;agentPill=document.createElement('button');agentPill.type='button';agentPill.className='pill';
  agentPill.onclick=()=>{if(modelState==='error'){classifier=null;classifierPromise=null;modelState='idle';modelError='';agentPaused=false;updatePill();runAgent();return;}agentPaused=!agentPaused;updatePill();if(!agentPaused)runAgent();};bar.appendChild(agentPill);updatePill();return agentPill;
}
function updatePill(){
  const p=ensurePill();if(!p)return;const total=state.total||0,done=semanticMap.size,pct=total?Math.min(100,Math.round(done*100/total)):0,phase=state.phase==='deep'?'enrichissement':'indexation';
  if(modelState==='loading'){p.textContent='🧠 Agent visuel · chargement IA'+(modelProgress?` ${modelProgress}%`:'…');p.title='Téléchargement/initialisation de CLIP';return;}
  if(modelState==='error'){p.textContent=`🧠 Index visuel ${done.toLocaleString('fr-FR')} · IA indisponible`;p.title='Touchez pour réessayer. '+modelError;return;}
  if(state.completed)p.textContent=`🧠 Index visuel ${done.toLocaleString('fr-FR')} · enrichi`;
  else if(agentPaused)p.textContent=`⏸ Agent visuel ${done.toLocaleString('fr-FR')}/${total?total.toLocaleString('fr-FR'):'…'} · ${pct}%`;
  else p.textContent=`🧠 Agent ${phase} ${done.toLocaleString('fr-FR')}/${total?total.toLocaleString('fr-FR'):'…'} · ${pct}%`;
  p.title=`V${VERSION} ${modelState}${modelSource?' · '+modelSource:''}. ${state.visual} analyses CLIP · ${state.deep} enrichies · ${state.technical} techniques · phase ${state.phase}.`;
}

async function runAgent(){
  if(agentRunning||agentPaused||state.completed||!db)return;agentRunning=true;ensurePill();
  try{
    let offset=Math.max(0,Number(state.offset||0));
    while(!agentPaused){
      while(document.hidden||Date.now()-lastActivity<USER_IDLE_MS){await sleep(350);if(agentPaused)return;}
      const p=new URLSearchParams({render_availability:'local-renderable',limit:String(PAGE),offset:String(offset)});const r=await fetch(API+'/search?'+p,{cache:'no-store'}),d=await r.json();if(!r.ok)throw new Error(d.message||d.error||'agent-search-failed');
      const list=d.items||[];state.total=Number(d.total||state.total||0);updatePill();
      if(!list.length){if(state.phase==='base'){state.phase='deep';state.offset=0;offset=0;saveState();updatePill();continue;}state.completed=true;state.offset=0;saveState();updatePill();break;}
      for(const a of list){
        if(agentPaused)return;while(document.hidden||Date.now()-lastActivity<USER_IDLE_MS)await sleep(300);
        const rec=semanticMap.get(a.stable_id);
        if(state.phase==='base'){if(!rec)await classifyAsset(a,false);}else if(rec?.source?.startsWith('clip')&&!rec.deep_done)await classifyAsset(a,true);
        state.scanned++;if(state.scanned%4===0){saveState();updatePill();}await sleep(ITEM_GAP_MS);
      }
      offset=Number(d.offset||offset)+list.length;state.offset=offset;saveState();updatePill();
      console.info('V38_1_AGENT_PROGRESS','phase='+state.phase,semanticMap.size+'/'+state.total,'offset='+offset,'model='+modelState,modelSource);
      if(!d.hasMore||offset>=state.total){if(state.phase==='base'){state.phase='deep';state.offset=0;offset=0;saveState();updatePill();}else{state.completed=true;state.offset=0;saveState();updatePill();break;}}
    }
  }catch(e){state.failed++;modelError=String(e?.message||e).slice(0,240);if(/transform|onnx|model|pipeline|import|wasm|webgpu|fetch/i.test(modelError))modelState='error';saveState();updatePill();console.warn('V38_1_AGENT_ERROR',e);setTimeout(()=>{agentRunning=false;if(!agentPaused&&modelState!=='error')runAgent();},RETRY_MS);return;}
  finally{agentRunning=false;}
}

function parseTerms(raw){const parser=window.WFGGMultiKeywordV372?.parse;if(parser)return parser(raw);const out=[];String(raw||'').replace(/"([^"]+)"|'([^']+)'|([^\s,;]+)/g,(_,a,b,c)=>{out.push(a||b||c);return _;});return out;}
function semanticSpec(term){return ALIAS.get(norm(term))||'';}
function uiSpecs(){const specs=[];for(const t of parseTerms(document.querySelector('#q')?.value||'')){const s=semanticSpec(t);if(s)specs.push(s);}if(advancedSpec)specs.push(advancedSpec);return [...new Set(specs)];}
function recordTags(rec){const out=new Set([rec?.category,rec?.subtype]);for(const x of rec?.top_subtypes||[])if(x.score>=.12)out.add(x.label);for(const a of rec?.attributes||[])out.add(a);for(const d of rec?.deep_labels||[])if(d.score>=.14)out.add('deep:'+d.label);return out;}
function specMatch(rec,spec){
  if(!rec)return false;if(minConfidence&&rec.source.startsWith('clip')&&Number(rec.score||0)<minConfidence)return false;const tags=recordTags(rec),[kind,...rest]=spec.split(':'),value=rest.join(':');
  if(kind==='category')return rec.category===value;if(kind==='subtype')return rec.subtype===value||tags.has(value);if(kind==='attr')return tags.has(value);if(kind==='deep')return tags.has('deep:'+value);return false;
}
function metadataMatch(a,spec){const m=metadataProvisional(a),[k,...r]=spec.split(':'),v=r.join(':');if(k==='category')return m.category===v;if(k==='subtype')return m.subtype===v;return false;}
function assetMatches(a,specs){if(!specs.length)return true;const rec=semanticMap.get(a?.stable_id);return specs.every(s=>specMatch(rec,s)||(!rec&&metadataMatch(a,s))||(rec?.provisional&&metadataMatch(a,s)));}

function installAdvancedFilters(){
  const body=document.querySelector('#advancedDialog .modal-body');if(!body||document.querySelector('#visual_semantic_type'))return;
  const lab=document.createElement('label');lab.innerHTML='Type visuel IA<select id="visual_semantic_type"><option value="">Tous</option><option value="category:vehicle">Véhicules</option><option value="subtype:tank">Chars</option><option value="category:character">Personnages</option><option value="category:animal">Animaux</option><option value="category:vegetation">Végétation</option><option value="subtype:flower">Fleurs</option><option value="category:weapon">Armes</option><option value="category:building">Bâtiments</option><option value="category:environment">Décors</option><option value="category:ui">UI / icônes</option><option value="category:effect">Effets</option><option value="category:texture">Textures</option><option value="category:object">Objets</option><option value="category:resource">Ressources</option><option value="category:map">Cartes / terrain</option></select>';
  const conf=document.createElement('label');conf.innerHTML='Confiance IA minimale<select id="visual_semantic_conf"><option value="0">Toutes</option><option value="0.30">30 %</option><option value="0.45">45 %</option><option value="0.60">60 %</option><option value="0.75">75 %</option></select>';
  const note=body.querySelector('.modal-note');body.insertBefore(lab,note||null);body.insertBefore(conf,note||null);lab.querySelector('select').onchange=e=>{advancedSpec=e.target.value;};conf.querySelector('select').onchange=e=>{minConfidence=Number(e.target.value||0);};
}
function installSearchIntegration(){
  if(typeof params!=='function'||typeof preparePageItems!=='function')return false;if(params.__wfggV381)return true;
  const baseParams=params;params=function(){const p=baseParams(),terms=parseTerms(document.querySelector('#q')?.value||''),semIdx=new Set();terms.forEach((t,i)=>{if(semanticSpec(t))semIdx.add(i);});if(!semIdx.size&&!advancedSpec)return p;const lexical=terms.filter((_,i)=>!semIdx.has(i));const resolver=window.WFGGSearchCorrelation?.resolveHeroQuery,heroIdx=new Set();if(typeof resolver==='function')lexical.forEach((t,i)=>{if(resolver(t))heroIdx.add(i);});const rest=lexical.filter((_,i)=>!heroIdx.has(i));p.delete('q');p.delete('keywords');if(rest.length)p.set('keywords',rest.map(x=>/\s/.test(x)?'"'+x+'"':x).join(' '));return p;};params.__wfggV381=true;
  const basePrepare=preparePageItems;preparePageItems=function(raw){const base=basePrepare(raw),specs=uiSpecs();return specs.length?base.filter(a=>assetMatches(a,specs)):base;};
  if(typeof activeFilters==='function'){const bf=activeFilters;activeFilters=function(){const o=bf(),specs=uiSpecs();if(specs.length)o.unshift({id:'visual_semantic',label:'IA visuelle '+specs.map(s=>s.split(':').slice(1).join(':')).join(' + ')});return o;};}
  return true;
}
function badge(rec){if(!rec)return '';const pct=Math.round(Number(rec.score||0)*100),p=rec.source.startsWith('clip')?'🧠':rec.source==='technical-rule'?'◆':'◇';return `${p} ${rec.subtype||rec.category} · ${pct}%`;}
function installCardBadges(){if(typeof renderList!=='function'||renderList.__wfggV381)return false;const base=renderList;renderList=function(){base();[...document.querySelectorAll('#results .card')].forEach((card,i)=>{const a=items[i],rec=semanticMap.get(a?.stable_id);if(!rec||card.querySelector('[data-v381-sem]'))return;const s=document.createElement('span');s.dataset.v381Sem='1';s.className='avail';s.textContent=badge(rec);s.title=`${rec.category} › ${rec.subtype} · ${rec.source}`;card.appendChild(s);});};renderList.__wfggV381=true;return true;}
function installMetaBadge(){if(typeof renderMeta!=='function'||renderMeta.__wfggV381)return false;const base=renderMeta;renderMeta=function(a,m=null){base(a,m);const rec=semanticMap.get(a?.stable_id),meta=document.querySelector('#meta');if(rec&&meta&&!meta.querySelector('[data-v381-sem]')){const top=(rec.top_subtypes||[]).slice(0,4).map(x=>`${esc(x.label)} ${Math.round(x.score*100)}%`).join(' · '),attrs=(rec.attributes||[]).slice(0,6).map(x=>esc(x.replace(/^color:/,''))).join(' · ');const s=document.createElement('div');s.dataset.v381Sem='1';s.className='meta-block';s.innerHTML=`<b>Analyse visuelle IA V38.1</b><br>${esc(rec.category)} › ${esc(rec.subtype)} · ${Math.round(rec.score*100)} %<br><span class="hint">${top||esc(rec.source)}${attrs?'<br>'+attrs:''}</span>`;meta.appendChild(s);}};renderMeta.__wfggV381=true;return true;}

async function classifyCurrentVisible(){
  const a=window.currentAsset||(typeof currentAsset!=='undefined'?currentAsset:null);if(!a?.stable_id)return;const stage=document.querySelector('#stage');if(!stage)return;
  const canvas=stage.querySelector('.v33modelcanvas,canvas'),img=stage.querySelector('#assetImg,img');
  try{
    let blob=null;if(canvas&&canvas.width&&canvas.height)blob=await new Promise(res=>canvas.toBlob(res,'image/png'));else if(img?.src){const r=await fetch(img.src,{cache:'force-cache'});if(r.ok)blob=await r.blob();}
    if(blob?.size){await classifyBlob(a,blob,is3D(a)?'clip-current-3d':'clip-current-2d',true);renderList?.();renderMeta?.(a,typeof currentRenderMeta!=='undefined'?currentRenderMeta:null);updatePill();}
  }catch(e){console.debug('V38_1_CURRENT_FAIL',a.stable_id,e);}
}
function installStageObserver(){const stage=document.querySelector('#stage');if(!stage||stage.dataset.v381Observer)return;stage.dataset.v381Observer='1';new MutationObserver(()=>{clearTimeout(visibleTimer);visibleTimer=setTimeout(classifyCurrentVisible,950);}).observe(stage,{childList:true,subtree:true});}

async function boot(){
  try{db=await openDb();await loadAllRecords();}catch(e){console.warn('V38_1_IDB_FAIL',e);return;}ensurePill();installAdvancedFilters();
  const install=()=>{const a=installSearchIntegration(),b=installCardBadges(),c=installMetaBadge();installAdvancedFilters();installStageObserver();if(!(a&&b&&c))setTimeout(install,180);};install();
  document.addEventListener('pointerdown',()=>{lastActivity=Date.now();},{passive:true});document.addEventListener('keydown',()=>{lastActivity=Date.now();},{passive:true});
  window.WFGGVisualAgentV38={version:VERSION,state:()=>({...state,indexed:semanticMap.size,paused:agentPaused,modelState,modelSource,modelError}),pause:()=>{agentPaused=true;updatePill();},resume:()=>{agentPaused=false;updatePill();runAgent();},get:id=>semanticMap.get(id)||null,match:assetMatches,reclassifyCurrent:classifyCurrentVisible,retryModel:()=>{classifier=null;classifierPromise=null;modelState='idle';modelError='';agentPaused=false;runAgent();}};
  console.info('V38_1_VISUAL_AGENT ready indexed='+semanticMap.size+' model='+MODEL+' webgpu='+(navigator.gpu?'YES':'NO')+' taxonomy=HIERARCHICAL deep-phase=ON');setTimeout(()=>{if(!agentPaused)runAgent();},MODEL_DELAY_MS);
}
boot();
})();
