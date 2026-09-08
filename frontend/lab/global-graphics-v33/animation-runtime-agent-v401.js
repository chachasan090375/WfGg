(()=>{
'use strict';
/* WfGg V40.1 — agent-driven runtime prefab preview.
   Replaces the V39.15 blind child loop while V40 is active.
   Policy: exact + local runtime relations only; WORK then IDLE automatically.
   Other variants remain manual fallback. Every model request has a hard timeout.
*/
const VERSION='40.1';
const EXACT=/^LWGA-[A-Z0-9]+$/i;
const AUTO_VARIANTS=['work','idle'];
const TIMEOUT_MS=10000;
let installed=false,seq=0,activeRoot='',state=null;

const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const stage=()=>document.getElementById('stage');
function current(){try{return typeof currentAsset!=='undefined'?currentAsset:null}catch{return null}}
function navMarkup(){try{return typeof nav==='function'?nav():''}catch{return ''}}
function bindNativeNav(){try{if(typeof bindNav==='function')bindNav()}catch{}}
function destroyModel(){try{if(typeof currentModel!=='undefined'){currentModel?.destroy?.();currentModel=null}}catch{}}
function local(v){return String(v||'').startsWith('local-')}
function exactChild(x){const b=x?.best||{};return EXACT.test(String(b.stable_id||''))&&local(b.render_availability)&&!!(b.exactName||b.exactPath)}
function needs(a){
  if(!a||!EXACT.test(String(a.stable_id||'')))return false;
  const p=String(a.asset_path||'').toLowerCase();
  if(!(p.endsWith('.prefab')||String(a.dimension_class||'').toLowerCase().includes('3d')))return false;
  const s=stage();if(!s)return false;const t=(s.textContent||'').toLowerCase();
  return t.includes('sans mesh autonome')||t.includes('assemblage 3d indisponible')||t.includes('sous-prefab exact');
}
function style(){if(document.getElementById('wfgg-v401-runtime-style'))return;const x=document.createElement('style');x.id='wfgg-v401-runtime-style';x.textContent=`
#wfggV401Probe{width:100%;max-width:700px;text-align:center;color:#adb7c8;padding:26px 18px;line-height:1.45}#wfggV401Probe b{color:#f4f7fb}.v401code{font:10px ui-monospace,monospace;color:#bddbff;word-break:break-all}.v401warn{color:#ffd38a}
#wfggV401Bar{position:absolute;z-index:88;left:9px;right:9px;bottom:58px;display:flex;gap:6px;align-items:center;padding:6px;background:#0b1018e8;border:1px solid #354158;border-radius:10px;font:700 10px/1.15 system-ui}#wfggV401Bar .label{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#d2d9e6}#wfggV401Bar .states{display:flex;gap:4px}#wfggV401Bar button{padding:5px 7px;border:1px solid #4a5873;border-radius:7px;background:#111722;color:#edf1f8;font:700 10px/1 system-ui}#wfggV401Bar button.active{border-color:#9f83e9;background:#29203d}
`;document.head.appendChild(x)}

async function fetchJSON(url,timeout=TIMEOUT_MS){
  const ctl=new AbortController();const tm=setTimeout(()=>ctl.abort('timeout'),timeout);
  try{const r=await fetch(url,{cache:'no-store',signal:ctl.signal});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.message||d.error||('HTTP '+r.status));return d}
  finally{clearTimeout(tm)}
}
async function graph(sid){return fetchJSON('/api/v40/animation-graph?id='+encodeURIComponent(sid),30000)}
async function model(sid){const d=await fetchJSON('/api/v33/model?id='+encodeURIComponent(sid),TIMEOUT_MS);if(!d?.model)throw new Error('model-payload-missing');return d.model}
async function animStatus(sid){try{const d=await fetchJSON('/api/v39/animation?id='+encodeURIComponent(sid),8000);return String(d?.classification?.status||'')}catch{return ''}}

function candidatesFrom(d){
  const out=[],seen=new Set();
  for(const x of d?.runtimePrefabs?.items||[]){if(!exactChild(x))continue;const b=x.best,v=String(x.variant||'runtime').toLowerCase(),sid=String(b.stable_id||'').toUpperCase();const k=v+'|'+sid;if(seen.has(k))continue;seen.add(k);out.push({variant:v,slot:x.nodePath||'',best:b})}
  const pri=v=>AUTO_VARIANTS.indexOf(v)>=0?AUTO_VARIANTS.indexOf(v):20;
  out.sort((a,b)=>pri(a.variant)-pri(b.variant)||String(a.slot).localeCompare(String(b.slot)));
  return out
}
function openExact(c){try{window.WFGGAnimationResolverV392?.openDirect?.(c.best)}catch{}}
function bar(root,cands,c,status){const s=stage();if(!s)return;document.getElementById('wfggV401Bar')?.remove();const b=document.createElement('div');b.id='wfggV401Bar';const l=document.createElement('div');l.className='label';l.textContent=`V40.1 · ${c.variant.toUpperCase()} · ${c.best.stable_id}${status?' · '+status:''}`;const st=document.createElement('div');st.className='states';for(const x of cands.slice(0,6)){const q=document.createElement('button');q.type='button';q.textContent=x.variant.toUpperCase();if(x.best.stable_id===c.best.stable_id&&x.variant===c.variant)q.classList.add('active');q.onclick=()=>show(root,cands,x);st.appendChild(q)}const op=document.createElement('button');op.type='button';op.textContent='Ouvrir';op.onclick=()=>openExact(c);b.append(l,st,op);s.appendChild(b)}

async function show(root,cands,c){
  const my=++seq,s=stage();if(!s)return false;s.innerHTML=`<div id="wfggV401Probe"><b>V40.1 · chargement ${esc(c.variant.toUpperCase())} exact…</b><br><span class="v401code">${esc(c.best.stable_id)}</span><br><span class="v401warn">délai maximum ${TIMEOUT_MS/1000}s</span></div>`+navMarkup();bindNativeNav();
  try{const m=await model(c.best.stable_id);if(my!==seq||String(current()?.stable_id||'').toUpperCase()!==root)return false;destroyModel();s.innerHTML='';currentModel=await WFGGModelViewer.mount(s,m);if(my!==seq)return false;s.insertAdjacentHTML('beforeend',navMarkup());bindNativeNav();const status=await animStatus(c.best.stable_id);state={root,cands,current:c,status};bar(root,cands,c,status);console.info('V40_1_RUNTIME_RENDER',root,'->',c.best.stable_id,c.variant);return true}
  catch(e){console.warn('V40_1_RUNTIME_FAIL',root,c.best.stable_id,c.variant,String(e?.message||e));return false}
}

async function resolve(a){
  const root=String(a?.stable_id||'').toUpperCase();if(!EXACT.test(root))return;activeRoot=root;const my=++seq,s=stage();if(!s)return;const original=s.innerHTML;s.innerHTML='<div id="wfggV401Probe"><b>Agent V40.1 · résolution du chemin runtime…</b><br>WORK puis IDLE, relations exactes uniquement.</div>'+navMarkup();bindNativeNav();
  let d,c=[];try{d=await graph(root);c=candidatesFrom(d)}catch(e){if(my===seq)s.innerHTML=original;return}
  if(my!==seq||String(current()?.stable_id||'').toUpperCase()!==root)return;
  const auto=c.filter(x=>AUTO_VARIANTS.includes(x.variant));
  for(const x of auto){if(await show(root,c,x))return}
  if(my!==seq)return;
  const manual=c.filter(x=>!AUTO_VARIANTS.includes(x.variant));
  s.innerHTML='<div id="wfggV401Probe"><b>WORK / IDLE exacts retrouvés mais non rendus comme Mesh autonome.</b><br><span class="v401warn">V40.1 n’essaie plus automatiquement des composants runtime sans rapport direct.</span>'+manual.slice(0,8).map(x=>`<div><button data-sid="${esc(x.best.stable_id)}" data-var="${esc(x.variant)}">Tester ${esc(x.variant.toUpperCase())}</button><br><span class="v401code">${esc(x.best.asset_path||x.best.stable_id)}</span></div>`).join('')+'</div>'+navMarkup();bindNativeNav();
  for(const btn of s.querySelectorAll('#wfggV401Probe button[data-sid]')){btn.onclick=()=>{const x=manual.find(z=>z.best.stable_id===btn.dataset.sid&&z.variant===btn.dataset.var);if(x)show(root,c,x)}}
}
function maybe(){const a=current();if(!a?.stable_id)return;if(needs(a)){const sid=String(a.stable_id).toUpperCase();if(activeRoot!==sid||!state)setTimeout(()=>resolve(a),0)}}
function boot(){style();if(window.WFGGRuntimePrefabPreviewV3915){console.info('V40_1 legacy V39.15 preview present but V40.1 server should omit it')}new MutationObserver(()=>{try{maybe()}catch{}}).observe(document.getElementById('stage')||document.body,{childList:true,subtree:true});setInterval(maybe,650);setTimeout(maybe,150);window.WFGGRuntimeAgentV401={version:VERSION,refresh:()=>{activeRoot='';state=null;maybe()},get state(){return state}};console.info('V40_1_RUNTIME_AGENT installed WORK-IDLE-only-auto=ON timeout=10s legacy-blind-loop=OFF')}
boot();
})();
