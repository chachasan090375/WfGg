(()=>{
'use strict';
/* V39.3: 2D icon -> related 3D prefab resolver + exact LWGA-ID search guard.
   The selected catalogue entry can be a UI/build icon, while the runtime animation lives on a
   different prefab. This layer uses catalogue identity tokens to discover candidates, then asks
   the exact V39 scanner to validate animation evidence. It never claims an animation from naming
   alone and never modifies audit/index state.

   Exact LWGA IDs are special-cased before the V31 FTS parser: an ID such as
   LWGA-C37A0F67197299 is passed through the existing `keywords` LIKE path instead of FTS5. This
   preserves all normal filters/search state while avoiding hyphen/tokenization failures.
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

function installExactIdSearch(){
  if(exactIdSearchInstalled||typeof params!=='function')return false;
  exactIdSearchInstalled=true;
  const baseParams=params;
  params=function(){
    const p=baseParams();
    const raw=String(document.getElementById('q')?.value||'').trim();
    if(!EXACT_ID.test(raw))return p;
    p.delete('q');
    p.delete('keywords');
    p.set('keywords',raw.toUpperCase());
    p.set('sort','default');
    console.debug('V39_3_EXACT_ID_SEARCH',raw.toUpperCase(),'via=keywords-like');
    return p;
  };
  if(typeof activeFilters==='function'){
    const baseFilters=activeFilters;
    activeFilters=function(){
      const out=baseFilters();
      const raw=String(document.getElementById('q')?.value||'').trim();
      if(EXACT_ID.test(raw))out.unshift({id:'exact_lwga_id',label:'ID WfGg exact'});
      return out;
    };
  }
  console.info('V39_3_EXACT_ID_SEARCH installed fts-hyphen-guard=ON');
  return true;
}

function closeModal(){modal?.remove();modal=null;}
function openModal(){if(!resolution)return;ensureStyle();closeModal();const r=resolution,c=r.candidate||{},d=r.diagnostic||{};modal=document.createElement('div');modal.id='wfggV392Modal';modal.innerHTML=`<div class="box"><h3>Prefab 3D lié à l’icône</h3><div class="muted">L’asset affiché est une image UI 2D. V39.2 a recherché les assets 3D partageant les identifiants de catalogue, puis a vérifié les candidats avec le scanner Unity.</div><div class="cand"><b>${esc(c.stable_id||'—')}</b><br><code>${esc(c.asset_path||c.logical_name||c.alias_name||'')}</code><div><span class="v392pill">score liaison ${esc(c.resolver_score??'—')}</span><span class="v392pill">${esc(d?.classification?.status||r.status||'à confirmer')}</span></div><div class="muted" style="margin-top:7px">${esc((c.resolver_reasons||[]).join(' · '))}</div></div><div class="row"><button class="primary" id="v392open">Ouvrir le prefab 3D</button><button id="v392close">Fermer</button></div></div>`;document.body.appendChild(modal);document.getElementById('v392close').onclick=closeModal;document.getElementById('v392open').onclick=()=>{closeModal();const q=document.getElementById('q');if(q){q.value=c.stable_id||'';if(typeof runSearch==='function')runSearch();}};modal.onclick=e=>{if(e.target===modal)closeModal();};}
async function scanCandidate(c,myToken){try{const r=await fetch('/api/v39/animation?id='+encodeURIComponent(c.stable_id),{cache:'no-store'});const d=await r.json().catch(()=>({}));if(myToken!==token)return null;if(!r.ok)return {candidate:c,error:d.message||d.error||('HTTP '+r.status)};return {candidate:c,diagnostic:d};}catch(e){return {candidate:c,error:String(e)}}}
async function resolve(a){const sid=String(a?.stable_id||'');if(!sid||sid===activeSid)return;activeSid=sid;resolution=null;const myToken=++token;setTimeout(()=>{if(myToken===token)setBadge('Icône 2D · recherche du prefab 3D…','loading');},40);let targets;try{const r=await fetch('/api/v39/animation-targets?id='+encodeURIComponent(sid),{cache:'no-store'});targets=await r.json();if(!r.ok)throw new Error(targets.message||targets.error||'targets');}catch(e){if(myToken===token)setBadge('Icône 2D · liaison prefab indisponible','error');return;}if(myToken!==token)return;const candidates=(targets.candidates||[]).slice(0,MAX_SCAN);if(!candidates.length){setBadge('Icône 2D · aucun prefab 3D relié','static-or-undetected');return;}let best=null;for(let i=0;i<candidates.length;i++){setBadge(`Prefab 3D ${i+1}/${candidates.length} · vérification animation…`,'loading');const x=await scanCandidate(candidates[i],myToken);if(myToken!==token)return;if(!x)continue;if(!best&&!x.error)best=x;const code=x.diagnostic?.classification?.code||'';if(code&&code!=='static-or-undetected'){best=x;break;}}if(myToken!==token)return;if(!best){resolution={candidate:candidates[0],status:'prefab trouvé · diagnostic à ouvrir'};setBadge('Prefab 3D lié trouvé · ouvrir','animated-clip',openModal);return;}resolution=best;const st=best.diagnostic?.classification?.status||'Prefab 3D lié';const animated=(best.diagnostic?.classification?.code||'')!=='static-or-undetected';setBadge((animated?'🔗 ':'')+st+' · prefab lié',animated?(best.diagnostic?.classification?.code||'animated-clip'):'static-or-undetected',openModal);console.info('V39_2_ICON_PREFAB_RESOLVED',sid,'->',best.candidate?.stable_id,st);}
function tick(){const a=cur(),sid=String(a?.stable_id||'');if(!sid){activeSid='';return;}if(!is2DIcon(a)){if(activeSid&&sid!==activeSid){activeSid='';resolution=null;}return;}if(sid!==activeSid)resolve(a);}
function boot(){ensureStyle();if(!installExactIdSearch())setTimeout(boot,120);setInterval(tick,350);setTimeout(tick,120);}
boot();window.WFGGAnimationResolverV392={version:'39.3',state:()=>resolution,refresh:()=>{activeSid='';tick();},open:openModal};
})();