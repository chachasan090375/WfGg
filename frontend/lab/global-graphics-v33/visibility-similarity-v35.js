(()=>{
'use strict';

/* V35 automatic preview audit + similar-image explorer.
   - Runs automatically while the viewer is open; no manual asset-by-asset validation.
   - Reuses WFGGSearchCorrelation.recordPreview so learned visibility immediately feeds filters.
   - Uses the existing server similarity index, then enriches/reranks 2D candidates against the
     currently displayed 2D/3D pixels when a canvas/image is available.
*/

const API35='/api/v33';
const AUDIT_STATE_KEY='wfgg-auto-preview-audit-v35';
const AUDIT_PAGE=120;
const AUDIT_CONCURRENCY=2;
const AUDIT_TIMEOUT_MS=45000;
const SIMILAR_MAX=900;
const SIMILAR_VISUAL_SAMPLE=160;
let auditPaused=false;
let auditRunning=false;
let auditState={offset:0,total:0,checked:0,visible2d:0,visible3d:0,nonautonomous:0,unavailable:0,completed:false};
let auditPill=null;
let similarMode=false;
let similarSource=null;
let similarityById=new Map();
let lastActivity=Date.now();

function corr(){return window.WFGGSearchCorrelation||null;}
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
function pathOf(a){return String(a?.asset_path||a?.logical_name||a?.alias_name||'').replace(/\\/g,'/').toLowerCase();}
function roleOf(a){return String(a?.model_role||'').toLowerCase();}
function techOf(a){return String(a?.tech_kind||'').toLowerCase();}
function dimOf(a){return String(a?.dimension_class||'');}
function isAnimation(a){const p=pathOf(a),r=roleOf(a),t=techOf(a);return p.includes('/animation/')||p.endsWith('.anim')||r==='animation'||t==='animation'||t==='animationclip';}
function isEffectPrefab(a){const p=pathOf(a);return (p.includes('/effect/')||p.includes('/effects/')||p.includes('/vfx/')||/(^|\/)(eff_|fx_|vfx_)/.test(p))&&(p.includes('/prefab/')||p.endsWith('.prefab'));}
function modelCandidate(a){
  const r=roleOf(a),d=dimOf(a),p=pathOf(a);
  if(['geometry','geometry-candidate','prefab'].includes(r))return true;
  if(d==='3D'&&!['material','shader','animation','component','texture'].includes(r))return true;
  if(d==='Mixte 2D/3D'&&!['material','shader'].includes(r))return true;
  if(d==='Composant 3D'&&(p.endsWith('.prefab')||p.includes('/prefab/'))&&!['material','shader','animation','texture'].includes(r))return true;
  return false;
}
function rasterCandidate(a){
  const d=dimOf(a),t=techOf(a),r=roleOf(a);
  return d==='2D'||d==='Mixte 2D/3D'||/sprite|texture|atlas|image|png|jpg|jpeg/.test(t)||['texture','material'].includes(r)||String(a?.graphic_class||'').toLowerCase().includes('graph');
}
function noMeshError(s){return /RUNTIME_3D_NO_STANDALONE_MESH|PTR3D_NO_MESH_POINTER|Aucune géométrie Mesh décodable|RUNTIME_3D_OBJECT_MISMATCH/i.test(String(s||''));}
function targetMissing(s){return /RUNTIME_TARGET_OBJECT_NOT_FOUND/i.test(String(s||''));}

function loadAuditState(){
  try{const x=JSON.parse(localStorage.getItem(AUDIT_STATE_KEY)||'{}');if(x&&typeof x==='object')auditState={...auditState,...x};}catch{}
}
function saveAuditState(){try{localStorage.setItem(AUDIT_STATE_KEY,JSON.stringify(auditState));}catch{}}
loadAuditState();

function ensureAuditPill(){
  if(auditPill?.isConnected)return auditPill;
  const bar=document.querySelector('.bar');if(!bar)return null;
  auditPill=document.createElement('button');auditPill.type='button';auditPill.className='pill';auditPill.style.cursor='pointer';auditPill.style.padding='5px 9px';
  auditPill.title='Audit automatique des aperçus. Appuyer pour pause/reprise.';
  auditPill.onclick=()=>{auditPaused=!auditPaused;updateAuditPill();};
  bar.appendChild(auditPill);updateAuditPill();return auditPill;
}
function updateAuditPill(){
  const p=ensureAuditPill();if(!p)return;
  const total=auditState.total||0,checked=auditState.checked||0;
  const pct=total?Math.min(100,Math.round(checked*100/total)):0;
  if(auditState.completed)p.textContent=`✓ Audit ${checked.toLocaleString('fr-FR')} · terminé`;
  else if(auditPaused)p.textContent=`⏸ Audit ${checked.toLocaleString('fr-FR')}/${total?total.toLocaleString('fr-FR'):'…'} · ${pct}%`;
  else p.textContent=`⚙ Audit auto ${checked.toLocaleString('fr-FR')}/${total?total.toLocaleString('fr-FR'):'…'} · ${pct}%`;
}

async function fetchJson(url,timeout=AUDIT_TIMEOUT_MS){
  const ctl=new AbortController();const timer=setTimeout(()=>ctl.abort(),timeout);
  try{const r=await fetch(url,{signal:ctl.signal,cache:'no-store'});let d={};try{d=await r.json();}catch{}return {ok:r.ok,status:r.status,data:d};}
  finally{clearTimeout(timer);}
}
async function checkRaster(a){
  const ctl=new AbortController();const timer=setTimeout(()=>ctl.abort(),AUDIT_TIMEOUT_MS);
  try{
    const r=await fetch(API35+'/render?id='+encodeURIComponent(a.stable_id),{signal:ctl.signal,cache:'no-store'});
    if(r.ok){try{await r.body?.cancel?.();}catch{}return {ok:true};}
    let d={};try{d=await r.json();}catch{}return {ok:false,error:d.message||d.error||('HTTP '+r.status)};
  }catch(e){return {ok:false,error:e?.name==='AbortError'?'AUDIT_TIMEOUT':String(e?.message||e)};}
  finally{clearTimeout(timer);}
}
function learn(a,status,mode,reason){
  try{corr()?.recordPreview?.(a,status,mode,reason);}catch{}
  auditState.checked++;
  if(status==='visible'&&mode==='2d')auditState.visible2d++;
  else if(status==='visible'&&mode==='3d')auditState.visible3d++;
  else if(status==='nonautonomous')auditState.nonautonomous++;
  else if(status==='unavailable')auditState.unavailable++;
}
async function auditOne(a){
  const known=corr()?.previewInfo?.(a);
  if(known?.verified){auditState.checked++;return;}
  if(isAnimation(a)){learn(a,'nonautonomous','','audit-animation');return;}
  if(a.render_availability==='global-index-only'){learn(a,'unavailable','','audit-source-absent');return;}
  let modelErr='';
  if(modelCandidate(a)){
    try{
      const m=await fetchJson(API35+'/model?id='+encodeURIComponent(a.stable_id));
      if(m.ok){learn(a,'visible','3d','audit-model-ok');return;}
      modelErr=String(m.data?.message||m.data?.error||('HTTP '+m.status));
    }catch(e){modelErr=String(e?.message||e);}
  }
  if(rasterCandidate(a)||modelCandidate(a)){
    const rr=await checkRaster(a);
    if(rr.ok){learn(a,'visible','2d',modelErr?'audit-raster-fallback':'audit-raster-ok');return;}
    const combined=modelErr+' '+String(rr.error||'');
    if((isEffectPrefab(a)&&(noMeshError(combined)||targetMissing(combined)))||isAnimation(a))learn(a,'nonautonomous','',combined.slice(0,150));
    else learn(a,'unavailable','',combined.slice(0,150)||'audit-no-preview');
    return;
  }
  learn(a,'nonautonomous','','audit-passive-component');
}

async function auditPage(raw){
  let next=0;
  async function worker(){
    while(true){
      const i=next++;if(i>=raw.length)return;
      while(auditPaused)await sleep(500);
      // Keep foreground browsing responsive when the user has just interacted.
      const wait=900-(Date.now()-lastActivity);if(wait>0)await sleep(wait);
      try{await auditOne(raw[i]);}catch(e){console.debug('V35_AUDIT_ITEM_ERROR',raw[i]?.stable_id,e);auditState.checked++;}
      if(auditState.checked%12===0){saveAuditState();updateAuditPill();}
    }
  }
  await Promise.all(Array.from({length:AUDIT_CONCURRENCY},()=>worker()));
}
async function runAutomaticAudit(){
  if(auditRunning||auditState.completed)return;
  auditRunning=true;ensureAuditPill();
  try{
    let offset=Math.max(0,Number(auditState.offset||0));
    while(true){
      while(auditPaused)await sleep(500);
      const u=new URLSearchParams({render_availability:'local-renderable',limit:String(AUDIT_PAGE),offset:String(offset)});
      const r=await fetch(API35+'/search?'+u,{cache:'no-store'}),d=await r.json();
      if(!r.ok)throw new Error(d.message||d.error||'audit search failed');
      const raw=d.items||[];auditState.total=Number(d.total||auditState.total||0);
      if(!raw.length){auditState.completed=true;auditState.offset=0;saveAuditState();updateAuditPill();break;}
      await auditPage(raw);
      offset=Number(d.offset||offset)+raw.length;auditState.offset=offset;saveAuditState();updateAuditPill();
      console.info('V35_AUTO_AUDIT_PROGRESS',auditState.checked+'/'+auditState.total,'sourceOffset='+offset);
      if(!d.hasMore||offset>=Number(d.total||0)){auditState.completed=true;auditState.offset=0;saveAuditState();updateAuditPill();break;}
      await sleep(80);
    }
  }catch(e){console.warn('V35_AUTO_AUDIT_PAUSED_BY_ERROR',e);saveAuditState();updateAuditPill();setTimeout(()=>{auditRunning=false;runAutomaticAudit();},5000);return;}
  finally{auditRunning=false;}
}

// --- Visual similarity helpers -------------------------------------------------
function sourceCanvas(){return currentModel?.canvas||document.querySelector('#stage .v33modelcanvas')||document.querySelector('#stage canvas')||null;}
async function canvasFromImageElement(img){
  const c=document.createElement('canvas');c.width=Math.max(1,img.naturalWidth||img.width||1);c.height=Math.max(1,img.naturalHeight||img.height||1);c.getContext('2d',{willReadFrequently:true}).drawImage(img,0,0,c.width,c.height);return c;
}
function popcountBigInt(x){let n=0;while(x){x&=x-1n;n++;}return n;}
function fingerprintCanvas(src){
  try{
    const w=src.width||src.clientWidth,h=src.height||src.clientHeight;if(!w||!h)return null;
    const c=document.createElement('canvas');c.width=9;c.height=8;const x=c.getContext('2d',{willReadFrequently:true});x.drawImage(src,0,0,9,8);
    const d=x.getImageData(0,0,9,8).data;let hash=0n,rs=0,gs=0,bs=0,count=0;
    const gray=(i)=>0.299*d[i]+0.587*d[i+1]+0.114*d[i+2];
    for(let y=0;y<8;y++)for(let xx=0;xx<8;xx++){const i=(y*9+xx)*4,j=i+4;hash=(hash<<1n)|(gray(i)>gray(j)?1n:0n);rs+=d[i];gs+=d[i+1];bs+=d[i+2];count++;}
    return {dh:hash.toString(16).padStart(16,'0'),rgb:[rs/count,gs/count,bs/count],aspect:w/h};
  }catch(e){console.debug('V35_FINGERPRINT_FAIL',e);return null;}
}
function visualScore(a,b){
  if(!a||!b)return null;
  let hd=32;try{hd=popcountBigInt(BigInt('0x'+a.dh)^BigInt('0x'+b.dh));}catch{}
  const hash=1-hd/64;
  const cd=Math.sqrt(a.rgb.reduce((s,v,i)=>s+(v-b.rgb[i])**2,0))/(Math.sqrt(3)*255),color=1-Math.min(1,cd);
  const ar=Math.exp(-Math.abs(Math.log(Math.max(.01,a.aspect)/Math.max(.01,b.aspect))));
  return .68*hash+.20*color+.12*ar;
}
async function fingerprintRenderedAsset(a){
  try{
    const r=await fetch(API35+'/render?id='+encodeURIComponent(a.stable_id),{cache:'force-cache'});if(!r.ok)return null;
    const blob=await r.blob();const bmp=await createImageBitmap(blob);const c=document.createElement('canvas');c.width=bmp.width;c.height=bmp.height;c.getContext('2d').drawImage(bmp,0,0);bmp.close?.();
    try{corr()?.recordPreview?.(a,'visible','2d','similarity-render-ok');}catch{}
    return fingerprintCanvas(c);
  }catch{return null;}
}

async function fetchAllSimilar(sid){
  const out=[],seen=new Set();let offset=0,total=Infinity;
  while(offset<total&&out.length<SIMILAR_MAX){
    const p=new URLSearchParams({similar_to:sid,render_availability:'local-renderable',limit:'120',offset:String(offset)});
    const r=await fetch(API35+'/search?'+p,{cache:'no-store'}),d=await r.json();if(!r.ok)throw new Error(d.message||d.error||'similarity search failed');
    total=Number(d.total||0);const page=d.items||[];if(!page.length)break;
    for(const a of page)if(!seen.has(a.stable_id)){seen.add(a.stable_id);out.push(a);}
    offset=Number(d.offset||offset)+page.length;if(!d.hasMore)break;
  }
  return out;
}
function serverScore(a){return Number(a?.similarity_score||0);}
async function refineVisualSimilarity(list,sourceFp){
  if(!sourceFp)return;
  const sample=list.filter(a=>rasterCandidate(a)).slice(0,SIMILAR_VISUAL_SAMPLE);let next=0;
  async function worker(){
    while(true){const i=next++;if(i>=sample.length)return;const a=sample[i];const fp=await fingerprintRenderedAsset(a);if(!fp)continue;const vs=visualScore(sourceFp,fp);if(vs==null)continue;similarityById.set(a.stable_id,{visual:vs,combined:.78*vs+.22*serverScore(a)});}
  }
  await Promise.all(Array.from({length:3},()=>worker()));
}

function installSimilarityCardScores(){
  try{
    const cards=[...document.querySelectorAll('#results .card')];
    cards.forEach((card,i)=>{const a=items[i],s=similarityById.get(a?.stable_id);if(!s)return;const span=document.createElement('span');span.className='avail preview-good';span.textContent='SIMILAIRE '+Math.round(s.combined*100)+' %';card.appendChild(span);});
  }catch{}
}

const baseRenderList35=renderList;
renderList=function(){baseRenderList35();if(similarMode)installSimilarityCardScores();};

const baseRenderMeta35=renderMeta;
renderMeta=function(a,m=null){
  baseRenderMeta35(a,m);
  const tools=document.querySelector('#meta .tools');if(!tools)return;
  if(!tools.querySelector('#findSimilar')){const b=document.createElement('button');b.id='findSimilar';b.textContent='🔎 Images similaires';b.onclick=()=>showSimilar(a);tools.appendChild(b);}
  if(similarMode&&!tools.querySelector('#backFromSimilar')){const b=document.createElement('button');b.id='backFromSimilar';b.textContent='↩ Retour recherche';b.onclick=()=>{similarMode=false;similarityById.clear();runSearch();};tools.appendChild(b);}
};

const baseBindNav35=bindNav;
bindNav=function(){
  if(!similarMode){baseBindNav35();return;}
  const p=document.querySelector('#prev'),n=document.querySelector('#next');if(p)p.onclick=()=>idx>0&&select(idx-1);if(n)n.onclick=()=>idx<items.length-1&&select(idx+1);
};
const baseRunSearch35=runSearch;
runSearch=async function(){similarMode=false;similarSource=null;similarityById.clear();return baseRunSearch35();};

async function showSimilar(a){
  if(!a)return;
  const stage=document.querySelector('#stage');stage.innerHTML='<div class="empty"><b>Recherche des images similaires…</b><br><span class="hint">Corrélation catalogue + comparaison visuelle avec le rendu actuellement affiché.</span></div>';
  const img=document.querySelector('#assetImg');let sourceFp=null;
  const cv=sourceCanvas();if(cv)sourceFp=fingerprintCanvas(cv);else if(img)sourceFp=fingerprintCanvas(await canvasFromImageElement(img));
  try{
    const found=await fetchAllSimilar(a.stable_id);similarMode=true;similarSource=a;similarityById.clear();
    // Seed with server similarity so results are useful immediately, including 3D candidates.
    for(const x of found)similarityById.set(x.stable_id,{visual:null,combined:serverScore(x)});
    if(sourceFp)await refineVisualSimilarity(found,sourceFp);
    found.sort((x,y)=>(similarityById.get(y.stable_id)?.combined||0)-(similarityById.get(x.stable_id)?.combined||0));
    items=found;idx=-1;currentAsset=null;currentModel?.destroy?.();currentModel=null;
    if(currentUrl){try{URL.revokeObjectURL(currentUrl)}catch{}currentUrl=null;}
    renderList();const rc=document.querySelector('#resultCount');if(rc)rc.textContent=String(items.length);
    const fs=document.querySelector('#filterSummary');if(fs)fs.innerHTML=`<span class="filterchip">🔎 ${items.length} similaires à ${String(a.stable_id)}</span>`;
    if(items.length)select(0);else stage.innerHTML='<div class="empty">Aucun asset similaire trouvé.</div>';
    console.info('V35_SIMILAR_SEARCH',a.stable_id,'results='+items.length,'visual='+!!sourceFp);
  }catch(e){stage.innerHTML=`<div class="empty error">Recherche similaire impossible : ${String(e?.message||e)}</div>`;}
}

['pointerdown','keydown','touchstart'].forEach(ev=>document.addEventListener(ev,()=>{lastActivity=Date.now();},{passive:true}));
ensureAuditPill();setTimeout(runAutomaticAudit,1600);
window.WFGGVisibilitySimilarityV35={
  version:'35.1',audit:()=>({...auditState,running:auditRunning,paused:auditPaused}),pause:()=>{auditPaused=true;updateAuditPill();},resume:()=>{auditPaused=false;updateAuditPill();runAutomaticAudit();},showSimilar,runAutomaticAudit
};
console.info('V35_VISIBILITY_SIMILARITY installed auto-audit=ON similar-button=ON cross-3d-2d=ON');
})();
