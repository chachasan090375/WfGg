(()=>{
'use strict';
/* Explorer UI bootstrap / final navigation semantics.
   Loaded after search-correlation-v33.js and the injected V34 accelerator.
   This final wrapper owns the user-facing browsing semantics:
   - keep the selected card centered immediately;
   - classify animation FBX files as non-autonomous components;
   - silently skip terminal runtime failures instead of showing technical panels;
   - preserve real final diagnostics in console/Termux for development;
   - load V35 automatic visibility audit + similar-image exploration;
   - load V35 texture-sheet filtering and 3D texture UX;
   - load V35.3 progressive/non-blocking similarity UX.
*/

function installTransientErrorGuard(){
  try{
    if(typeof errorMarkup!=='function')return;
    const baseErrorMarkup=errorMarkup;
    errorMarkup=function(raw,kind='2D',extra=''){
      const text=String(raw||'');
      const pendingFallback=kind==='3D' && /Tentative automatique|rendu raster réel de secours/i.test(String(extra||''));
      const legacyMismatch=/RUNTIME_3D_OBJECT_MISMATCH|RUNTIME_3D_NO_STANDALONE_MESH/.test(text);
      if(pendingFallback&&legacyMismatch){
        return '<div class="empty"><b>Recherche du meilleur aperçu disponible…</b><br><span class="hint">Vérification silencieuse des voies de rendu exactes.</span></div>';
      }
      return baseErrorMarkup(raw,kind,extra);
    };
    console.info('V34_TRANSIENT_3D_ERROR_GUARD installed');
  }catch(e){console.debug('V34_TRANSIENT_3D_ERROR_GUARD failed',e);}
}

function ensureAccelerator(){
  if(window.WFGGPreviewAccelerator)return;
  if(document.querySelector('script[data-wfgg-preview-accelerator]'))return;
  const s=document.createElement('script');
  s.src='/lab/global-graphics-v33/preview-accelerator-v34.js?v=348';
  s.dataset.wfggPreviewAccelerator='1';
  s.onload=()=>{console.info('V34_PREVIEW_ACCEL direct-loader=OK');installSelectionSemantics();};
  s.onerror=()=>console.debug('V34_PREVIEW_ACCEL direct-loader=MISS; injected copy may already be active');
  document.head.appendChild(s);
}

function ensureV35Tools(){
  if(window.WFGGVisibilitySimilarityV35)return;
  if(document.querySelector('script[data-wfgg-v35-tools]'))return;
  const s=document.createElement('script');
  s.src='/lab/global-graphics-v33/visibility-similarity-v35.js?v=351';
  s.dataset.wfggV35Tools='1';
  s.onload=()=>{console.info('V35_VISIBILITY_SIMILARITY loader=OK');ensureV35FastSimilarity();};
  s.onerror=()=>console.warn('V35_VISIBILITY_SIMILARITY loader=MISS');
  document.head.appendChild(s);
}

function ensureV35TextureExperience(){
  if(window.WFGGTextureExperienceV35)return;
  if(document.querySelector('script[data-wfgg-v35-texture-experience]'))return;
  const s=document.createElement('script');
  s.src='/lab/global-graphics-v33/texture-experience-v35.js?v=352';
  s.dataset.wfggV35TextureExperience='1';
  s.onload=()=>console.info('V35_TEXTURE_EXPERIENCE loader=OK');
  s.onerror=()=>console.warn('V35_TEXTURE_EXPERIENCE loader=MISS');
  document.head.appendChild(s);
}

function ensureV35FastSimilarity(){
  if(window.WFGGFastSimilarityV35)return;
  if(document.querySelector('script[data-wfgg-v35-fast-similarity]'))return;
  const s=document.createElement('script');
  s.src='/lab/global-graphics-v33/similarity-fast-v35.js?v=353';
  s.dataset.wfggV35FastSimilarity='1';
  s.onload=()=>console.info('V35_FAST_SIMILARITY loader=OK');
  s.onerror=()=>console.warn('V35_FAST_SIMILARITY loader=MISS');
  document.head.appendChild(s);
}

function pathOf(a){return String(a?.asset_path||a?.logical_name||a?.alias_name||'').replace(/\\/g,'/').toLowerCase();}
function isAnimationAsset(a){
  const p=pathOf(a),role=String(a?.model_role||'').toLowerCase(),tech=String(a?.tech_kind||'').toLowerCase();
  return p.includes('/animation/')||p.endsWith('.anim')||role==='animation'||tech==='animation'||tech==='animationclip';
}
function centerSelected(behavior='smooth'){try{window.WFGGResultStripSync?.(behavior);}catch{}}
function markViewed(a){try{fetch('/api/v33/view',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:a.stable_id}),keepalive:true}).catch(()=>{});}catch{}}

const TERMINAL_RUNTIME=/RUNTIME_NO_LOCAL_BUNDLE|RUNTIME_TARGET_OBJECT_NOT_FOUND|RUNTIME_3D_OBJECT_MISMATCH|RUNTIME_3D_NO_STANDALONE_MESH|Aucune géométrie Mesh décodable|Aucune géométrie OBJ lisible|model-file-not-found|HTTP 404/i;
function terminalFailure(stage){
  const box=stage?.querySelector('.errorbox');if(!box)return null;
  const text=box.textContent||'';
  const details=box.querySelector('#errorDetails')?.textContent||text;
  return TERMINAL_RUNTIME.test(details)?details:null;
}
function correlation(){return window.WFGGSearchCorrelation||null;}
function isRejected(sid){try{return !!correlation()?.isRuntimeRejected?.(sid);}catch{return false;}}
function reject(sid){try{correlation()?.rejectRuntimeId?.(sid);}catch{}}
function nextUsable(from){
  for(let j=Math.max(0,from);j<items.length;j++){const sid=items[j]?.stable_id;if(sid&&!isRejected(sid))return j;}
  return -1;
}
async function skipTerminalFailure(i,a,stage,reason){
  reject(a.stable_id);
  console.warn('V34_FINAL_RUNTIME_SKIPPED',a.stable_id,String(reason).slice(0,900));
  stage.innerHTML='<div class="empty"><b>Recherche du prochain aperçu disponible…</b><br><span class="hint">Cet asset n’est pas prévisualisable dans l’installation locale actuelle ; il est ignoré pour la navigation.</span></div>';
  let wanted=nextUsable(i+1);
  if(wanted<0){
    try{
      const c=correlation();
      if(c?.state?.().hasMore){await c.loadMore?.('final-runtime-skip');wanted=nextUsable(i+1);}
    }catch{}
  }
  if(wanted>=0){setTimeout(()=>select(wanted),0);return true;}
  for(let j=Math.min(i-1,items.length-1);j>=0;j--){if(!isRejected(items[j]?.stable_id)){setTimeout(()=>select(j),0);return true;}}
  stage.innerHTML='<div class="empty"><b>Aucun aperçu décodable dans cette sélection.</b><br><span class="hint">Les fichiers restent indexés et recherchables, mais aucun rendu local exploitable n’a été trouvé.</span></div>';
  return true;
}

let semanticsInstalled=false;
function installSelectionSemantics(){
  if(semanticsInstalled||typeof select!=='function')return;
  semanticsInstalled=true;
  const baseSelect=select;
  select=async function(i){
    if(i<0||i>=items.length)return;
    const a=items[i];
    if(isRejected(a?.stable_id)){
      const n=nextUsable(i+1);if(n>=0){setTimeout(()=>select(n),0);return;}
    }

    if(isAnimationAsset(a)){
      idx=i;currentAsset=a;currentRenderMeta=null;currentModel?.destroy?.();currentModel=null;
      if(currentUrl){try{URL.revokeObjectURL(currentUrl)}catch{}currentUrl=null;}
      renderList();renderMeta(a);
      const stage=document.querySelector('#stage');
      stage.innerHTML=`<div class="empty"><b>Animation 3D non autonome</b><br><span class="hint">Ce fichier contient une animation destinée à un modèle ou à un squelette. Il n’a pas de géométrie autonome à afficher seul.</span></div>${nav()}`;
      bindNav();markViewed(a);requestAnimationFrame(()=>centerSelected('smooth'));setTimeout(()=>centerSelected('smooth'),80);
      console.debug('V34_ANIMATION_COMPONENT',a.stable_id,pathOf(a));return;
    }

    const task=baseSelect(i);
    requestAnimationFrame(()=>centerSelected('smooth'));setTimeout(()=>centerSelected('smooth'),70);
    try{await task;}
    finally{requestAnimationFrame(()=>centerSelected('smooth'));}

    if(currentAsset?.stable_id===a.stable_id){
      const stage=document.querySelector('#stage'),reason=terminalFailure(stage);
      if(reason){await skipTerminalFailure(i,a,stage,reason);return;}
    }
  };
  console.info('V34_SELECTION_SEMANTICS installed card-centering=IMMEDIATE animation-fbx=NONAUTONOMOUS terminal-runtime=AUTOSKIP');
}

async function refreshStatus(){
  try{
    const r=await fetch('/api/v33/explorer-status',{cache:'no-store'});if(!r.ok)return;
    const d=await r.json();window.WFGGExplorerV33={version:'35.3',status:d,ready:true,accelerator:!!window.WFGGPreviewAccelerator,textureViewer:window.WFGGModelViewer?.cacheStats?.()?.uvTextureViewer||null,fastSimilarity:!!window.WFGGFastSimilarityV35};
  }catch(e){window.WFGGExplorerV33={version:'35.3',ready:false,error:String(e)};}
}

installTransientErrorGuard();ensureAccelerator();installSelectionSemantics();ensureV35Tools();ensureV35TextureExperience();ensureV35FastSimilarity();
setTimeout(installSelectionSemantics,60);setTimeout(installSelectionSemantics,250);setTimeout(ensureV35Tools,400);setTimeout(ensureV35TextureExperience,500);setTimeout(ensureV35FastSimilarity,700);refreshStatus();
})();
