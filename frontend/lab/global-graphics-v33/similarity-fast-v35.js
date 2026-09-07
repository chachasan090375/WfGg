(()=>{
'use strict';

/* V35.3 fast/progressive similarity UX.
   The previous similarity button waited for up to 160 fresh raster decodes before returning any
   result. On Android this could leave the stage on “Recherche des images similaires…” for minutes,
   especially while the automatic preview audit was consuming the same local decoder.

   This overlay changes the contract:
   - capture the currently displayed 2D/3D pixels first;
   - temporarily pause the background audit;
   - obtain a broad metadata candidate set through ordinary fast /search queries;
   - show candidates immediately;
   - refine a bounded set of 2D candidates visually in the background;
   - never block navigation while visual refinement is running.
*/

const API='/api/v33';
const MAX_CANDIDATES=520;
const VISUAL_SAMPLE=48;
const VISUAL_CONCURRENCY=3;
const FETCH_TIMEOUT=7000;
let seq=0;
let fastMode=false;
let fastSource=null;
let scores=new Map();
let refinementRunning=false;

function corr(){return window.WFGGSearchCorrelation||null;}
function textureUX(){return window.WFGGTextureExperienceV35||null;}
function esc2(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function pathOf(a){return String(a?.asset_path||a?.logical_name||a?.alias_name||'').replace(/\\/g,'/').toLowerCase();}
function roleOf(a){return String(a?.model_role||'').toLowerCase();}
function techOf(a){return String(a?.tech_kind||'').toLowerCase();}
function dimOf(a){return String(a?.dimension_class||'');}
function isAnimation(a){const p=pathOf(a),r=roleOf(a),t=techOf(a);return p.includes('/animation/')||p.endsWith('.anim')||r==='animation'||t==='animation'||t==='animationclip';}
function rasterCandidate(a){const d=dimOf(a),t=techOf(a),r=roleOf(a);return d==='2D'||d==='Mixte 2D/3D'||/sprite|texture|atlas|image|png|jpg|jpeg/.test(t)||['texture','material'].includes(r);}
function isKnownBad(a){try{const p=corr()?.previewInfo?.(a);return p?.status==='unavailable'||p?.status==='nonautonomous';}catch{return false;}}
function isTextureSheet(a){try{return !!textureUX()?.isTextureSheet?.(a);}catch{return false;}}

function popcountBigInt(x){let n=0;while(x){x&=x-1n;n++;}return n;}
function fingerprintCanvas(src){
  try{
    const w=src.width||src.clientWidth,h=src.height||src.clientHeight;if(!w||!h)return null;
    const c=document.createElement('canvas');c.width=9;c.height=8;const x=c.getContext('2d',{willReadFrequently:true});x.drawImage(src,0,0,9,8);
    const d=x.getImageData(0,0,9,8).data;let hash=0n,rs=0,gs=0,bs=0,count=0,lumMin=255,lumMax=0;
    const gray=(i)=>0.299*d[i]+0.587*d[i+1]+0.114*d[i+2];
    for(let y=0;y<8;y++)for(let xx=0;xx<8;xx++){
      const i=(y*9+xx)*4,j=i+4,g=gray(i);hash=(hash<<1n)|(g>gray(j)?1n:0n);
      rs+=d[i];gs+=d[i+1];bs+=d[i+2];count++;lumMin=Math.min(lumMin,g);lumMax=Math.max(lumMax,g);
    }
    if(lumMax-lumMin<3)return null;
    return {dh:hash.toString(16).padStart(16,'0'),rgb:[rs/count,gs/count,bs/count],aspect:w/h};
  }catch(e){console.debug('V353_SOURCE_FP_FAIL',e);return null;}
}
function visualScore(a,b){
  if(!a||!b)return null;let hd=32;
  try{hd=popcountBigInt(BigInt('0x'+a.dh)^BigInt('0x'+b.dh));}catch{}
  const hash=1-hd/64,cd=Math.sqrt(a.rgb.reduce((s,v,i)=>s+(v-b.rgb[i])**2,0))/(Math.sqrt(3)*255),color=1-Math.min(1,cd);
  const ar=Math.exp(-Math.abs(Math.log(Math.max(.01,a.aspect)/Math.max(.01,b.aspect))));
  return .68*hash+.20*color+.12*ar;
}
function sourceFingerprint(){
  const cv=currentModel?.canvas||document.querySelector('#stage .v33modelcanvas')||document.querySelector('#stage canvas');
  if(cv){const fp=fingerprintCanvas(cv);if(fp)return fp;}
  const img=document.querySelector('#assetImg');if(!img)return null;
  try{const c=document.createElement('canvas');c.width=Math.max(1,img.naturalWidth||img.width);c.height=Math.max(1,img.naturalHeight||img.height);c.getContext('2d',{willReadFrequently:true}).drawImage(img,0,0,c.width,c.height);return fingerprintCanvas(c);}catch{return null;}
}

async function fetchJson(url,timeout=FETCH_TIMEOUT){
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),timeout);
  try{const r=await fetch(url,{signal:ctl.signal,cache:'no-store'}),d=await r.json();if(!r.ok)throw new Error(d.message||d.error||('HTTP '+r.status));return d;}
  finally{clearTimeout(timer);}
}
function addScope(scopes,key,value){value=String(value||'').trim();if(value&&!scopes.some(x=>x[key]===value))scopes.push({[key]:value});}
function candidateScopes(a){
  const scopes=[];addScope(scopes,'family',a?.family);addScope(scopes,'visual_role',a?.visual_role);addScope(scopes,'context',a?.context);
  const direct=(a?.hero_links||[]).find(h=>h.relation==='direct');if(direct)addScope(scopes,'hero_id',direct.hero_id);
  const folder=String(a?.asset_folder||'').replace(/\\/g,'/').replace(/^\/+|\/+$/g,'');if(folder)addScope(scopes,'path_prefix',folder.split('/').slice(0,-1).join('/'));
  return scopes.slice(0,5);
}
async function fetchScope(scope){
  const p=new URLSearchParams({render_availability:'local-renderable',limit:'120',offset:'0'});for(const [k,v] of Object.entries(scope))p.set(k,String(v));
  if(scope.hero_id)p.set('hero_relation','direct');return (await fetchJson(API+'/search?'+p)).items||[];
}
function metadataScore(a,src){
  let s=.05;
  if(src.family&&a.family===src.family)s+=.30;
  if(src.visual_role&&a.visual_role===src.visual_role)s+=.18;
  if(src.context&&a.context===src.context)s+=.12;
  if(src.dimension_class&&a.dimension_class===src.dimension_class)s+=.05;
  if(src.tech_kind&&a.tech_kind===src.tech_kind)s+=.04;
  const sh=new Set((src.hero_links||[]).filter(x=>x.relation==='direct').map(x=>String(x.hero_id)));
  if(sh.size&&(a.hero_links||[]).some(x=>x.relation==='direct'&&sh.has(String(x.hero_id))))s+=.14;
  const sp=pathOf(src),ap=pathOf(a),stem=sp.split('/').slice(-3,-1).join('/');if(stem&&ap.includes(stem))s+=.10;
  return Math.min(.88,s);
}
async function collectCandidates(src){
  const scopes=candidateScopes(src);const settled=await Promise.allSettled(scopes.map(fetchScope));const map=new Map();
  for(const r of settled)if(r.status==='fulfilled')for(const a of r.value){
    if(a.stable_id===src.stable_id||map.has(a.stable_id)||isAnimation(a)||isKnownBad(a)||isTextureSheet(a))continue;
    map.set(a.stable_id,a);if(map.size>=MAX_CANDIDATES)break;
  }
  let out=[...map.values()];
  // Fallback to the existing server similarity endpoint, but never let it hold the UI indefinitely.
  if(out.length<12){
    try{
      const p=new URLSearchParams({similar_to:src.stable_id,render_availability:'local-renderable',limit:'120',offset:'0'}),d=await fetchJson(API+'/search?'+p,4500);
      for(const a of (d.items||[]))if(a.stable_id!==src.stable_id&&!map.has(a.stable_id)&&!isAnimation(a)&&!isKnownBad(a)&&!isTextureSheet(a)){map.set(a.stable_id,a);}
      out=[...map.values()];
    }catch(e){console.debug('V353_SERVER_SIM_FALLBACK_TIMEOUT',e?.message||e);}
  }
  for(const a of out)scores.set(a.stable_id,{metadata:metadataScore(a,src),visual:null,combined:metadataScore(a,src)});
  out.sort((x,y)=>(scores.get(y.stable_id)?.combined||0)-(scores.get(x.stable_id)?.combined||0));return out;
}

function installScoreBadges(){
  const cards=[...document.querySelectorAll('#results .card')];
  cards.forEach((card,i)=>{
    const a=items[i],s=scores.get(a?.stable_id);if(!s)return;
    card.querySelectorAll('[data-v353-score]').forEach(x=>x.remove());
    const span=document.createElement('span');span.dataset.v353Score='1';span.className='avail preview-good';
    span.textContent=(s.visual!=null?'SIMILAIRE ':'PROCHE ')+Math.round((s.combined||0)*100)+' %';card.appendChild(span);
  });
}
function updateSummary(text){const fs=document.querySelector('#filterSummary');if(fs)fs.innerHTML=`<span class="filterchip">${esc2(text)}</span>`;}

let installed=false;
function installWrappers(){
  if(installed||typeof renderMeta!=='function'||typeof renderList!=='function')return false;installed=true;
  const baseRenderList=renderList;renderList=function(){const r=baseRenderList();if(fastMode)installScoreBadges();return r;};
  const baseRenderMeta=renderMeta;renderMeta=function(a,m=null){
    baseRenderMeta(a,m);const tools=document.querySelector('#meta .tools');if(!tools)return;
    const find=tools.querySelector('#findSimilar');if(find)find.onclick=()=>showSimilarFast(a);
    else{const b=document.createElement('button');b.id='findSimilar';b.textContent='🔎 Images similaires';b.onclick=()=>showSimilarFast(a);tools.appendChild(b);}
    if(fastMode&&!tools.querySelector('#backFromSimilarFast')){const b=document.createElement('button');b.id='backFromSimilarFast';b.textContent='↩ Retour recherche';b.onclick=()=>{seq++;fastMode=false;fastSource=null;scores.clear();runSearch();};tools.appendChild(b);}
  };
  const baseRunSearch=runSearch;runSearch=async function(){if(fastMode){seq++;fastMode=false;fastSource=null;scores.clear();}return baseRunSearch();};
  console.info('V35_FAST_SIMILARITY wrappers=ON progressive-results=ON audit-pause=ON');return true;
}

async function fingerprintRendered(a){
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),6000);
  try{
    const r=await fetch(API+'/render?id='+encodeURIComponent(a.stable_id),{signal:ctl.signal,cache:'force-cache'});if(!r.ok)return null;
    const blob=await r.blob(),bmp=await createImageBitmap(blob),c=document.createElement('canvas');c.width=bmp.width;c.height=bmp.height;c.getContext('2d').drawImage(bmp,0,0);bmp.close?.();
    try{corr()?.recordPreview?.(a,'visible','2d','similarity-fast-render-ok');}catch{}
    return fingerprintCanvas(c);
  }catch{return null;}finally{clearTimeout(timer);}
}
async function refineInBackground(list,sourceFp,my,resumeAudit){
  if(!sourceFp){if(resumeAudit)window.WFGGVisibilitySimilarityV35?.resume?.();return;}
  refinementRunning=true;const sample=list.filter(rasterCandidate).slice(0,VISUAL_SAMPLE);let next=0,done=0;
  updateSummary(`🔎 ${list.length} résultats proches · affinage visuel en arrière-plan…`);
  async function worker(){
    while(my===seq){const i=next++;if(i>=sample.length)return;const a=sample[i],fp=await fingerprintRendered(a);if(my!==seq)return;
      if(fp){const vs=visualScore(sourceFp,fp),old=scores.get(a.stable_id)||{metadata:0};if(vs!=null)scores.set(a.stable_id,{metadata:old.metadata||0,visual:vs,combined:.78*vs+.22*(old.metadata||0)});}
      done++;if(done%6===0)installScoreBadges();
    }
  }
  try{await Promise.all(Array.from({length:VISUAL_CONCURRENCY},()=>worker()));
    if(my!==seq)return;
    const activeSid=currentAsset?.stable_id||'';items.sort((x,y)=>(scores.get(y.stable_id)?.combined||0)-(scores.get(x.stable_id)?.combined||0));
    if(activeSid){const ni=items.findIndex(x=>x.stable_id===activeSid);if(ni>=0)idx=ni;}
    renderList();try{window.WFGGResultStripSync?.('auto');}catch{}
    updateSummary(`🔎 ${items.length} résultats similaires · affinage visuel terminé (${done} comparés)`);
  }finally{refinementRunning=false;if(resumeAudit&&my===seq)window.WFGGVisibilitySimilarityV35?.resume?.();}
}

async function showSimilarFast(a){
  if(!a)return;const my=++seq;const sourceFp=sourceFingerprint();
  const audit=window.WFGGVisibilitySimilarityV35?.audit?.()||{},resumeAudit=!!audit.running&&!audit.paused;
  if(resumeAudit)window.WFGGVisibilitySimilarityV35?.pause?.();
  const stage=document.querySelector('#stage');stage.innerHTML='<div class="empty"><b>Recherche rapide des images similaires…</b><br><span class="hint">Les premiers résultats vont apparaître immédiatement ; l’affinage visuel continuera ensuite en arrière-plan.</span></div>';
  try{
    scores.clear();const found=await collectCandidates(a);if(my!==seq)return;
    fastMode=true;fastSource=a;items=found;idx=-1;currentAsset=null;currentModel?.destroy?.();currentModel=null;
    if(currentUrl){try{URL.revokeObjectURL(currentUrl)}catch{}currentUrl=null;}
    renderList();const rc=document.querySelector('#resultCount');if(rc)rc.textContent=String(items.length);
    updateSummary(`🔎 ${items.length} résultats proches de ${a.stable_id} · affichés immédiatement`);
    if(items.length){select(0);refineInBackground(items.slice(),sourceFp,my,resumeAudit);}else{
      stage.innerHTML='<div class="empty">Aucun asset proche trouvé avec les critères disponibles.</div>';if(resumeAudit)window.WFGGVisibilitySimilarityV35?.resume?.();
    }
    console.info('V353_FAST_SIMILAR',a.stable_id,'results='+items.length,'sourcePixels='+!!sourceFp);
  }catch(e){if(my!==seq)return;stage.innerHTML=`<div class="empty error">Recherche similaire impossible : ${esc2(e?.message||e)}</div>`;if(resumeAudit)window.WFGGVisibilitySimilarityV35?.resume?.();}
}

function boot(){if(!installWrappers())setTimeout(boot,100);}
boot();
window.WFGGFastSimilarityV35={version:'35.3',showSimilar:showSimilarFast,state:()=>({fastMode,source:fastSource?.stable_id||null,results:fastMode?items.length:0,refinementRunning})};
})();
