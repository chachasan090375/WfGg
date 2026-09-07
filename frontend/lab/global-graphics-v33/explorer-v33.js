(()=>{
'use strict';
/* Explorer UI bootstrap.
   This file is also the last-resort compatibility guard for the V34 preview path:
   - guarantee that preview-accelerator-v34.js is installed even if an older injected
     search-correlation response reaches the browser;
   - never flash the old RUNTIME_3D_OBJECT_MISMATCH panel while the base viewer is still
     attempting its legitimate raster fallback.
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
  s.src='/lab/global-graphics-v33/preview-accelerator-v34.js?v=344';
  s.dataset.wfggPreviewAccelerator='1';
  s.onload=()=>console.info('V34_PREVIEW_ACCEL direct-loader=OK');
  s.onerror=()=>console.debug('V34_PREVIEW_ACCEL direct-loader=MISS; injected copy may already be active');
  document.head.appendChild(s);
}

async function refreshStatus(){
  try{
    const r=await fetch('/api/v33/explorer-status',{cache:'no-store'});if(!r.ok)return;
    const d=await r.json();
    window.WFGGExplorerV33={version:'33.2',status:d,ready:true,accelerator:!!window.WFGGPreviewAccelerator};
  }catch(e){window.WFGGExplorerV33={version:'33.2',ready:false,error:String(e)};}
}

installTransientErrorGuard();
ensureAccelerator();
refreshStatus();
})();
