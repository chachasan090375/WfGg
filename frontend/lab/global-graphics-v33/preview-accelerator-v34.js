(()=>{
'use strict';

/* V34 mobile preview accelerator.
   - never flashes a red error while another exact fallback is still running;
   - does not ask the 3D assembler to build autonomous models for pure material/shader/animation rows;
   - prewarms the next useful 3D results only after the current preview is visible;
   - shares model-manifest promises with foreground navigation so a prewarm is never duplicated;
   - treats an exact prefab graph with no Mesh pointer as a legitimate non-autonomous VFX/component,
     not as a viewer failure;
   - leaves final technical failures available only when every legitimate preview path has failed. */

let previewSeq=0;
let rasterController=null;
const modelManifestCache=new Map();
const warmJobs=new Map();
const MAX_MANIFEST_CACHE=14;
const MAX_WARM_AHEAD=2;

function roleOf(a){return String(a?.model_role||'').toLowerCase();}
function dimOf(a){return String(a?.dimension_class||'');}
function techOf(a){return String(a?.tech_kind||'').toLowerCase();}

function passive3DComponent(a){
  const r=roleOf(a);
  return dimOf(a)==='Composant 3D' && ['material','shader','animation','component','texture'].includes(r);
}

function nonAutonomousModelError(msg){
  const text=String(msg||'');
  return /RUNTIME_3D_NO_STANDALONE_MESH|PTR3D_NO_MESH_POINTER/.test(text);
}

function modelCandidate(a){
  const r=roleOf(a),d=dimOf(a);
  if(['geometry','geometry-candidate','prefab'].includes(r))return true;
  if(d==='3D'&&!['material','shader','animation','component','texture'].includes(r))return true;
  if(d==='Mixte 2D/3D'&&r!=='material'&&r!=='shader')return true;
  return false;
}

function rasterCandidate(a){
  const t=techOf(a),r=roleOf(a),d=dimOf(a);
  if(d==='2D'||d==='Mixte 2D/3D')return true;
  if(/sprite|texture|atlas|image|png|jpg|jpeg/.test(t))return true;
  if(['texture','material'].includes(r))return true;
  // Exact raster fallback remains useful for VFX prefabs whose visible representation is texture-driven.
  return modelCandidate(a)||String(a?.graphic_class||'').includes('graphique');
}

function trimMap(map,max){
  while(map.size>max){const k=map.keys().next().value;map.delete(k);}
}

function modelManifest(a){
  const sid=a.stable_id;
  if(modelManifestCache.has(sid)){
    const p=modelManifestCache.get(sid);modelManifestCache.delete(sid);modelManifestCache.set(sid,p);return p;
  }
  const p=(async()=>{
    const r=await fetch(API+'/model?id='+encodeURIComponent(sid),{cache:'no-store'});
    const d=await r.json();
    if(!r.ok)throw new Error(d.message||d.error||'assemblage 3D impossible');
    return d.model;
  })();
  modelManifestCache.set(sid,p);trimMap(modelManifestCache,MAX_MANIFEST_CACHE);
  p.catch(()=>{if(modelManifestCache.get(sid)===p)modelManifestCache.delete(sid);});
  return p;
}

async function warmModel(a){
  if(!a||!modelCandidate(a)||a.render_availability==='global-index-only')return;
  const sid=a.stable_id;if(warmJobs.has(sid))return warmJobs.get(sid);
  const job=(async()=>{
    const started=performance.now();
    try{
      const manifest=await modelManifest(a);
      await window.WFGGModelViewer?.prefetch?.(manifest);
      console.debug('V34_PREWARM_OK',sid,Math.round(performance.now()-started)+'ms');
    }catch(e){
      console.debug('V34_PREWARM_MISS',sid,e?.message||e);
    }
  })();
  warmJobs.set(sid,job);
  try{await job;}finally{setTimeout(()=>warmJobs.delete(sid),30000);}
}

function scheduleWarm(from){
  const seq=previewSeq;
  setTimeout(async()=>{
    if(seq!==previewSeq)return;
    const targets=[];
    for(let j=from+1;j<items.length&&targets.length<MAX_WARM_AHEAD;j++){
      const a=items[j];if(modelCandidate(a)&&a.render_availability!=='global-index-only')targets.push(a);
    }
    // Sequential on purpose: foreground interaction always keeps CPU/I/O priority.
    for(const a of targets){
      if(seq!==previewSeq)return;
      await warmModel(a);
    }
  },180);
}

function loading(stage,title,detail=''){
  stage.innerHTML=`<div class="empty"><b>${esc(title)}</b>${detail?`<br><span class="hint">${esc(detail)}</span>`:''}</div>${nav()}`;
  bindNav();
}

function markViewed(a){
  try{fetch(API+'/view',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:a.stable_id}),keepalive:true}).catch(()=>{});}catch{}
}

function componentNeutral(stage,a,modelError,rasterError){
  const label=roleOf(a)||'composant';
  const exactNoMesh=nonAutonomousModelError(modelError);
  const headline=exactNoMesh?'Composant 3D sans Mesh autonome':'Composant 3D non autonome';
  const detail=exactNoMesh
    ?'Le graphe Unity exact de ce prefab a été trouvé, mais il ne référence aucun Mesh autonome. Il s’agit typiquement d’un effet, de particules ou d’un composant utilisé dans une scène.'
    :`${label} : cet élément participe à un assemblage, mais ne contient pas forcément une géométrie ou une image affichable seul.`;
  stage.innerHTML=`<div class="empty"><b>${esc(headline)}</b><br><span class="hint">${esc(detail)}</span></div>${nav()}`;
  bindNav();
  console.debug('V34_COMPONENT_NO_STANDALONE_PREVIEW',a.stable_id,{modelError,rasterError});
}

async function acceleratedSelect(i){
  if(i<0||i>=items.length)return;
  const my=++previewSeq;
  try{rasterController?.abort();}catch{}
  rasterController=null;

  idx=i;currentAsset=items[i];currentRenderMeta=null;currentModel?.destroy?.();currentModel=null;renderList();
  const a=currentAsset,stage=document.querySelector('#stage');
  if(currentUrl){try{URL.revokeObjectURL(currentUrl)}catch{}currentUrl=null;}
  renderMeta(a);

  if(a.render_availability==='global-index-only'){
    stage.innerHTML=`<div class="empty"><b>Asset indexé globalement.</b><br><span class="warn">Le bundle correspondant n’est pas présent dans l’installation Last War actuelle.</span><br><span class="hint">Il reste recherchable et classé, mais le LAB ne fabrique pas de faux rendu.</span></div>${nav()}`;
    bindNav();markViewed(a);return;
  }

  let modelError='';let rasterError='';const started=performance.now();

  if(modelCandidate(a)){
    loading(stage,'Préparation du modèle 3D…','Passe rapide exacte, puis approfondissement uniquement si nécessaire.');
    try{
      const manifest=await modelManifest(a);if(my!==previewSeq)return;
      stage.innerHTML='';
      const mounted=await WFGGModelViewer.mount(stage,manifest);
      if(my!==previewSeq){mounted?.destroy?.();return;}
      currentModel=mounted;stage.insertAdjacentHTML('beforeend',nav());bindNav();renderMeta(a,manifest);markViewed(a);
      console.debug('V34_PREVIEW_3D_OK',a.stable_id,Math.round(performance.now()-started)+'ms',manifest.assemblySpeed||manifest.correlation||'');
      scheduleWarm(i);return;
    }catch(e){
      modelError=String(e?.message||e||'assemblage 3D impossible');
      console.debug('V34_PREVIEW_3D_FALLBACK',a.stable_id,modelError);
      if(my!==previewSeq)return;
      // Important UX rule: this is not a visible error yet because a real raster fallback remains possible.
      const noMesh=nonAutonomousModelError(modelError);
      loading(stage,noMesh?'Composant sans Mesh autonome — recherche du rendu 2D…':'Aperçu 3D non disponible — recherche du rendu 2D…',
        noMesh?'Le prefab est valide mais ne contient pas de géométrie Mesh isolée.':'Aucune erreur rouge n’est affichée tant que les solutions de secours exactes ne sont pas terminées.');
    }
  }else if(passive3DComponent(a)){
    loading(stage,'Recherche d’un aperçu du composant…','Matériaux, shaders et animations ne sont pas toujours affichables seuls.');
  }else{
    loading(stage,'Décodage du rendu…','Lecture de l’asset exact dans les bundles locaux.');
  }

  if(rasterCandidate(a)){
    rasterController=new AbortController();
    try{
      const r=await fetch(API+'/render?id='+encodeURIComponent(a.stable_id),{signal:rasterController.signal,cache:'no-store'});
      if(!r.ok){const e=await r.json();throw new Error(e.message||e.error||'rendu impossible');}
      const mh=r.headers.get('X-WfGg-Render-Meta');if(mh)try{currentRenderMeta=JSON.parse(mh)}catch{}
      const blob=await r.blob();if(my!==previewSeq)return;
      currentUrl=URL.createObjectURL(blob);
      const fallback=modelError?' · SECOURS APRÈS 3D':'';
      stage.innerHTML=`<img id="assetImg" src="${currentUrl}" alt="${esc(a.alias_name||a.stable_id)}"><span class="badge">RENDU 2D RÉEL${fallback} · b${esc(a.bundle_id)}</span>${nav()}`;
      bindNav();renderMeta(a);markViewed(a);
      console.debug('V34_PREVIEW_RASTER_OK',a.stable_id,Math.round(performance.now()-started)+'ms');
      scheduleWarm(i);return;
    }catch(e){
      if(e?.name==='AbortError')return;
      rasterError=String(e?.message||e||'rendu impossible');
      console.debug('V34_PREVIEW_RASTER_FAIL',a.stable_id,rasterError);
      if(my!==previewSeq)return;
    }
  }

  // A proven exact no-Mesh prefab is not an error. It is a valid VFX/component with no standalone
  // preview. Present that semantic state even when it is technically classified as model_role=prefab.
  if(passive3DComponent(a)||nonAutonomousModelError(modelError)){
    componentNeutral(stage,a,modelError,rasterError);markViewed(a);scheduleWarm(i);return;
  }

  const details=[modelError&&('3D: '+modelError),rasterError&&('2D: '+rasterError)].filter(Boolean).join('\n\n')||'Aucun chemin de prévisualisation exploitable.';
  const kind=modelCandidate(a)?'3D':'2D';
  stage.innerHTML=errorMarkup(details,kind,'Toutes les voies de prévisualisation exactes ont été essayées. Cette erreur est maintenant définitive pour cet asset dans l’installation locale actuelle.')+nav();
  bindErrorDetails();bindNav();markViewed(a);
}

// Install after search-correlation-v33.js: runSearch/renderList/bindNav will resolve this new function dynamically.
select=acceleratedSelect;
window.WFGGPreviewAccelerator={
  version:'34.4',
  modelCandidate,
  warmModel,
  state:()=>({previewSeq,manifestCache:modelManifestCache.size,warmJobs:warmJobs.size,viewerCache:window.WFGGModelViewer?.cacheStats?.()||null})
};
console.info('V34_PREVIEW_ACCEL installed neutral-fallback=ON exact-no-mesh=NONAUTONOMOUS model-prewarm='+MAX_WARM_AHEAD);
})();
