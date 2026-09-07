(()=>{
'use strict';

/* WfGg V36 — strict visual similarity.
   User contract:
   - "Images similaires" means visually similar by default, not technically related.
   - texture/PBR/UV/material sheets are excluded from visual mode.
   - texture search is an explicit separate mode.
   - candidates stay fast: metadata narrows first, bounded pixel/silhouette refinement runs progressively.
*/

const API='/api/v33';
const MAX_CANDIDATES=420;
const VISUAL_SAMPLE=56;
const VISUAL_CONCURRENCY=3;
const FETCH_TIMEOUT=7000;
const MODE_KEY='wfgg-similarity-mode-v36';
let seq=0;
let active=false;
let source=null;
let scores=new Map();
let mode='visual';
let refinementRunning=false;

try{mode=localStorage.getItem(MODE_KEY)||'visual';}catch{}
if(!['visual','correlated','texture','all'].includes(mode))mode='visual';

function corr(){return window.WFGGSearchCorrelation||null;}
function textureUX(){return window.WFGGTextureExperienceV35||null;}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function pathOf(a){return String(a?.asset_path||a?.logical_name||a?.alias_name||'').replace(/\\/g,'/').toLowerCase();}
function roleOf(a){return String(a?.model_role||'').toLowerCase();}
function techOf(a){return String(a?.tech_kind||'').toLowerCase();}
function dimOf(a){return String(a?.dimension_class||'');}
function familyOf(a){return String(a?.family||'').toLowerCase();}
function visualRoleOf(a){return String(a?.visual_role||'').toLowerCase();}
function contextOf(a){return String(a?.context||'').toLowerCase();}
function isAnimation(a){const p=pathOf(a),r=roleOf(a),t=techOf(a);return p.includes('/animation/')||p.endsWith('.anim')||r==='animation'||t==='animation'||t==='animationclip';}
function isKnownBad(a){try{const p=corr()?.previewInfo?.(a);return p?.status==='unavailable'||p?.status==='nonautonomous';}catch{return false;}}
function isVerifiedVisible(a){try{return corr()?.previewInfo?.(a)?.status==='visible';}catch{return false;}}

function isTextureLike(a){
  try{if(textureUX()?.isTextureSheet?.(a))return true;}catch{}
  const p=pathOf(a),tail=p.split('/').pop()||'',r=roleOf(a),t=techOf(a),f=familyOf(a);
  if(/\/(texture|textures|pbr|uv|material|materials)\//.test(p))return true;
  if(['texture','material','shader','normalmap','mask','pbr','uv'].includes(r))return true;
  if(/texture2d|normalmap|shader|material|cubemap|rendertexture|astc|ktx/.test(t))return true;
  if(/(?:^|[_-])(albedo|basecolor|diffuse|normal|nrm|spec|specular|smooth|rough|metal|metallic|mask|ao|occlusion|emission|emissive)(?:[_-]|\.)/i.test(tail))return true;
  if(/\.(tga|dds|ktx|ktx2|astc)$/i.test(tail))return true;
  if(f.includes('texture')||f.includes('material'))return true;
  return false;
}
function rasterCandidate(a){const d=dimOf(a),t=techOf(a),r=roleOf(a),p=pathOf(a);return d==='2D'||d==='Mixte 2D/3D'||/sprite|image|png|jpg|jpeg/.test(t)||/\.(png|jpg|jpeg|webp)$/i.test(p)||r==='sprite';}
function modelCandidate(a){const d=dimOf(a),r=roleOf(a),p=pathOf(a);return d==='3D'||d==='Composant 3D'||d==='Mixte 2D/3D'||['geometry','geometry-candidate','prefab'].includes(r)||p.endsWith('.prefab')||p.endsWith('.fbx');}
function sameBroadKind(a,b){
  const af=familyOf(a),bf=familyOf(b);if(af&&bf&&af===bf)return true;
  const av=visualRoleOf(a),bv=visualRoleOf(b);if(av&&bv&&av===bv)return true;
  if(modelCandidate(a)&&modelCandidate(b))return true;
  if(rasterCandidate(a)&&rasterCandidate(b))return true;
  return false;
}

function allowedCandidate(a,src,currentMode){
  if(!a||a.stable_id===src.stable_id||isAnimation(a)||isKnownBad(a))return false;
  const tex=isTextureLike(a);
  if(currentMode==='texture')return tex;
  if(currentMode==='visual'){
    if(tex)return false;
    if(['material','shader','texture'].includes(roleOf(a)))return false;
    const sf=familyOf(src),af=familyOf(a);
    // When the source has a strong semantic family (vehicles/heroes/etc.), visual mode stays in it.
    if(sf&&af&&sf!=='unknown'&&af!=='unknown'&&sf!==af)return false;
    return true;
  }
  if(currentMode==='correlated')return !tex;
  return true;
}

function popcountBigInt(x){let n=0;while(x){x&=x-1n;n++;}return n;}
function fingerprintCanvas(src){
  try{
    const w=src.width||src.clientWidth,h=src.height||src.clientHeight;if(!w||!h)return null;
    const dw=24,dh=24,c=document.createElement('canvas');c.width=dw;c.height=dh;const x=c.getContext('2d',{willReadFrequently:true});x.drawImage(src,0,0,dw,dh);
    const d=x.getImageData(0,0,dw,dh).data;
    const pix=(xx,yy)=>{const i=(yy*dw+xx)*4;return [d[i],d[i+1],d[i+2],d[i+3]];};
    const corners=[pix(0,0),pix(dw-1,0),pix(0,dh-1),pix(dw-1,dh-1)];
    const bg=[0,1,2].map(k=>corners.reduce((s,p)=>s+p[k],0)/corners.length);
    let rs=0,gs=0,bs=0,count=0,occ=0,cx=0,cy=0;const rows=Array(dh).fill(0),cols=Array(dw).fill(0),gray=[];
    for(let yy=0;yy<dh;yy++)for(let xx=0;xx<dw;xx++){
      const i=(yy*dw+xx)*4,r=d[i],g=d[i+1],b=d[i+2],a=d[i+3]/255,lum=.299*r+.587*g+.114*b;gray.push(lum);
      rs+=r;gs+=g;bs+=b;count++;
      const delta=Math.sqrt((r-bg[0])**2+(g-bg[1])**2+(b-bg[2])**2);
      if(a>.08&&delta>32){occ++;cx+=xx;cy+=yy;rows[yy]++;cols[xx]++;}
    }
    let hash=0n;
    for(let yy=0;yy<8;yy++)for(let xx=0;xx<8;xx++){
      const sx=Math.min(dw-2,Math.floor(xx*(dw-1)/8)),sy=Math.min(dh-1,Math.floor(yy*(dh-1)/8));
      const a=gray[sy*dw+sx],b=gray[sy*dw+sx+1];hash=(hash<<1n)|(a>b?1n:0n);
    }
    const total=dw*dh,occupancy=occ/total;
    return {dh:hash.toString(16).padStart(16,'0'),rgb:[rs/count,gs/count,bs/count],aspect:w/h,occupancy,cx:occ?cx/occ/(dw-1):.5,cy:occ?cy/occ/(dh-1):.5,rows:rows.map(v=>v/dw),cols:cols.map(v=>v/dh)};
  }catch(e){console.debug('V36_FP_FAIL',e);return null;}
}
function projectionScore(a,b){
  if(!a?.rows||!b?.rows)return .5;
  const avg=(x,y)=>1-Math.min(1,x.reduce((s,v,i)=>s+Math.abs(v-(y[i]||0)),0)/x.length);
  return .5*avg(a.rows,b.rows)+.5*avg(a.cols,b.cols);
}
function silhouetteScore(a,b){
  if(!a||!b)return null;
  const occ=1-Math.min(1,Math.abs(a.occupancy-b.occupancy)*2.2);
  const cent=1-Math.min(1,Math.hypot(a.cx-b.cx,a.cy-b.cy)*1.5);
  const proj=projectionScore(a,b);
  const ar=Math.exp(-Math.abs(Math.log(Math.max(.01,a.aspect)/Math.max(.01,b.aspect))));
  return .35*proj+.25*occ+.20*cent+.20*ar;
}
function pixelScore(a,b){
  if(!a||!b)return null;let hd=32;try{hd=popcountBigInt(BigInt('0x'+a.dh)^BigInt('0x'+b.dh));}catch{}
  const hash=1-hd/64,cd=Math.sqrt(a.rgb.reduce((s,v,i)=>s+(v-b.rgb[i])**2,0))/(Math.sqrt(3)*255),color=1-Math.min(1,cd);
  return .74*hash+.26*color;
}
function sourceFingerprint(){
  const cv=currentModel?.canvas||document.querySelector('#stage .v33modelcanvas')||document.querySelector('#stage canvas');if(cv){const fp=fingerprintCanvas(cv);if(fp)return fp;}
  const img=document.querySelector('#assetImg');if(!img)return null;
  try{const c=document.createElement('canvas');c.width=Math.max(1,img.naturalWidth||img.width);c.height=Math.max(1,img.naturalHeight||img.height);c.getContext('2d',{willReadFrequently:true}).drawImage(img,0,0,c.width,c.height);return fingerprintCanvas(c);}catch{return null;}
}

async function fetchJson(url,timeout=FETCH_TIMEOUT){const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),timeout);try{const r=await fetch(url,{signal:ctl.signal,cache:'no-store'}),d=await r.json();if(!r.ok)throw new Error(d.message||d.error||('HTTP '+r.status));return d;}finally{clearTimeout(timer);}}
function addScope(scopes,key,value){value=String(value||'').trim();if(value&&!scopes.some(x=>x[key]===value))scopes.push({[key]:value});}
function candidateScopes(a){
  const scopes=[];addScope(scopes,'family',a?.family);addScope(scopes,'visual_role',a?.visual_role);addScope(scopes,'context',a?.context);
  const direct=(a?.hero_links||[]).find(h=>h.relation==='direct');if(direct)addScope(scopes,'hero_id',direct.hero_id);
  const folder=String(a?.asset_folder||'').replace(/\\/g,'/').replace(/^\/+|\/+$/g,'');if(folder)addScope(scopes,'path_prefix',folder.split('/').slice(0,-1).join('/'));
  return scopes.slice(0,5);
}
async function fetchScope(scope){const p=new URLSearchParams({render_availability:'local-renderable',limit:'120',offset:'0'});for(const [k,v] of Object.entries(scope))p.set(k,String(v));if(scope.hero_id)p.set('hero_relation','direct');return (await fetchJson(API+'/search?'+p)).items||[];}
function metadataScore(a,src){
  let s=.02;if(src.family&&a.family===src.family)s+=.30;if(src.visual_role&&a.visual_role===src.visual_role)s+=.22;if(src.context&&a.context===src.context)s+=.10;
  if(sameBroadKind(a,src))s+=.10;if(src.dimension_class&&a.dimension_class===src.dimension_class)s+=.04;
  const sh=new Set((src.hero_links||[]).filter(x=>x.relation==='direct').map(x=>String(x.hero_id)));if(sh.size&&(a.hero_links||[]).some(x=>x.relation==='direct'&&sh.has(String(x.hero_id))))s+=.08;
  const sp=pathOf(src),ap=pathOf(a),stem=sp.split('/').slice(-3,-1).join('/');if(stem&&ap.includes(stem))s+=.08;
  if(isVerifiedVisible(a))s+=.05;return Math.min(.92,s);
}
async function collectCandidates(src,currentMode){
  const scopes=candidateScopes(src),settled=await Promise.allSettled(scopes.map(fetchScope)),map=new Map();
  for(const r of settled)if(r.status==='fulfilled')for(const a of r.value){if(!allowedCandidate(a,src,currentMode)||map.has(a.stable_id))continue;map.set(a.stable_id,a);if(map.size>=MAX_CANDIDATES)break;}
  if(map.size<18){
    try{const p=new URLSearchParams({similar_to:src.stable_id,render_availability:'local-renderable',limit:'120',offset:'0'}),d=await fetchJson(API+'/search?'+p,4500);for(const a of (d.items||[]))if(allowedCandidate(a,src,currentMode)&&!map.has(a.stable_id))map.set(a.stable_id,a);}catch(e){console.debug('V36_SERVER_FALLBACK',e?.message||e);}
  }
  const out=[...map.values()];for(const a of out){const m=metadataScore(a,src);scores.set(a.stable_id,{metadata:m,visual:null,silhouette:null,combined:m*.45});}
  out.sort((x,y)=>(scores.get(y.stable_id)?.combined||0)-(scores.get(x.stable_id)?.combined||0));return out;
}

function badgeLabel(s,currentMode){
  const pct=Math.round((s?.combined||0)*100);
  if(currentMode==='texture')return 'TEXTURE '+pct+' %';
  if(currentMode==='correlated')return 'CORRÉLÉ '+pct+' %';
  if(currentMode==='all')return (s?.visual!=null?'SIMILAIRE ':'PROCHE ')+pct+' %';
  return (s?.visual!=null?'SIMILAIRE VISUEL ':'CANDIDAT VISUEL ')+pct+' %';
}
function installScoreBadges(){
  const cards=[...document.querySelectorAll('#results .card')];cards.forEach((card,i)=>{const a=items[i],s=scores.get(a?.stable_id);if(!s)return;card.querySelectorAll('[data-v36-score]').forEach(x=>x.remove());const span=document.createElement('span');span.dataset.v36Score='1';span.className='avail preview-good';span.textContent=badgeLabel(s,mode);card.appendChild(span);});
}
function updateSummary(text){const fs=document.querySelector('#filterSummary');if(fs)fs.innerHTML=`<span class="filterchip">${esc(text)}</span>`;}
function ensureControls(tools,a){
  if(!tools)return;
  let box=tools.querySelector('#similarityModeV36');if(!box){box=document.createElement('span');box.id='similarityModeV36';box.style.display='inline-flex';box.style.gap='4px';box.style.alignItems='center';box.innerHTML='<select id="simModeV36" style="width:auto;max-width:155px;padding:8px"><option value="visual">Visuel</option><option value="correlated">Corrélé</option><option value="texture">Texture</option><option value="all">Tout</option></select>';tools.appendChild(box);}
  const sel=box.querySelector('#simModeV36');if(sel){if(isTextureLike(a)&&mode==='visual')mode='texture';sel.value=mode;sel.onchange=()=>{mode=sel.value;try{localStorage.setItem(MODE_KEY,mode);}catch{}};}
}

let installed=false;
function installWrappers(){
  if(installed||typeof renderMeta!=='function'||typeof renderList!=='function')return false;installed=true;
  const baseRenderList=renderList;renderList=function(){const r=baseRenderList();if(active)installScoreBadges();return r;};
  const baseRenderMeta=renderMeta;renderMeta=function(a,m=null){baseRenderMeta(a,m);const tools=document.querySelector('#meta .tools');if(!tools)return;ensureControls(tools,a);const find=tools.querySelector('#findSimilar');if(find)find.onclick=()=>showSimilarV36(a);else{const b=document.createElement('button');b.id='findSimilar';b.textContent='🔎 Images similaires';b.onclick=()=>showSimilarV36(a);tools.appendChild(b);}if(active&&!tools.querySelector('#backFromSimilarV36')){const b=document.createElement('button');b.id='backFromSimilarV36';b.textContent='↩ Retour recherche';b.onclick=()=>{seq++;active=false;source=null;scores.clear();runSearch();};tools.appendChild(b);}};
  const baseRunSearch=runSearch;runSearch=async function(){if(active){seq++;active=false;source=null;scores.clear();}return baseRunSearch();};
  console.info('V36_VISUAL_SIMILARITY wrappers=ON default=VISUAL texture-exclusion=ON silhouette-score=ON');return true;
}

async function fingerprintRendered(a){
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),6000);try{const r=await fetch(API+'/render?id='+encodeURIComponent(a.stable_id),{signal:ctl.signal,cache:'force-cache'});if(!r.ok)return null;const blob=await r.blob(),bmp=await createImageBitmap(blob),c=document.createElement('canvas');c.width=bmp.width;c.height=bmp.height;c.getContext('2d').drawImage(bmp,0,0);bmp.close?.();return fingerprintCanvas(c);}catch{return null;}finally{clearTimeout(timer);}
}
async function refine(list,sourceFp,my,resumeAudit,currentMode){
  if(!sourceFp||currentMode==='texture'||currentMode==='correlated'){if(resumeAudit)window.WFGGVisibilitySimilarityV35?.resume?.();return;}
  refinementRunning=true;const sample=list.filter(a=>rasterCandidate(a)&&!isTextureLike(a)).slice(0,VISUAL_SAMPLE);let next=0,done=0;
  updateSummary(`🔎 ${list.length} candidats visuels · comparaison de forme en arrière-plan…`);
  async function worker(){while(my===seq){const i=next++;if(i>=sample.length)return;const a=sample[i],fp=await fingerprintRendered(a);if(my!==seq)return;if(fp){const pix=pixelScore(sourceFp,fp),sil=silhouetteScore(sourceFp,fp),old=scores.get(a.stable_id)||{metadata:0};const comb=.55*(pix||0)+.25*(sil||0)+.20*(old.metadata||0);scores.set(a.stable_id,{metadata:old.metadata||0,visual:pix,silhouette:sil,combined:Math.min(1,comb)});}done++;if(done%5===0)installScoreBadges();}}
  try{await Promise.all(Array.from({length:VISUAL_CONCURRENCY},()=>worker()));if(my!==seq)return;const activeSid=currentAsset?.stable_id||'';items.sort((x,y)=>(scores.get(y.stable_id)?.combined||0)-(scores.get(x.stable_id)?.combined||0));if(activeSid){const ni=items.findIndex(x=>x.stable_id===activeSid);if(ni>=0)idx=ni;}renderList();try{window.WFGGResultStripSync?.('auto');}catch{}updateSummary(`🔎 ${items.length} similaires visuels · ${done} rendus comparés`);}finally{refinementRunning=false;if(resumeAudit&&my===seq)window.WFGGVisibilitySimilarityV35?.resume?.();}
}

async function showSimilarV36(a){
  if(!a)return;const my=++seq;const currentMode=isTextureLike(a)&&mode==='visual'?'texture':mode,sourceFp=sourceFingerprint();const audit=window.WFGGVisibilitySimilarityV35?.audit?.()||{},resumeAudit=!!audit.running&&!audit.paused;if(resumeAudit)window.WFGGVisibilitySimilarityV35?.pause?.();
  const stage=document.querySelector('#stage');stage.innerHTML=`<div class="empty"><b>Recherche ${currentMode==='visual'?'visuelle':currentMode==='texture'?'de textures':'corrélée'}…</b><br><span class="hint">Les planches PBR/UV sont ${currentMode==='visual'?'exclues':'gérées selon le mode choisi'}.</span></div>`;
  try{scores.clear();const found=await collectCandidates(a,currentMode);if(my!==seq)return;active=true;source=a;items=found;idx=-1;currentAsset=null;currentModel?.destroy?.();currentModel=null;if(currentUrl){try{URL.revokeObjectURL(currentUrl)}catch{}currentUrl=null;}renderList();const rc=document.querySelector('#resultCount');if(rc)rc.textContent=String(items.length);updateSummary(`🔎 ${items.length} candidats · mode ${currentMode}`);if(items.length){select(0);refine(items.slice(),sourceFp,my,resumeAudit,currentMode);}else{stage.innerHTML='<div class="empty">Aucun candidat dans ce mode.</div>';if(resumeAudit)window.WFGGVisibilitySimilarityV35?.resume?.();}console.info('V36_SIMILAR',a.stable_id,'mode='+currentMode,'results='+items.length);}catch(e){if(my!==seq)return;stage.innerHTML=`<div class="empty error">Recherche similaire impossible : ${esc(e?.message||e)}</div>`;if(resumeAudit)window.WFGGVisibilitySimilarityV35?.resume?.();}
}

function boot(){if(!installWrappers())setTimeout(boot,120);}
boot();
window.WFGGVisualSimilarityV36={version:'36.0',showSimilar:showSimilarV36,state:()=>({active,source:source?.stable_id||null,mode,results:active?items.length:0,refinementRunning}),setMode:(m)=>{if(['visual','correlated','texture','all'].includes(m)){mode=m;try{localStorage.setItem(MODE_KEY,mode);}catch{}}}};
})();
