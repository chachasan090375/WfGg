(()=>{
'use strict';
/* Explorer UI bootstrap / final navigation semantics.
   Loaded after search-correlation-v33.js (and therefore after the injected V34 accelerator).
   Responsibilities here are intentionally UI-level:
   - guarantee accelerator availability;
   - keep the selected result card centered immediately on every explicit selection;
   - treat FBX/animation assets as non-autonomous animation components instead of failed 3D models;
   - keep transient legacy diagnostics out of the visible browsing experience.
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
        return '<div class="empty"><b>Recherche du meilleur aperçu disponible…</b><br><span class="hint">Ce composant ne fournit pas de Mesh autonome. Vérification silencieuse du rendu raster exact.</span></div>';
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

function pathOf(a){return String(a?.asset_path||a?.logical_name||a?.alias_name||'').replace(/\\/g,'/').toLowerCase();}
function isAnimationAsset(a){
  const p=pathOf(a),role=String(a?.model_role||'').toLowerCase(),tech=String(a?.tech_kind||'').toLowerCase();
  return p.includes('/animation/')||p.endsWith('.anim')||role==='animation'||tech==='animation'||tech==='animationclip';
}
function centerSelected(behavior='smooth'){
  try{window.WFGGResultStripSync?.(behavior);}catch{}
}
function markViewed(a){
  try{fetch('/api/v33/view',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:a.stable_id}),keepalive:true}).catch(()=>{});}catch{}
}

let semanticsInstalled=false;
function installSelectionSemantics(){
  if(semanticsInstalled||typeof select!=='function')return;
  semanticsInstalled=true;
  const baseSelect=select;
  select=async function(i){
    if(i<0||i>=items.length)return;
    const a=items[i];

    // Animation FBX files describe motion bound to another model/skeleton. Trying to decode them as
    // an autonomous mesh or raster is semantically wrong and only creates a scary false failure.
    if(isAnimationAsset(a)){
      idx=i;currentAsset=a;currentRenderMeta=null;currentModel?.destroy?.();currentModel=null;
      if(currentUrl){try{URL.revokeObjectURL(currentUrl)}catch{}currentUrl=null;}
      renderList();renderMeta(a);
      const stage=document.querySelector('#stage');
      stage.innerHTML=`<div class="empty"><b>Animation 3D non autonome</b><br><span class="hint">Ce fichier contient une animation destinée à un modèle ou à un squelette. Il n’a pas de géométrie autonome à afficher seul.</span></div>${nav()}`;
      bindNav();markViewed(a);
      requestAnimationFrame(()=>centerSelected('smooth'));
      setTimeout(()=>centerSelected('smooth'),80);
      console.debug('V34_ANIMATION_COMPONENT',a.stable_id,pathOf(a));
      return;
    }

    // baseSelect changes idx and rebuilds the strip synchronously before its first await. Center at
    // that exact moment instead of waiting for model/raster decoding, then confirm again at the end.
    const task=baseSelect(i);
    requestAnimationFrame(()=>centerSelected('smooth'));
    setTimeout(()=>centerSelected('smooth'),70);
    try{return await task;}
    finally{requestAnimationFrame(()=>centerSelected('smooth'));}
  };
  console.info('V34_SELECTION_SEMANTICS installed card-centering=IMMEDIATE animation-fbx=NONAUTONOMOUS');
}

async function refreshStatus(){
  try{
    const r=await fetch('/api/v33/explorer-status',{cache:'no-store'});if(!r.ok)return;
    const d=await r.json();
    window.WFGGExplorerV33={version:'33.3',status:d,ready:true,accelerator:!!window.WFGGPreviewAccelerator};
  }catch(e){window.WFGGExplorerV33={version:'33.3',ready:false,error:String(e)};}
}

installTransientErrorGuard();
ensureAccelerator();
installSelectionSemantics();
setTimeout(installSelectionSemantics,60);
setTimeout(installSelectionSemantics,250);
refreshStatus();
})();
