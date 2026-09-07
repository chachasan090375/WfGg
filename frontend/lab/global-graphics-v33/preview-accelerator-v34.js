(()=>{
'use strict';

/* V34.8 mobile preview accelerator.
   The legacy inline viewer can begin init() before injected enhancements finish loading. This file
   therefore guards the whole boot/navigation window, not only the instant at which it is loaded:
   transitional legacy 3D/2D errors are neutralized while the V34 exact model/raster path is still
   working. Final V34 errors remain visible and are explicitly marked for the early shield. */

let previewSeq=0;
let rasterController=null;
let finalErrorVisible=false;
const modelManifestCache=new Map();
const warmJobs=new Map();
const MAX_MANIFEST_CACHE=14;
const MAX_WARM_AHEAD=2;

function roleOf(a){return String(a?.model_role||'').toLowerCase();}
function dimOf(a){return String(a?.dimension_class||'');}
function techOf(a){return String(a?.tech_kind||'').toLowerCase();}
function pathOf(a){return String(a?.asset_path||a?.logical_name||a?.alias_name||'').replace(/\\/g,'/').toLowerCase();}
function looksPrefabAsset(a){const p=pathOf(a);return p.endsWith('.prefab')||p.includes('/prefab/');}
function looksEffectAsset(a){const p=pathOf(a);const tail=p.rsplit?null:null;return p.includes('/effect/')||p.includes('/effects/')||p.includes('/vfx/')||/(^|\/)(eff_|fx_|vfx_)/.test(p)||/particle|particlesystem|visualeffect/.test(p);}
function targetNotFound(msg){return /RUNTIME_TARGET_OBJECT_NOT_FOUND/.test(String(msg||''));}
function passive3DComponent(a){
  const r=roleOf(a);
  return dimOf(a)==='Composant 3D' && ['material','shader','animation','component','texture'].includes(r);
}
function nonAutonomousModelError(msg){return /RUNTIME_3D_NO_STANDALONE_MESH|PTR3D_NO_MESH_POINTER/.test(String(msg||''));}
function modelCandidate(a){
  const r=roleOf(a),d=dimOf(a);
  if(['geometry','geometry-candidate','prefab'].includes(r))return true;
  if(d==='3D'&&!['material','shader','animation','component','texture'].includes(r))return true;
  if(d==='Mixte 2D/3D'&&r!=='material'&&r!=='shader')return true;
  // Many catalogue rows have dimension=Composant 3D but no model_role even though the exact
  // source path is a prefab. Treat those as real model candidates instead of sending them only
  // through the raster decoder (which is what produced the old TARGET_OBJECT_NOT_FOUND panel).
  if(d==='Composant 3D'&&looksPrefabAsset(a)&&!['material','shader','animation','texture'].includes(r))return true;
  return false;
}
function rasterCandidate(a){
  const t=techOf(a),r=roleOf(a),d=dimOf(a);
  if(d==='2D'||d==='Mixte 2D/3D')return true;
  if(/sprite|texture|atlas|image|png|jpg|jpeg/.test(t))return true;
  if(['texture','material'].includes(r))return true;
  return modelCandidate(a)||String(a?.graphic_class||'').includes('graphique');
}
function trimMap(map,max){while(map.size>max){const k=map.keys().next().value;map.delete(k);}}

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
    }catch(e){console.debug('V34_PREWARM_MISS',sid,e?.message||e);}
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
    for(const a of targets){if(seq!==previewSeq)return;await warmModel(a);}
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
  const missingTarget=looksEffectAsset(a)&&(targetNotFound(modelError)||targetNotFound(rasterError));
  const headline=exactNoMesh?'Composant 3D sans Mesh autonome':missingTarget?'Effet 3D non autonome':'Composant 3D non autonome';
  const detail=exactNoMesh
    ?'Le graphe Unity exact de ce prefab a été trouvé, mais il ne référence aucun Mesh autonome. Il s’agit typiquement d’un effet, de particules ou d’un composant utilisé dans une scène.'
    :missingTarget
      ?'Ce prefab d’effet participe à une scène ou à un assemblage et ne possède pas de cible raster ou Mesh autonome identifiable à afficher seul.'
      :`${label} : cet élément participe à un assemblage, mais ne contient pas forcément une géométrie ou une image affichable seul.`;
  stage.innerHTML=`<div class="empty"><b>${esc(headline)}</b><br><span class="hint">${esc(detail)}</span></div>${nav()}`;
  bindNav();console.debug('V34_COMPONENT_NO_STANDALONE_PREVIEW',a.stable_id,{modelError,rasterError});
}

/* The old inline select() can still be awaiting /model or /render when this enhancement loads.
   Its two catch blocks call errorMarkup(). Intercept only those transitional calls. The final V34
   path below sets finalErrorVisible=true before using errorMarkup, so genuine final diagnostics
   remain visible. */
const legacyErrorMarkup=errorMarkup;
function transitionalLegacyError(raw,kind,extra){
  if(finalErrorVisible)return false;
  if(!currentAsset||!modelCandidate(currentAsset))return false;
  const x=String(extra||''),r=String(raw||'');
  const legacyPhase=/Tentative automatique d.un rendu raster réel de secours|Cette erreur concerne le décodage\/reconstruction/.test(x);
  const known=/RUNTIME_3D_OBJECT_MISMATCH|RUNTIME_TARGET_OBJECT_NOT_FOUND|model-file-not-found|404/.test(r);
  return legacyPhase&&(kind==='3D'||known);
}
errorMarkup=function(raw,kind='2D',extra=''){
  if(transitionalLegacyError(raw,kind,extra)){
    return `<div class="empty"><b>Finalisation de l’aperçu…</b><br><span class="hint">Le moteur V34 poursuit la reconstruction exacte. Le diagnostic intermédiaire reste dans la console.</span></div>`;
  }
  return legacyErrorMarkup(raw,kind,extra);
};

function suppressLegacyStage(stage){
  if(!stage||finalErrorVisible)return false;
  const box=stage.querySelector('.errorbox');if(!box)return false;
  const text=box.textContent||'';
  if(!currentAsset||!modelCandidate(currentAsset))return false;
  if(!/RUNTIME_3D_OBJECT_MISMATCH|RUNTIME_TARGET_OBJECT_NOT_FOUND|Assemblage 3D indisponible|Rendu local impossible/.test(text))return false;
  loading(stage,'Finalisation de l’aperçu…','La reconstruction exacte est toujours en cours ; aucune erreur intermédiaire n’est affichée.');
  return true;
}

async function acceleratedSelect(i){
  if(i<0||i>=items.length)return;
  const my=++previewSeq;finalErrorVisible=false;
  try{rasterController?.abort();}catch{}rasterController=null;
  idx=i;currentAsset=items[i];currentRenderMeta=null;currentModel?.destroy?.();currentModel=null;renderList();
  const a=currentAsset,stage=document.querySelector('#stage');
  if(currentUrl){try{URL.revokeObjectURL(currentUrl)}catch{}currentUrl=null;}
  renderMeta(a);

  if(a.render_availability==='global-index-only'){
    stage.innerHTML=`<div class="empty"><b>Asset indexé globalement.</b><br><span class="warn">Le bundle correspondant n’est pas présent dans l’installation Last War actuelle.</span><br><span class="hint">Il reste recherchable et classé, mais le LAB ne fabrique pas de faux rendu.</span></div>${nav()}`;
    bindNav();markViewed(a);return;
  }

  let modelError='',rasterError='';const started=performance.now();
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
      modelError=String(e?.message||e||'assemblage 3D impossible');console.debug('V34_PREVIEW_3D_FALLBACK',a.stable_id,modelError);
      if(my!==previewSeq)return;
      const noMesh=nonAutonomousModelError(modelError);
      loading(stage,noMesh?'Composant sans Mesh autonome — recherche du rendu 2D…':'Aperçu 3D non disponible — recherche du rendu 2D…',
        noMesh?'Le prefab est valide mais ne contient pas de géométrie Mesh isolée.':'Le moteur essaie encore le rendu exact de secours.');
    }
  }else if(passive3DComponent(a))loading(stage,'Recherche d’un aperçu du composant…','Matériaux, shaders et animations ne sont pas toujours affichables seuls.');
  else loading(stage,'Décodage du rendu…','Lecture de l’asset exact dans les bundles locaux.');

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
      bindNav();renderMeta(a);markViewed(a);console.debug('V34_PREVIEW_RASTER_OK',a.stable_id,Math.round(performance.now()-started)+'ms');scheduleWarm(i);return;
    }catch(e){
      if(e?.name==='AbortError')return;
      rasterError=String(e?.message||e||'rendu impossible');console.debug('V34_PREVIEW_RASTER_FAIL',a.stable_id,rasterError);if(my!==previewSeq)return;
    }
  }

  // A proven no-Mesh graph or an Effect/Prefab with no standalone target is a semantic component
  // state, not a broken viewer. Keep its technical details in console/Termux instead of red UI.
  if(passive3DComponent(a)||nonAutonomousModelError(modelError)||(looksEffectAsset(a)&&(targetNotFound(modelError)||targetNotFound(rasterError)))){
    componentNeutral(stage,a,modelError,rasterError);markViewed(a);scheduleWarm(i);return;
  }

  finalErrorVisible=true;
  const details=[modelError&&('3D: '+modelError),rasterError&&('2D: '+rasterError)].filter(Boolean).join('\n\n')||'Aucun chemin de prévisualisation exploitable.';
  const kind=modelCandidate(a)?'3D':'2D';
  stage.innerHTML=legacyErrorMarkup(details,kind,'Toutes les voies de prévisualisation exactes ont été essayées. Cette erreur est maintenant définitive pour cet asset dans l’installation locale actuelle.')+nav();
  const finalBox=stage.querySelector('.errorbox');if(finalBox)finalBox.dataset.v34Final='1';
  bindErrorDetails();bindNav();markViewed(a);
}

select=acceleratedSelect;

/* Always-on guard for the first 30 seconds. The early model-viewer guard is already active before
   base init(); this second guard covers later legacy async responses that were already in flight. */
const stageGuard=document.querySelector('#stage');
let guardObserver=null;
if(stageGuard){
  guardObserver=new MutationObserver(()=>{
    if(stageGuard.querySelector('canvas,#assetImg'))return;
    suppressLegacyStage(stageGuard);
  });
  guardObserver.observe(stageGuard,{childList:true,subtree:true});
  setTimeout(()=>{guardObserver?.disconnect();guardObserver=null;},30000);
}

let bootTakeoverDone=false;
function tryBootTakeover(){
  if(bootTakeoverDone)return;
  if(idx>=0&&currentAsset){bootTakeoverDone=true;acceleratedSelect(idx);}
}
[0,40,120,300,700,1400].forEach(ms=>setTimeout(tryBootTakeover,ms));

window.WFGGPreviewAccelerator={
  version:'34.8',modelCandidate,warmModel,
  state:()=>({previewSeq,manifestCache:modelManifestCache.size,warmJobs:warmJobs.size,finalErrorVisible,viewerCache:window.WFGGModelViewer?.cacheStats?.()||null})
};
console.info('V34_PREVIEW_ACCEL installed early-shield=EXPECTED component-prefab-model=ON effect-target-miss=NONAUTONOMOUS model-prewarm='+MAX_WARM_AHEAD);
})();