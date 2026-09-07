(()=>{
'use strict';

/* WfGg V37 — real folder/subfolder explorer.
   Uses the existing V33 /api/v33/path/children tree and path_prefix search support.
   The tree is independent from free-text search and combines with normal filters once applied.
*/

const API37='/api/v33';
let activePath='';
let browsePath='';
let treeBusy=false;
let installed=false;
let wrappersInstalled=false;

const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const norm=s=>String(s||'').replace(/\\/g,'/').replace(/^\/+|\/+$/g,'');
const byId=id=>document.getElementById(id);

function injectStyle(){
  if(byId('wfggPathExplorerStyle'))return;
  const st=document.createElement('style');st.id='wfggPathExplorerStyle';st.textContent=`
  #pathExplorerDialog .path-search{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:7px}
  #pathExplorerDialog .path-breadcrumbs{display:flex;gap:5px;flex-wrap:wrap;align-items:center}
  #pathExplorerDialog .path-breadcrumbs button{padding:6px 8px;font-size:11px}
  #pathExplorerDialog .path-current{background:#101722;border:1px solid #293346;border-radius:10px;padding:9px;font:11px ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere;color:var(--muted)}
  #pathExplorerDialog .path-folders{display:grid;gap:6px;max-height:48dvh;overflow:auto;padding-right:2px}
  #pathExplorerDialog .path-folder{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;text-align:left;padding:10px}
  #pathExplorerDialog .path-folder strong{display:block;overflow-wrap:anywhere}
  #pathExplorerDialog .path-folder small{display:block;color:var(--muted);font-size:10px;overflow-wrap:anywhere;margin-top:2px}
  #pathExplorerDialog .path-count{color:var(--muted);font-size:11px;white-space:nowrap}
  #pathExplorerDialog .path-actions{display:grid;grid-template-columns:1fr 1fr;gap:7px}
  #pathExplorerDialog .path-empty{text-align:center;color:var(--muted);padding:18px 8px}
  #openPathExplorer.path-active{border-color:var(--violet);color:#ddd5ff}
  @media(max-width:420px){#pathExplorerDialog .path-search{grid-template-columns:1fr}#pathExplorerDialog .path-actions{grid-template-columns:1fr}}
  `;document.head.appendChild(st);
}

function ensureDialog(){
  let d=byId('pathExplorerDialog');if(d)return d;
  d=document.createElement('dialog');d.id='pathExplorerDialog';d.innerHTML=`
    <div class="modal-shell">
      <div class="modal-head"><h2>📁 Arborescence des assets</h2><button id="closePathExplorer" aria-label="Fermer">✕</button></div>
      <div class="modal-body" style="display:grid;grid-template-columns:1fr">
        <div class="path-search"><input id="pathFolderQuery" placeholder="Rechercher un dossier…" autocomplete="off"><button id="pathFolderSearch">Rechercher</button></div>
        <div id="pathBreadcrumbs" class="path-breadcrumbs"></div>
        <div id="pathCurrent" class="path-current">Racine</div>
        <div id="pathFolderStatus" class="hint">Chargement…</div>
        <div id="pathFolders" class="path-folders"></div>
        <div class="path-actions">
          <button id="pathShowVisible" class="primary">Afficher les aperçus du dossier</button>
          <button id="pathShowAll">Afficher tout le dossier</button>
        </div>
        <div class="modal-note">Un dossier sélectionné inclut ses sous-dossiers. « Afficher les aperçus » conserve le rendu local et les statuts affichables/probables. « Afficher tout » désactive ces deux restrictions pour explorer l’intégralité du chemin.</div>
      </div>
      <div class="modal-foot"><button id="pathClear" class="clear">Effacer le dossier actif</button><button id="pathCloseBottom">Fermer</button></div>
    </div>`;
  document.body.appendChild(d);
  byId('closePathExplorer').onclick=()=>d.close();
  byId('pathCloseBottom').onclick=()=>d.close();
  byId('pathFolderSearch').onclick=()=>searchFolders();
  byId('pathFolderQuery').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();searchFolders();}});
  byId('pathShowVisible').onclick=()=>applyPath(true);
  byId('pathShowAll').onclick=()=>applyPath(false);
  byId('pathClear').onclick=()=>clearActivePath(true);
  return d;
}

function ensureOpenButton(){
  const qa=document.querySelector('.quickactions');if(!qa||byId('openPathExplorer'))return;
  const b=document.createElement('button');b.id='openPathExplorer';b.textContent='📁 Arborescence';b.onclick=()=>openExplorer(activePath||'');
  qa.insertBefore(b,qa.firstChild);
  refreshButton();
}
function refreshButton(){
  const b=byId('openPathExplorer');if(!b)return;
  b.classList.toggle('path-active',!!activePath);
  b.textContent=activePath?'📁 '+(activePath.split('/').pop()||'Dossier'):'📁 Arborescence';
  b.title=activePath||'Explorer les dossiers et sous-dossiers';
}

function breadcrumbs(path){
  const box=byId('pathBreadcrumbs');if(!box)return;box.innerHTML='';
  const root=document.createElement('button');root.textContent='Racine';root.onclick=()=>loadPath('');box.appendChild(root);
  const parts=norm(path).split('/').filter(Boolean);let acc='';
  parts.forEach(p=>{const sep=document.createElement('span');sep.textContent='›';sep.className='hint';box.appendChild(sep);acc=acc?acc+'/'+p:p;const target=acc;const b=document.createElement('button');b.textContent=p;b.onclick=()=>loadPath(target);box.appendChild(b);});
}
function renderFolders(data,searchMode=false){
  const box=byId('pathFolders'),status=byId('pathFolderStatus');if(!box)return;box.innerHTML='';
  const folders=data?.folders||[];
  status.textContent=searchMode?`${folders.length} dossier(s) trouvé(s)`:`${folders.length} sous-dossier(s)`;
  if(!folders.length){box.innerHTML='<div class="path-empty">Aucun sous-dossier à ce niveau.</div>';return;}
  for(const f of folders){
    const b=document.createElement('button');b.className='path-folder';
    b.innerHTML=`<span><strong>📁 ${esc(f.name||f.full_path||'dossier')}</strong><small>${esc(f.full_path||'')}</small></span><span class="path-count">${Number(f.total_assets||0).toLocaleString('fr-FR')} assets</span>`;
    b.onclick=()=>loadPath(f.full_path||'');box.appendChild(b);
  }
}

async function loadPath(path){
  if(treeBusy)return;treeBusy=true;browsePath=norm(path);breadcrumbs(browsePath);byId('pathCurrent').textContent=browsePath||'Racine';byId('pathFolderStatus').textContent='Chargement…';
  try{
    const p=new URLSearchParams();if(browsePath)p.set('parent',browsePath);
    const r=await fetch(API37+'/path/children?'+p,{cache:'no-store'}),d=await r.json();if(!r.ok)throw new Error(d.message||d.error||'arborescence indisponible');renderFolders(d,false);
  }catch(e){byId('pathFolderStatus').textContent='Erreur : '+String(e?.message||e);byId('pathFolders').innerHTML='';}
  finally{treeBusy=false;}
}
async function searchFolders(){
  const q=String(byId('pathFolderQuery')?.value||'').trim();if(!q){loadPath(browsePath);return;}
  if(treeBusy)return;treeBusy=true;byId('pathFolderStatus').textContent='Recherche…';
  try{const r=await fetch(API37+'/path/children?q='+encodeURIComponent(q),{cache:'no-store'}),d=await r.json();if(!r.ok)throw new Error(d.message||d.error||'recherche dossier impossible');renderFolders(d,true);}catch(e){byId('pathFolderStatus').textContent='Erreur : '+String(e?.message||e);}finally{treeBusy=false;}
}
function openExplorer(path=''){
  ensureDialog();const d=byId('pathExplorerDialog');browsePath=norm(path||activePath);byId('pathFolderQuery').value='';d.showModal();loadPath(browsePath);
}

function applyPath(previewOnly){
  activePath=norm(browsePath);refreshButton();
  if(previewOnly){const ra=byId('render_availability');if(ra)ra.value='local-renderable';const ps=byId('preview_status');if(ps)ps.value='previewable';}
  else{const ra=byId('render_availability');if(ra)ra.value='all';const ps=byId('preview_status');if(ps)ps.value='all';}
  try{updateFilterSummary?.();}catch{}
  byId('pathExplorerDialog')?.close();
  if(typeof runSearch==='function')runSearch();
}
function clearActivePath(run=true){activePath='';browsePath='';refreshButton();try{updateFilterSummary?.();}catch{}if(byId('pathExplorerDialog')?.open)loadPath('');if(run&&typeof runSearch==='function')runSearch();}

function installQueryIntegration(){
  if(wrappersInstalled||typeof params!=='function')return false;wrappersInstalled=true;
  const baseParams=params;params=function(){const p=baseParams();if(activePath)p.set('path_prefix',activePath);return p;};
  if(typeof activeFilters==='function'){
    const baseActiveFilters=activeFilters;activeFilters=function(){const out=baseActiveFilters();if(activePath)out.unshift({id:'path_prefix',label:'Dossier '+activePath});return out;};
  }
  if(typeof resetFilters==='function'){
    const baseReset=resetFilters;resetFilters=function(run=true){activePath='';browsePath='';refreshButton();return baseReset(run);};
  }
  console.info('V37_PATH_EXPLORER query-integration=ON recursive-path-prefix=ON');return true;
}

function installMetaFolderButton(){
  if(typeof renderMeta!=='function'||renderMeta.__wfggPathV37)return false;
  const base=renderMeta;
  const wrapped=function(a,m=null){base(a,m);const tools=document.querySelector('#meta .tools');if(!tools||!a)return;let b=tools.querySelector('#openAssetFolderV37');if(!b){b=document.createElement('button');b.id='openAssetFolderV37';b.textContent='📂 Ouvrir son dossier';tools.appendChild(b);}const folder=norm(a.asset_folder||String(a.asset_path||'').replace(/\\/g,'/').split('/').slice(0,-1).join('/'));b.disabled=!folder;b.onclick=()=>openExplorer(folder);};
  wrapped.__wfggPathV37=true;renderMeta=wrapped;return true;
}

function boot(){
  injectStyle();ensureDialog();ensureOpenButton();
  const q=installQueryIntegration(),m=installMetaFolderButton();
  if(!q||!m)setTimeout(boot,150);
  else{installed=true;window.WFGGPathExplorerV37={version:'37.0',open:openExplorer,clear:clearActivePath,state:()=>({activePath,browsePath})};console.info('V37_PATH_EXPLORER ready tree=ON breadcrumbs=ON folder-search=ON');}
}
boot();
})();
