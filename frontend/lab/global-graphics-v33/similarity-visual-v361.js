(()=>{
'use strict';

/* WfGg V36.1 — strict visual relevance guard.
   Fixes two user-facing problems:
   1) the V36 source auto-switch could silently force "texture" mode when a 3D asset was currently
      displayed through a 2D fallback; the main Images similaires action is now VISUAL by default;
   2) visual results are now filtered by semantic object kind and readability before display.
      Texture/PBR/UV/material sheets, atlases, flipbooks and multi-frame effect sheets are excluded
      from a vehicle/character visual search.
*/

const API='/api/v33';
const MAX_CANDIDATES=320;
const FIRST_VISUAL_SAMPLE=28;
const BACKGROUND_SAMPLE=36;
const FETCH_TIMEOUT=6500;
const RESULT_LIMIT=36;
const MIN_VISUAL=.52;
const MIN_COMBINED=.54;
let seq=0;
let strictActive=false;
let strictSource=null;
let strictScores=new Map();
let manualMode=false;
let requestedMode='visual';
let wrappersInstalled=false;

function corr(){return window.WFGGSearchCorrelation||null;}
function pathOf(a){return String(a?.asset_path||a?.logical_name||a?.alias_name||'').replace(/\\/g,'/').toLowerCase();}
function roleOf(a){return String(a?.model_role||'').toLowerCase();}
function techOf(a){return String(a?.tech_kind||'').toLowerCase();}
function familyOf(a){return String(a?.family||'').toLowerCase();}
function visualRoleOf(a){return String(a?.visual_role||'').toLowerCase();}
function contextOf(a){return String(a?.context||'').toLowerCase();}
function dimOf(a){return String(a?.dimension_class||'');}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}

function semanticKind(a){
  const s=[pathOf(a),familyOf(a),visualRoleOf(a),contextOf(a),String(a?.subfamily||'').toLowerCase()].join(' ');
  if(/\b(vehicle|vehicles|car|cars|tank|tanks|uav|truck|jeep|motor|helicopter|aircraft)\b/.test(s)||/\/models?\/cars?\//.test(s)||/\/vehicle\//.test(s))return 'vehicle';
  if(/\b(hero|heroes|character|characters|soldier|unit|troop)\b/.test(s)||/\/character\//.test(s))return 'character';
  if(/\b(effect|effects|vfx|particle|particles|fx)\b/.test(s)||/\/(effect|effects|vfx)\//.test(s))return 'effect';
  if(/\b(ui|icon|icons|hud|menu|button|avatar|portrait)\b/.test(s)||/\/(ui|icons?)\//.test(s))return 'ui';
  return 'other';
}
function isAnimation(a){const p=pathOf(a),r=roleOf(a),t=techOf(a);return p.includes('/animation/')||p.endsWith('.anim')||r==='animation'||t==='animation'||t==='animationclip';}
function isKnownBad(a){try{const p=corr()?.previewInfo?.(a);return p?.status==='unavailable'||p?.status==='nonautonomous';}catch{return false;}}
function isVerifiedVisible(a){try{return corr()?.previewInfo?.(a)?.status==='visible';}catch{return false;}}
function isTextureLike(a){
  try{if(window.WFGGTextureExperienceV35?.isTextureSheet?.(a))return true;}catch{}
  const p=pathOf(a),tail=p.split('/').pop()||'',r=roleOf(a),t=techOf(a),f=familyOf(a);
  if(/\/(texture|textures|pbr|uv|material|materials)\//.test(p))return true;
  if(['texture','material','shader','normalmap','mask','pbr','uv'].includes(r))return true;
  if(/texture2d|normalmap|shader|material|cubemap|rendertexture|astc|ktx/.test(t))return true;
  if(/(?:^|[_-])(albedo|basecolor|diffuse|normal|nrm|spec|specular|smooth|rough|metal|metallic|mask|ao|occlusion|emission|emissive)(?:[_-]|\.)/i.test(tail))return true;
  if(/\.(tga|dds|ktx|ktx2|astc)$/i.test(tail))return true;
  return f.includes('texture')||f.includes('material');
}
function isTechnicalSheetByMeta(a){
  const p=pathOf(a),t=techOf(a),r=roleOf(a);
  if(/atlas|spritesheet|sprite[_-]?sheet|flipbook|sequence|frames?[_-]?sheet|contact[_-]?sheet/.test(p+' '+t+' '+r))return true;
  if(/\/(effect|effects|vfx)\//.test(p)&&/(sprite|texture|atlas|frame|sequence|flipbook)/.test(p+' '+t+' '+r))return true;
  return false;
}
function modelCandidate(a){const d=dimOf(a),r=roleOf(a),p=pathOf(a);return d==='3D'||d==='Composant 3D'||d==='Mixte 2D/3D'||['geometry','geometry-candidate','prefab'].includes(r)||p.endsWith('.prefab')||p.endsWith('.fbx');}
function rasterCandidate(a){const d=dimOf(a),t=techOf(a),r=roleOf(a),p=pathOf(a);return d==='2D'||d==='Mixte 2D/3D'||/sprite|image|png|jpg|jpeg/.test(t)||/\.(png|jpg|jpeg|webp)$/i.test(p)||r==='sprite';}
function sameDirectHero(a,b){
  const aa=new Set((a?.hero_links||[]).filter(x=>x.relation==='direct').map(x=>String(x.hero_id)));
  return aa.size>0&&(b?.hero_links||[]).some(x=>x.relation==='direct'&&aa.has(String(x.hero_id)));
}
function allowedVisualCandidate(a,src){
  if(!a||a.stable_id===src.stable_id||isAnimation(a)||isKnownBad(a)||isTextureLike(a)||isTechnicalSheetByMeta(a))return false;
  const sk=semanticKind(src),ak=semanticKind(a);
  if(sk==='vehicle'&&ak!=='vehicle')return false;
  if(sk==='character'&&ak!=='character')return false;
  if(sk==='effect'&&ak!=='effect')return false;
  if(sk==='ui'&&ak!=='ui')return false;
  if((sk==='vehicle'||sk==='character')&&(ak==='effect'||ak==='ui'))return false;
  return modelCandidate(a)||rasterCandidate(a);
}

function metadataScore(a,src){
  const sk=semanticKind(src),ak=semanticKind(a);let s=.04;
  if(sk===ak&&sk!=='other')s+=.42;
  if(src.family&&a.family===src.family)s+=.18;
  if(src.visual_role&&a.visual_role===src.visual_role)s+=.13;
  if(src.context&&a.context===src.context)s+=.05;
  if(sameDirectHero(src,a))s+=.04;
  const sp=pathOf(src),ap=pathOf(a),stem=sp.split('/').slice(-3,-1).join('/');if(stem&&ap.includes(stem))s+=.08;
  if(modelCandidate(src)&&modelCandidate(a))s+=.05;
  if(isVerifiedVisible(a))s+=.05;
  return Math.min(1,s);
}

function popcountBigInt(x){let n=0;while(x){x&=x-1n;n++;}return n;}
function fingerprintCanvas(src){
  try{
    const w=src.width||src.clientWidth,h=src.height||src.clientHeight;if(!w||!h)return null;
    const dw=32,dh=32,c=document.createElement('canvas');c.width=dw;c.height=dh;const x=c.getContext('2d',{willReadFrequently:true});x.drawImage(src,0,0,dw,dh);
    const d=x.getImageData(0,0,dw,dh).data;
    const corner=(xx,yy)=>{const i=(yy*dw+xx)*4;return [d[i],d[i+1],d[i+2]];};
    const cs=[corner(0,0),corner(dw-1,0),corner(0,dh-1),corner(dw-1,dh-1)];
    const bg=[0,1,2].map(k=>cs.reduce((s,p)=>s+p[k],0)/4);
    const mask=new Uint8Array(dw*dh),gray=new Float32Array(dw*dh);let rs=0,gs=0,bs=0,occ=0,cx=0,cy=0,lumMin=255,lumMax=0;
    for(let yy=0;yy<dh;yy++)for(let xx=0;xx<dw;xx++){
      const q=yy*dw+xx,i=q*4,r=d[i],g=d[i+1],b=d[i+2],a=d[i+3]/255,lum=.299*r+.587*g+.114*b;gray[q]=lum;rs+=r;gs+=g;bs+=b;lumMin=Math.min(lumMin,lum);lumMax=Math.max(lumMax,lum);
      const delta=Math.hypot(r-bg[0],g-bg[1],b-bg[2]);if(a>.08&&delta>36){mask[q]=1;occ++;cx+=xx;cy+=yy;}
    }
    let hash=0n;for(let yy=0;yy<8;yy++)for(let xx=0;xx<8;xx++){const sx=Math.min(dw-2,Math.floor(xx*(dw-1)/8)),sy=Math.min(dh-1,Math.floor(yy*(dh-1)/8));hash=(hash<<1n)|(gray[sy*dw+sx]>gray[sy*dw+sx+1]?1n:0n);}
    const seen=new Uint8Array(mask.length);let components=0;
    for(let q=0;q<mask.length;q++)if(mask[q]&&!seen[q]){let count=0,stack=[q];seen[q]=1;while(stack.length){const z=stack.pop();count++;const yy=Math.floor(z/dw),xx=z-yy*dw;for(const [nx,ny] of [[xx-1,yy],[xx+1,yy],[xx,yy-1],[xx,yy+1]])if(nx>=0&&nx<dw&&ny>=0&&ny<dh){const nz=ny*dw+nx;if(mask[nz]&&!seen[nz]){seen[nz]=1;stack.push(nz);}}}if(count>=3)components++;}
    const rows=Array(dh).fill(0),cols=Array(dw).fill(0);for(let yy=0;yy<dh;yy++)for(let xx=0;xx<dw;xx++)if(mask[yy*dw+xx]){rows[yy]++;cols[xx]++;}
    const total=dw*dh;return {dh:hash.toString(16).padStart(16,'0'),rgb:[rs/total,gs/total,bs/total],aspect:w/h,occupancy:occ/total,cx:occ?cx/occ/(dw-1):.5,cy:occ?cy/occ/(dh-1):.5,rows:rows.map(v=>v/dw),cols:cols.map(v=>v/dh),components,contrast:lumMax-lumMin};
  }catch(e){console.debug('V361_FP_FAIL',e);return null;}
}
function projectionScore(a,b){const avg=(x,y)=>1-Math.min(1,x.reduce((s,v,i)=>s+Math.abs(v-(y[i]||0)),0)/x.length);return .5*avg(a.rows,b.rows)+.5*avg(a.cols,b.cols);}
function silhouetteScore(a,b){
  if(!a||!b)return 0;const occ=1-Math.min(1,Math.abs(a.occupancy-b.occupancy)*2.3),cent=1-Math.min(1,Math.hypot(a.cx-b.cx,a.cy-b.cy)*1.7),proj=projectionScore(a,b),ar=Math.exp(-Math.abs(Math.log(Math.max(.01,a.aspect)/Math.max(.01,b.aspect))));return .40*proj+.25*occ+.20*cent+.15*ar;
}
function pixelScore(a,b){if(!a||!b)return 0;let hd=32;try{hd=popcountBigInt(BigInt('0x'+a.dh)^BigInt('0x'+b.dh));}catch{}const hash=1-hd/64,cd=Math.hypot(...a.rgb.map((v,i)=>v-b.rgb[i]))/(Math.sqrt(3)*255),color=1-Math.min(1,cd);return .82*hash+.18*color;}
function readableFingerprint(fp,sourceKind){
  if(!fp||fp.contrast<7)return false;
  if((sourceKind==='vehicle'||sourceKind==='character')&&fp.components>=5&&fp.occupancy<.72)return false;
  return true;
}
function sourceFingerprint(){
  const cv=currentModel?.canvas||document.querySelector('#stage .v33modelcanvas')||document.querySelector('#stage canvas');if(cv){const fp=fingerprintCanvas(cv);if(fp)return fp;}
  const img=document.querySelector('#assetImg');if(!img)return null;try{const c=document.createElement('canvas');c.width=Math.max(1,img.naturalWidth||img.width);c.height=Math.max(1,img.naturalHeight||img.height);c.getContext('2d',{willReadFrequently:true}).drawImage(img,0,0,c.width,c.height);return fingerprintCanvas(c);}catch{return null;}
}

async function fetchJson(url,timeout=FETCH_TIMEOUT){const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),timeout);try{const r=await fetch(url,{signal:ctl.signal,cache:'no-store'}),d=await r.json();if(!r.ok)throw new Error(d.message||d.error||('HTTP '+r.status));return d;}finally{clearTimeout(timer);}}
function addScope(scopes,key,value){value=String(value||'').trim();if(value&&!scopes.some(x=>x[key]===value))scopes.push({[key]:value});}
function candidateScopes(src){const scopes=[];addScope(scopes,'family',src?.family);addScope(scopes,'visual_role',src?.visual_role);addScope(scopes,'context',src?.context);const h=(src?.hero_links||[]).find(x=>x.relation==='direct');if(h)addScope(scopes,'hero_id',h.hero_id);const f=String(src?.asset_folder||'').replace(/\\/g,'/').replace(/^\/+|\/+$/g,'');if(f)addScope(scopes,'path_prefix',f.split('/').slice(0,-1).join('/'));return scopes.slice(0,5);}
async function fetchScope(scope){const p=new URLSearchParams({render_availability:'local-renderable',limit:'120',offset:'0'});for(const [k,v] of Object.entries(scope))p.set(k,String(v));if(scope.hero_id)p.set('hero_relation','direct');return (await fetchJson(API+'/search?'+p)).items||[];}
async function collectCandidates(src){
  const map=new Map(),settled=await Promise.allSettled(candidateScopes(src).map(fetchScope));for(const r of settled)if(r.status==='fulfilled')for(const a of r.value){if(!allowedVisualCandidate(a,src)||map.has(a.stable_id))continue;map.set(a.stable_id,a);if(map.size>=MAX_CANDIDATES)break;}
  if(map.size<20){try{const p=new URLSearchParams({similar_to:src.stable_id,render_availability:'local-renderable',limit:'120',offset:'0'}),d=await fetchJson(API+'/search?'+p,4200);for(const a of (d.items||[]))if(allowedVisualCandidate(a,src)&&!map.has(a.stable_id))map.set(a.stable_id,a);}catch(e){console.debug('V361_FALLBACK',e?.message||e);}}
  return [...map.values()].sort((a,b)=>metadataScore(b,src)-metadataScore(a,src));
}
async function fingerprintRendered(a){
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),6000);try{const r=await fetch(API+'/render?id='+encodeURIComponent(a.stable_id),{signal:ctl.signal,cache:'force-cache'});if(!r.ok)return null;const blob=await r.blob(),bmp=await createImageBitmap(blob),c=document.createElement('canvas');c.width=bmp.width;c.height=bmp.height;c.getContext('2d',{willReadFrequently:true}).drawImage(bmp,0,0);bmp.close?.();return fingerprintCanvas(c);}catch{return null;}finally{clearTimeout(timer);}
}
async function scoreRasterBatch(list,src,srcFp,limit,my){
  const sourceKind=semanticKind(src),sample=list.filter(rasterCandidate).slice(0,limit);let next=0;
  async function worker(){while(my===seq){const i=next++;if(i>=sample.length)return;const a=sample[i],fp=await fingerprintRendered(a);if(my!==seq)return;if(!readableFingerprint(fp,sourceKind)){strictScores.set(a.stable_id,{metadata:metadataScore(a,src),visual:0,silhouette:0,combined:0,rejected:true});continue;}const pix=pixelScore(srcFp,fp),sil=silhouetteScore(srcFp,fp),meta=metadataScore(a,src),combined=.43*pix+.47*sil+.10*meta;strictScores.set(a.stable_id,{metadata:meta,visual:pix,silhouette:sil,combined});}}
  await Promise.all(Array.from({length:4},()=>worker()));
}
function strongModelCandidate(a,src){const m=metadataScore(a,src);return modelCandidate(a)&&m>=.60;}
function buildResults(candidates,src){
  const out=[];for(const a of candidates){const s=strictScores.get(a.stable_id);if(s?.rejected)continue;if(s&&s.visual!=null){if(s.visual>=MIN_VISUAL&&s.combined>=MIN_COMBINED)out.push(a);continue;}if(strongModelCandidate(a,src)){strictScores.set(a.stable_id,{metadata:metadataScore(a,src),visual:null,silhouette:null,combined:metadataScore(a,src)*.82});out.push(a);}}
  out.sort((a,b)=>(strictScores.get(b.stable_id)?.combined||0)-(strictScores.get(a.stable_id)?.combined||0));return out.slice(0,RESULT_LIMIT);
}
function addBadges(){
  const cards=[...document.querySelectorAll('#results .card')];cards.forEach((card,i)=>{card.querySelectorAll('[data-v361-score]').forEach(x=>x.remove());const a=items[i],s=strictScores.get(a?.stable_id);if(!s)return;const b=document.createElement('span');b.dataset.v361Score='1';b.className='avail preview-good';b.textContent=(s.visual==null?'PROCHE FORME ':'SIMILAIRE VISUEL ')+Math.round((s.combined||0)*100)+' %';card.appendChild(b);});
}
function updateSummary(t){const f=document.querySelector('#filterSummary');if(f)f.innerHTML=`<span class="filterchip">${esc(t)}</span>`;}

async function runStrictVisual(src){
  if(!src)return;const my=++seq,srcFp=sourceFingerprint();strictSource=src;strictScores.clear();const audit=window.WFGGVisibilitySimilarityV35?.audit?.()||{},resumeAudit=!!audit.running&&!audit.paused;if(resumeAudit)window.WFGGVisibilitySimilarityV35?.pause?.();
  const stage=document.querySelector('#stage');stage.innerHTML='<div class="empty"><b>Recherche visuelle stricte…</b><br><span class="hint">Textures, planches techniques et familles sans rapport sont exclues avant comparaison.</span></div>';
  try{
    const candidates=await collectCandidates(src);if(my!==seq)return;if(!srcFp){for(const a of candidates)strictScores.set(a.stable_id,{metadata:metadataScore(a,src),visual:null,silhouette:null,combined:metadataScore(a,src)*.82});}
    else await scoreRasterBatch(candidates,src,srcFp,FIRST_VISUAL_SAMPLE,my);if(my!==seq)return;
    let found=buildResults(candidates,src);
    if(!found.length)found=candidates.filter(a=>strongModelCandidate(a,src)).slice(0,12);
    strictActive=true;items=found;idx=-1;currentAsset=null;currentModel?.destroy?.();currentModel=null;if(currentUrl){try{URL.revokeObjectURL(currentUrl)}catch{}currentUrl=null;}renderList();const rc=document.querySelector('#resultCount');if(rc)rc.textContent=String(items.length);updateSummary(`🔎 ${items.length} similaires visuels stricts · textures/atlases exclus`);if(items.length)select(0);else stage.innerHTML='<div class="empty"><b>Aucun résultat visuellement assez proche.</b><br><span class="hint">Le moteur préfère maintenant ne rien proposer plutôt que montrer des faux positifs.</span></div>';
    if(srcFp&&my===seq){(async()=>{try{await scoreRasterBatch(candidates.slice(FIRST_VISUAL_SAMPLE),src,srcFp,BACKGROUND_SAMPLE,my);if(my!==seq||!strictActive)return;const activeSid=currentAsset?.stable_id||'',better=buildResults(candidates,src);if(better.length){items=better;const ni=activeSid?items.findIndex(x=>x.stable_id===activeSid):-1;idx=ni>=0?ni:Math.min(idx,items.length-1);renderList();updateSummary(`🔎 ${items.length} similaires visuels stricts · affinage terminé`);}}finally{if(resumeAudit&&my===seq)window.WFGGVisibilitySimilarityV35?.resume?.();}})();}else if(resumeAudit)window.WFGGVisibilitySimilarityV35?.resume?.();
  }catch(e){stage.innerHTML=`<div class="empty error">Recherche visuelle impossible : ${esc(e?.message||e)}</div>`;if(resumeAudit)window.WFGGVisibilitySimilarityV35?.resume?.();}
}

function installWrappers(){
  if(wrappersInstalled||typeof renderList!=='function'||typeof renderMeta!=='function'||typeof runSearch!=='function')return false;wrappersInstalled=true;
  const baseRenderList=renderList;renderList=function(){const r=baseRenderList();if(strictActive)addBadges();return r;};
  const baseRunSearch=runSearch;
  const baseRenderMeta=renderMeta;renderMeta=function(a,m=null){baseRenderMeta(a,m);const tools=document.querySelector('#meta .tools');if(!tools)return;if(strictActive&&!tools.querySelector('#backFromV361')){const b=document.createElement('button');b.id='backFromV361';b.textContent='↩ Retour recherche';b.onclick=()=>{seq++;strictActive=false;strictSource=null;strictScores.clear();manualMode=false;requestedMode='visual';try{window.WFGGVisualSimilarityV36?.setMode?.('visual');localStorage.setItem('wfgg-similarity-mode-v36','visual');}catch{}baseRunSearch();};tools.appendChild(b);}forceDefaultSelector();};
  runSearch=async function(){if(strictActive){seq++;strictActive=false;strictSource=null;strictScores.clear();}return baseRunSearch();};
  return true;
}
function forceDefaultSelector(){
  const sel=document.querySelector('#simModeV36');if(!sel)return;if(!manualMode){sel.value='visual';requestedMode='visual';try{window.WFGGVisualSimilarityV36?.setMode?.('visual');localStorage.setItem('wfgg-similarity-mode-v36','visual');}catch{}}
}

document.addEventListener('change',e=>{if(e.target?.id!=='simModeV36')return;manualMode=true;requestedMode=e.target.value||'visual';},true);
document.addEventListener('click',e=>{
  const b=e.target?.closest?.('#findSimilar');if(!b)return;
  if(manualMode&&requestedMode!=='visual')return;
  e.preventDefault();e.stopImmediatePropagation();requestedMode='visual';try{window.WFGGVisualSimilarityV36?.setMode?.('visual');localStorage.setItem('wfgg-similarity-mode-v36','visual');}catch{}runStrictVisual(currentAsset);
},true);

try{localStorage.setItem('wfgg-similarity-mode-v36','visual');window.WFGGVisualSimilarityV36?.setMode?.('visual');}catch{}
function boot(){if(!installWrappers())setTimeout(boot,120);else setTimeout(forceDefaultSelector,0);}
boot();
new MutationObserver(()=>forceDefaultSelector()).observe(document.documentElement,{subtree:true,childList:true});
window.WFGGStrictVisualV361={version:'36.1',run:runStrictVisual,state:()=>({active:strictActive,source:strictSource?.stable_id||null,manualMode,requestedMode,results:strictActive?items.length:0})};
console.info('V36_1_STRICT_VISUAL installed default=VISUAL source-auto-texture=BLOCKED semantic-kind=STRICT technical-sheets=EXCLUDED');
})();
