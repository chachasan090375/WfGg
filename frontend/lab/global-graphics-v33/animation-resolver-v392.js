(()=>{
'use strict';
/* V39.7: 2D icon -> related 3D prefab resolver + exact target opening + physical source recovery.
   If the correct prefab is INDEX ONLY, V39.7 refreshes authoritative APK/BundleFragment discovery
   and then checks only exact standalone .bundle filenames with exact byte size + Unity header.
   No approximate asset or bundle substitution is allowed.
*/

let activeSid='',token=0,resolution=null,modal=null;
const MAX_SCAN=5;
const EXACT_ID=/^LWGA-[A-Z0-9]+$/i;
let exactIdSearchInstalled=false;
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function cur(){try{return typeof currentAsset!=='undefined'?currentAsset:null}catch{return null}}
function is2DIcon(a){const p=String(a?.asset_path||a?.logical_name||a?.alias_name||'').toLowerCase();return String(a?.dimension_class||'').toUpperCase()==='2D'||/\/sprites?\/|\/icons?\/|ui[_/]|buildicon/.test(p);}
function badgeEl(){return document.querySelector('#wfggV39Badge button');}
function setBadge(text,state='loading',click=null){const b=badgeEl();if(!b)return false;b.dataset.state=state;b.innerHTML=esc(text);b.onclick=click||null;b.title='Résolution icône 2D → prefab 3D animé';return true;}
function ensureStyle(){if(document.getElementById('wfgg-v392-style'))return;const s=document.createElement('style');s.id='wfgg-v392-style';s.textContent=`
#wfggV392Modal{position:fixed;z-index:10060;inset:0;background:#000b;display:flex;align-items:center;justify-content:center;padding:16px;font-family:system-ui;color:#eee}
#wfggV392Modal .box{width:min(720px,96vw);max-height:88vh;overflow:auto;background:#181820;border:1px solid #3a3a48;border-radius:16px;padding:16px;box-shadow:0 24px 70px #000a}
#wfggV392Modal h3{margin:0 0 5px;font-size:16px}#wfggV392Modal .muted{font-size:12px;color:#aaa}#wfggV392Modal .cand{margin-top:12px;padding:11px;border:1px solid #383845;border-radius:11px;background:#21212a}#wfggV392Modal code{font-size:10px;color:#bddbff;word-break:break-all}#wfggV392Modal .row{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}#wfggV392Modal button{border:1px solid #545465;background:#292936;color:#eee;border-radius:9px;padding:8px 11px;font-weight:700}#wfggV392Modal .primary{border-color:#9b7de8;background:#2d2441}.v392pill{display:inline-block;border:1px solid #555466;border-radius:999px;padding:3px 7px;margin:5px 4px 0 0;font-size:10px}
`;document.head.appendChild(s);}

function exactRaw(){return String(document.getElementById('q')?.value||'').trim();}
function installExactIdSearch(){
  if(exactIdSearchInstalled||typeof params!=='function')return false;
  exactIdSearchInstalled=true;
  const baseParams=params;
  params=function(){
    const p=baseParams();
    const raw=exactRaw();
    if(!EXACT_ID.test(raw))return p;
    p.delete('q');p.delete('keywords');p.delete('hero_id');p.delete('hero_relation');
    p.set('stable_id',raw.toUpperCase());p.set('sort','default');
    console.debug('V39_7_EXACT_ID_SEARCH',raw.toUpperCase(),'via=stable-id-equality');
    return p;
  };
  if(typeof preparePageItems==='function'){
    const basePrepare=preparePageItems;
    preparePageItems=function(rawItems){
      const raw=exactRaw();
      if(EXACT_ID.test(raw)){
        const sid=raw.toUpperCase();
        return (rawItems||[]).filter(a=>String(a?.stable_id||'').toUpperCase()===sid);
      }
      return basePrepare(rawItems);
    };
  }
  if(typeof activeFilters==='function'){
    const baseFilters=activeFilters;
    activeFilters=function(){
      const out=baseFilters();const raw=exactRaw();
      if(EXACT_ID.test(raw))out.unshift({id:'exact_lwga_id',label:'ID WfGg exact'});
      return out;
    };
  }
  console.info('V39_7_EXACT_ID_SEARCH installed stable-id-equality=ON preview-bypass=ON direct-open=ON source-recovery=ON');
  return true;
}

function closeModal(){modal?.remove();modal=null;}
async function fetchExact(sid){
  const r=await fetch('/api/v33/search?stable_id='+encodeURIComponent(sid)+'&limit=1&offset=0',{cache:'no-store'});
  const d=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(d.message||d.error||('HTTP '+r.status));
  const exact=(d.items||[]).find(a=>String(a?.stable_id||'').toUpperCase()===sid);
  if(!exact)throw new Error('Prefab '+sid+' absent de la table assets');
  return exact;
}
async function recoverExactSource(sid,exact){
  if(String(exact?.render_availability||'')!=='global-index-only')return {exact,recovery:null};
  const stage=document.getElementById('stage');
  if(stage)stage.innerHTML='<div class="empty"><b>Prefab exact trouvé.</b><br><span class="hint">Recherche de sa source physique locale…</span></div>';
  setBadge('Prefab trouvé · recherche du bundle physique…','loading');
  try{
    const r=await fetch('/api/v39/recover-source?id='+encodeURIComponent(sid),{cache:'no-store'});
    const recovery=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(recovery.message||recovery.error||('HTTP '+r.status));
    console.info('V39_7_PREFAB_SOURCE_PROBE',sid,recovery);
    if(recovery.recovered){
      setBadge('Bundle exact récupéré · ouverture 3D…','animated-clip');
      return {exact:await fetchExact(sid),recovery};
    }
    setBadge('Prefab exact trouvé · bundle physique absent','static-or-undetected');
    return {exact,recovery};
  }catch(e){
    console.warn('V39_7_PREFAB_SOURCE_PROBE_FAIL',sid,e);
    setBadge('Prefab exact trouvé · recherche bundle échouée','error');
    return {exact,recovery:{error:String(e?.message||e)}};
  }
}

async function openCandidateDirect(c){
  const sid=String(c?.stable_id||'').trim().toUpperCase();
  if(!EXACT_ID.test(sid)){console.warn('V39_7_DIRECT_OPEN_INVALID_ID',sid);return;}
  closeModal();
  const q=document.getElementById('q');if(q)q.value=sid;
  try{updateFilterSummary();}catch{}
  const stage=document.getElementById('stage');
  if(stage)stage.innerHTML='<div class="empty">Ouverture directe du prefab 3D…</div>';
  setBadge('Ouverture directe du prefab 3D…','loading');
  try{
    let exact=await fetchExact(sid);
    const probe=await recoverExactSource(sid,exact);exact=probe.exact;

    try{currentModel?.destroy?.();}catch{}
    currentModel=null;
    if(currentUrl){try{URL.revokeObjectURL(currentUrl)}catch{}currentUrl=null;}
    currentAsset=null;currentRenderMeta=null;idx=-1;
    items=[exact];
    renderList();
    const rc=document.getElementById('resultCount');if(rc)rc.textContent='1';
    await select(0);
    try{window.WFGGResultStripSync?.('auto');}catch{}
    console.info('V39_7_DIRECT_PREFAB_OPEN',sid,'availability='+String(exact.render_availability||''),'dimension='+String(exact.dimension_class||''),'role='+String(exact.model_role||''),'recovered='+String(!!probe.recovery?.recovered));
  }catch(e){
    console.warn('V39_7_DIRECT_PREFAB_OPEN_FAIL',sid,e);
    const results=document.getElementById('results');if(results)results.innerHTML='<div class="empty error">Prefab lié introuvable : '+esc(sid)+'</div>';
    if(stage)stage.innerHTML='<div class="empty"><b>Le candidat lié existe dans le resolver mais son ouverture exacte a échoué.</b><br><span class="hint">'+esc(String(e?.message||e))+'</span></div>';
  }
}

function openModal(){
  if(!resolution)return;ensureStyle();closeModal();const r=resolution,c=r.candidate||{},d=r.diagnostic||{};
  modal=document.createElement('div');modal.id='wfggV392Modal';
  modal.innerHTML=`<div class="box"><h3>Prefab 3D lié à l’icône</h3><div class="muted">L’asset affiché est une image UI 2D. V39.7 a recherché les assets 3D partageant les identifiants de catalogue. Si le prefab exact est seulement indexé, l’ouverture tente aussi de retrouver son bundle physique sans aucune substitution approximative.</div><div class="cand"><b>${esc(c.stable_id||'—')}</b><br><code>${esc(c.asset_path||c.logical_name||c.alias_name||'')}</code><div><span class="v392pill">score liaison ${esc(c.resolver_score??'—')}</span><span class="v392pill">${esc(d?.classification?.status||r.status||'à confirmer')}</span></div><div class="muted" style="margin-top:7px">${esc((c.resolver_reasons||[]).join(' · '))}</div></div><div class="row"><button class="primary" id="v392open">Ouvrir / rechercher le bundle exact</button><button id="v392close">Fermer</button></div></div>`;
  document.body.appendChild(modal);
  document.getElementById('v392close').onclick=closeModal;
  document.getElementById('v392open').onclick=()=>openCandidateDirect(c);
  modal.onclick=e=>{if(e.target===modal)closeModal();};
}

async function scanCandidate(c,myToken){try{const r=await fetch('/api/v39/animation?id='+encodeURIComponent(c.stable_id),{cache:'no-store'});const d=await r.json().catch(()=>({}));if(myToken!==token)return null;if(!r.ok)return {candidate:c,error:d.message||d.error||('HTTP '+r.status)};return {candidate:c,diagnostic:d};}catch(e){return {candidate:c,error:String(e)}}}
async function resolve(a){const sid=String(a?.stable_id||'');if(!sid||sid===activeSid)return;activeSid=sid;resolution=null;const myToken=++token;setTimeout(()=>{if(myToken===token)setBadge('Icône 2D · recherche du prefab 3D…','loading');},40);let targets;try{const r=await fetch('/api/v39/animation-targets?id='+encodeURIComponent(sid),{cache:'no-store'});targets=await r.json();if(!r.ok)throw new Error(targets.message||targets.error||'targets');}catch(e){if(myToken===token)setBadge('Icône 2D · liaison prefab indisponible','error');return;}if(myToken!==token)return;const candidates=(targets.candidates||[]).slice(0,MAX_SCAN);if(!candidates.length){setBadge('Icône 2D · aucun prefab 3D relié','static-or-undetected');return;}let best=null;for(let i=0;i<candidates.length;i++){setBadge(`Prefab 3D ${i+1}/${candidates.length} · vérification animation…`,'loading');const x=await scanCandidate(candidates[i],myToken);if(myToken!==token)return;if(!x)continue;if(!best&&!x.error)best=x;const code=x.diagnostic?.classification?.code||'';if(code&&code!=='static-or-undetected'){best=x;break;}}if(myToken!==token)return;if(!best){resolution={candidate:candidates[0],status:'prefab trouvé · source à vérifier'};setBadge('Prefab 3D lié trouvé · ouvrir','animated-clip',openModal);return;}resolution=best;const st=best.diagnostic?.classification?.status||'Prefab 3D lié';const animated=(best.diagnostic?.classification?.code||'')!=='static-or-undetected';setBadge((animated?'🔗 ':'')+st+' · prefab lié',animated?(best.diagnostic?.classification?.code||'animated-clip'):'static-or-undetected',openModal);console.info('V39_7_ICON_PREFAB_RESOLVED',sid,'->',best.candidate?.stable_id,st);}
function tick(){const a=cur(),sid=String(a?.stable_id||'');if(!sid){activeSid='';return;}if(!is2DIcon(a)){if(activeSid&&sid!==activeSid){activeSid='';resolution=null;}return;}if(sid!==activeSid)resolve(a);}
function boot(){ensureStyle();if(!installExactIdSearch())setTimeout(boot,120);setInterval(tick,350);setTimeout(tick,120);}
boot();window.WFGGAnimationResolverV392={version:'39.7',state:()=>resolution,refresh:()=>{activeSid='';tick();},open:openModal,openDirect:openCandidateDirect};
})();
