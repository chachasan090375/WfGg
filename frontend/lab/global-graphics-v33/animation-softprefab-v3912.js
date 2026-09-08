(()=>{
'use strict';
/* WfGg V39.12.1 — linked badge layout + exact SoftReferencePrefab trace UI.
   The add-on never fabricates a child prefab. It displays only backend candidates resolved from
   serialized/name/path evidence and lets the existing exact-ID opener handle a chosen child.
*/

const VERSION='39.12.1';
let lastModalSid='';
let modalRequest=0;

function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function byId(id){return document.getElementById(id);}

function injectStyle(){
  if(byId('wfgg-v3912-style'))return;
  const s=document.createElement('style');s.id='wfgg-v3912-style';s.textContent=`
/* Animation badge: same top row as the native render badge, never over the artwork below. */
#stage #wfggV39Badge.wfgg-v392-linked{position:absolute!important;z-index:40!important;display:block!important;margin:0!important;padding:0!important;pointer-events:auto!important;overflow:hidden!important;transform:none!important;}
#stage #wfggV39Badge.wfgg-v392-linked button{display:block!important;width:100%!important;min-width:0!important;max-width:100%!important;height:auto!important;min-height:0!important;margin:0!important;padding:5px 8px!important;border-radius:8px!important;font:700 11px/1.2 system-ui,sans-serif!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;box-shadow:none!important;backdrop-filter:none!important;}
#wfggV3912Soft .v3912intro{font-size:11px;color:#aaa;margin:7px 0 9px;line-height:1.35}
#wfggV3912Soft .v3912item{border:1px solid #343440;background:#1d1d26;border-radius:10px;padding:9px;margin:7px 0;font-size:11px;overflow:hidden}
#wfggV3912Soft .v3912row{display:flex;align-items:flex-start;gap:7px;flex-wrap:wrap;margin-top:6px}
#wfggV3912Soft .v3912pill{display:inline-block;border:1px solid #4a4a58;border-radius:999px;padding:3px 7px;background:#262631;font-size:10px}
#wfggV3912Soft code{font-size:10px;color:#bddbff;word-break:break-all}
#wfggV3912Soft button{border:1px solid #7865aa;background:#2a2340;color:#fff;border-radius:8px;padding:6px 8px;font-weight:700;font-size:11px;cursor:pointer}
#wfggV3912Soft .ok{color:#9be8c0}.wfggV3912Soft .warn{color:#ffd38a}
`;
  document.head.appendChild(s);
}

function stage(){return byId('stage');}
function normalRenderBadge(st){
  if(!st)return null;
  for(const el of Array.from(st.children||[])){
    if(el?.id==='wfggV39Badge')continue;
    if(el?.classList?.contains('badge'))return el;
  }
  return st.querySelector('.badge:not(#wfggV39Badge)');
}

function important(el,name,value){try{el.style.setProperty(name,String(value),'important');}catch{}}
function placeAnimationBadge(){
  const st=stage(), box=byId('wfggV39Badge');
  if(!st||!box)return false;
  const rb=normalRenderBadge(st);
  const gap=7, edge=9;
  let left=edge, top=edge, available=Math.max(72,st.clientWidth-edge*2);
  if(rb){
    const rLeft=Number(rb.offsetLeft)||edge;
    const rTop=Number(rb.offsetTop)||edge;
    const rWidth=Number(rb.offsetWidth)||0;
    left=Math.max(edge,Math.round(rLeft+rWidth+gap));
    top=Math.max(edge,Math.round(rTop));
    available=Math.max(54,Math.floor(st.clientWidth-left-edge));
  }
  /* The V39.11 resolver has fallback top/left rules marked !important. Inline !important is
     deliberate here so the runtime placement always wins on narrow mobile viewports. */
  important(box,'left',left+'px');
  important(box,'top',top+'px');
  important(box,'right','auto');
  important(box,'bottom','auto');
  important(box,'width',available+'px');
  important(box,'max-width',available+'px');
  important(box,'height','auto');
  important(box,'margin','0');
  important(box,'transform','none');
  const b=box.querySelector('button');
  if(b){
    important(b,'width','100%');important(b,'max-width','100%');important(b,'min-width','0');
    b.title=b.textContent.trim()+' — toucher pour le diagnostic / prefab lié';
  }
  box.dataset.wfggPlacement='same-row';
  return true;
}

function watchBadge(){
  injectStyle();
  const st=stage();
  if(st&&!st.dataset.wfggV3912Observed){
    st.dataset.wfggV3912Observed='1';
    new MutationObserver(()=>requestAnimationFrame(placeAnimationBadge)).observe(st,{childList:true,subtree:true});
  }
  placeAnimationBadge();
}

function variantLabel(v){
  if(v==='idle')return 'IDLE';if(v==='work')return 'WORK';if(v==='upgrade')return 'UPGRADE';if(v==='level-tip')return 'LEVEL TIP';return 'RUNTIME';
}
function availabilityLabel(v){
  const s=String(v||'');return s.startsWith('local-')?'LOCAL EXACT':(s==='global-index-only'?'INDEX SEULEMENT':(s||'—'));
}
function strongestTokens(ref){
  return (ref.tokens||[]).slice(0,4).map(t=>t.value).filter(Boolean);
}

function openExactCandidate(c){
  if(!c?.stable_id)return;
  try{
    if(window.WFGGAnimationResolverV392?.openDirect){window.WFGGAnimationResolverV392.openDirect(c);return;}
  }catch{}
  const q=byId('q');if(q)q.value=c.stable_id;
  const search=byId('search');if(search){search.click();return;}
}

function softHtml(d){
  const items=d?.items||[];
  if(!items.length)return `<div class="v3912intro">Aucun <b>SoftReferencePrefab</b> sur ce prefab.</div>`;
  const rows=items.map((r,i)=>{
    const best=r.best||null;
    const toks=strongestTokens(r);
    const bestBlock=best?`<div class="v3912row"><span class="v3912pill">score ${esc(best.score)}</span><span class="v3912pill">${esc(availabilityLabel(best.render_availability))}</span>${best.exactName||best.exactPath?'<span class="v3912pill ok">preuve exacte</span>':''}</div><div style="margin-top:6px"><b>${esc(best.stable_id||'—')}</b><br><code>${esc(best.asset_path||'')}</code></div><div class="v3912row"><button type="button" data-v3912-open="${i}">Ouvrir ce sous-prefab</button></div>`:`<div class="v3912row"><span class="v3912pill">non résolu exactement</span></div>`;
    return `<div class="v3912item"><div><b>${esc(variantLabel(r.variant))}</b> · ${esc(r.nodePath||r.gameObject||'(root)')}</div>${toks.length?`<div style="margin-top:5px"><span style="color:#aaa">Références :</span> ${toks.map(esc).join(' · ')}</div>`:''}${bestBlock}</div>`;
  }).join('');
  const ready=d.assemblyReady?`<div class="v3912intro ok"><b>Plan d’assemblage exact prêt :</b> tous les slots résolus sont locaux et correspondent à une preuve de nom/chemin exacte.</div>`:`<div class="v3912intro"><b>Assemblage fusionné encore verrouillé :</b> V39.12 suit et matérialise les sous-prefabs exacts, mais ne fusionne pas encore parent + enfants tant que chaque slot choisi n’est pas prouvé et local. Aucun faux rendu n’est généré.</div>`;
  return `<div class="v3912intro">${esc(d.resolvedCount||0)}/${esc(d.softReferenceCount||0)} références résolues · ${esc(d.localResolvedCount||0)} locales. Les variantes IDLE/WORK sont conservées séparément.</div>${ready}${rows}`;
}

async function hydrateModal(){
  const modal=byId('wfggV39Modal');if(!modal)return;
  const d=window.WFGGAnimationV39?.last;
  const sid=String(d?.stableId||'');if(!/^LWGA-[A-Z0-9]+$/i.test(sid))return;
  let host=byId('wfggV3912Soft');
  if(host&&host.dataset.sid===sid)return;
  if(!host){
    host=document.createElement('details');host.id='wfggV3912Soft';host.open=true;
    const summary=document.createElement('summary');summary.textContent='Sous-prefabs runtime — résolution exacte';host.appendChild(summary);
    const body=document.createElement('div');body.className='v3912body';body.innerHTML='<div class="v3912intro">Recherche des SoftReferencePrefab et matérialisation des correspondances exactes…</div>';host.appendChild(body);
    const provenance=Array.from(modal.querySelectorAll('details')).find(x=>/Provenance/i.test(x.querySelector('summary')?.textContent||''));
    if(provenance)provenance.before(host);else modal.querySelector('.v39body')?.appendChild(host);
  }
  host.dataset.sid=sid;const body=host.querySelector('.v3912body');
  const token=++modalRequest;lastModalSid=sid;
  try{
    const r=await fetch('/api/v39/soft-prefabs?id='+encodeURIComponent(sid)+'&materialize=1',{cache:'no-store'});
    const payload=await r.json().catch(()=>({}));
    if(token!==modalRequest||lastModalSid!==sid)return;
    if(!r.ok)throw new Error(payload.message||payload.error||('HTTP '+r.status));
    body.innerHTML=softHtml(payload);
    const items=payload.items||[];
    body.querySelectorAll('[data-v3912-open]').forEach(btn=>{
      btn.onclick=()=>{const ref=items[Number(btn.dataset.v3912Open)];if(ref?.best)openExactCandidate(ref.best);};
    });
    window.WFGGSoftPrefabV3912.last=payload;
    console.info('V39_12_1_SOFTPREFAB_UI',sid,'resolved='+payload.resolvedCount,'local='+payload.localResolvedCount,'ready='+payload.assemblyReady);
  }catch(e){
    if(body)body.innerHTML='<div class="v3912intro">Résolution des sous-prefabs indisponible : '+esc(String(e?.message||e))+'</div>';
    console.warn('V39_12_1_SOFTPREFAB_UI_FAIL',sid,e);
  }
}

function install(){
  injectStyle();watchBadge();
  window.addEventListener('resize',()=>requestAnimationFrame(placeAnimationBadge),{passive:true});
  new MutationObserver(()=>{
    watchBadge();
    if(byId('wfggV39Modal'))setTimeout(hydrateModal,0);
  }).observe(document.body,{childList:true,subtree:true});
  setInterval(()=>{watchBadge();if(byId('wfggV39Modal'))hydrateModal();},350);
  window.WFGGSoftPrefabV3912={version:VERSION,ready:true,last:null,refresh:hydrateModal,positionBadge:placeAnimationBadge};
  console.info('V39_12_1_SOFTPREFAB_UI installed badge=same-render-row FORCED viewport-clamp=ON exact-softrefs=ON');
}

install();
})();