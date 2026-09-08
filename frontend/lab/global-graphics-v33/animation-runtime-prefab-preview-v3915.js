(()=>{
'use strict';
/* WfGg V39.15 — exact runtime child-prefab preview.
   When a controller prefab has no autonomous Mesh, resolve only proven/local SoftReferencePrefab
   children and try their real V33 model payloads. No visual similarity, no synthetic geometry,
   no guessed parent/child fusion. WORK is preferred, then IDLE, while every resolved state remains
   selectable. Opening a child switches to its exact LWGA asset so the normal animation diagnostic
   can inspect it independently.
*/
const VERSION='39.15';
const EXACT=/^LWGA-[A-Z0-9]+$/i;
let installed=false, seq=0, activeRoot='', runtimeState=null;
const PRIORITY={work:0,idle:1,runtime:2,upgrade:3,'level-tip':4};

function st(){return document.getElementById('stage');}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function local(v){return String(v||'').startsWith('local-');}
function eligible(r){const b=r?.best;return !!(b&&EXACT.test(String(b.stable_id||''))&&local(b.render_availability)&&(b.exactName||b.exactPath));}
function needsRuntimePreview(a){
  if(!a||!EXACT.test(String(a.stable_id||'')))return false;
  const p=String(a.asset_path||'').toLowerCase();
  const role=String(a.model_role||'').toLowerCase();
  if(!(p.endsWith('.prefab')||role==='prefab'||String(a.dimension_class||'').toLowerCase().includes('3d')))return false;
  const s=st();if(!s)return false;
  const txt=(s.textContent||'').toLowerCase();
  return txt.includes('sans mesh autonome')||txt.includes('assemblage 3d indisponible');
}

function injectStyle(){
  if(document.getElementById('wfgg-v3915-style'))return;
  const x=document.createElement('style');x.id='wfgg-v3915-style';x.textContent=`
#wfggV3915RuntimeBar{position:absolute;z-index:86;left:9px;right:9px;bottom:58px;display:flex;align-items:center;gap:6px;min-width:0;padding:6px;background:rgba(10,13,20,.90);border:1px solid #30394b;border-radius:10px;backdrop-filter:blur(5px);font:700 10px/1.15 system-ui,sans-serif}
#wfggV3915RuntimeBar .v3915label{flex:1 1 auto;min-width:0;color:#cbd4e3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#wfggV3915RuntimeBar .v3915states{display:flex;gap:4px;flex:0 0 auto}
#wfggV3915RuntimeBar button{min-width:0;padding:5px 7px;border-radius:7px;font:700 10px/1 system-ui,sans-serif;background:#111722;border:1px solid #46546d;color:#edf1f8}
#wfggV3915RuntimeBar button.active{border-color:#a78bfa;color:#efe9ff;background:#241d37}
#wfggV3915RuntimeBar .open{border-color:#6d8ab8}
#wfggV3915Probe{width:100%;max-width:680px;text-align:center;color:#aeb7c6;padding:24px 18px;line-height:1.4}
#wfggV3915Probe b{color:#f5f7fb}.v3915ok{color:#89e6b4}.v3915warn{color:#ffd38a}.v3915code{font:10px ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all;color:#bddbff}
`;
  document.head.appendChild(x);
}

async function softRefs(sid){
  const r=await fetch('/api/v39/soft-prefabs?id='+encodeURIComponent(sid)+'&materialize=1',{cache:'no-store'});
  const d=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(d.message||d.error||('HTTP '+r.status));
  return d;
}
function collect(d){
  const seen=new Set(),out=[];
  for(const r of d?.items||[]){
    if(!eligible(r))continue;
    const b=r.best,sid=String(b.stable_id||'').toUpperCase();
    const key=(r.variant||'runtime')+'|'+sid;
    if(seen.has(key))continue;seen.add(key);
    out.push({variant:r.variant||'runtime',slot:r.nodePath||r.gameObject||'',best:b});
  }
  out.sort((a,b)=>(PRIORITY[a.variant]??9)-(PRIORITY[b.variant]??9)||String(a.slot).localeCompare(String(b.slot)));
  return out;
}
async function modelPayload(sid){
  const r=await fetch('/api/v33/model?id='+encodeURIComponent(sid),{cache:'no-store'});
  const d=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(d.message||d.error||('HTTP '+r.status));
  if(!d?.model)throw new Error('model-payload-missing');
  return d.model;
}
async function animationStatus(sid){
  try{
    const r=await fetch('/api/v39/animation?id='+encodeURIComponent(sid),{cache:'no-store'});
    const d=await r.json().catch(()=>({}));
    if(!r.ok)return '';
    return String(d?.classification?.status||'');
  }catch{return '';}
}

function navMarkup(){try{return typeof nav==='function'?nav():''}catch{return '';}}
function bindNativeNav(){try{if(typeof bindNav==='function')bindNav()}catch{}}
function destroyModel(){try{if(typeof currentModel!=='undefined'){currentModel?.destroy?.();currentModel=null;}}catch{}}

function openExact(c){
  try{if(window.WFGGAnimationResolverV392?.openDirect){window.WFGGAnimationResolverV392.openDirect(c.best);return;}}catch{}
  const q=document.getElementById('q');if(q)q.value=c.best.stable_id;
  document.getElementById('search')?.click();
}

function addBar(rootSid,candidates,current,status){
  const s=st();if(!s)return;
  document.getElementById('wfggV3915RuntimeBar')?.remove();
  const bar=document.createElement('div');bar.id='wfggV3915RuntimeBar';
  const label=document.createElement('div');label.className='v3915label';
  label.textContent=`Sous-prefab exact ${String(current.variant).toUpperCase()} · ${current.best.stable_id}${status?' · '+status:''}`;
  const states=document.createElement('div');states.className='v3915states';
  const uniq=[];const seen=new Set();
  for(const c of candidates){const k=c.variant+'|'+c.best.stable_id;if(seen.has(k))continue;seen.add(k);uniq.push(c);}
  for(const c of uniq.slice(0,4)){
    const b=document.createElement('button');b.type='button';b.textContent=String(c.variant||'runtime').toUpperCase();
    if(c.best.stable_id===current.best.stable_id&&c.variant===current.variant)b.classList.add('active');
    b.onclick=()=>showCandidate(rootSid,candidates,c);states.appendChild(b);
  }
  const open=document.createElement('button');open.type='button';open.className='open';open.textContent='Ouvrir';open.title='Ouvrir ce sous-prefab comme asset exact';open.onclick=()=>openExact(current);
  bar.append(label,states,open);s.appendChild(bar);
}

async function showCandidate(rootSid,candidates,c){
  const my=++seq;const s=st();if(!s)return false;
  s.innerHTML='<div id="wfggV3915Probe"><b>Chargement du sous-prefab exact '+esc(String(c.variant).toUpperCase())+'…</b><br><span class="v3915code">'+esc(c.best.stable_id)+'</span></div>'+navMarkup();bindNativeNav();
  try{
    const model=await modelPayload(c.best.stable_id);if(my!==seq||String(currentAsset?.stable_id||'')!==rootSid)return false;
    destroyModel();s.innerHTML='';
    currentModel=await WFGGModelViewer.mount(s,model);
    if(my!==seq||String(currentAsset?.stable_id||'')!==rootSid){destroyModel();return false;}
    s.insertAdjacentHTML('beforeend',navMarkup());bindNativeNav();
    const status=await animationStatus(c.best.stable_id);if(my!==seq)return false;
    runtimeState={rootSid,candidates,current:c,model,status};addBar(rootSid,candidates,c,status);
    console.info('V39_15_RUNTIME_CHILD_RENDER',rootSid,'->',c.best.stable_id,'variant='+c.variant,'status='+status);
    return true;
  }catch(e){
    console.warn('V39_15_RUNTIME_CHILD_FAIL',rootSid,c.best.stable_id,c.variant,e);
    return false;
  }
}

async function resolveAndRender(a){
  const rootSid=String(a?.stable_id||'').toUpperCase();if(!EXACT.test(rootSid))return;
  activeRoot=rootSid;const my=++seq;const s=st();if(!s)return;
  const original=s.innerHTML;
  s.innerHTML='<div id="wfggV3915Probe"><b>Prefab contrôleur détecté.</b><br>Résolution des sous-prefabs runtime exacts…</div>'+navMarkup();bindNativeNav();
  let d,candidates=[];
  try{d=await softRefs(rootSid);candidates=collect(d);}catch(e){if(my===seq&&String(currentAsset?.stable_id||'')===rootSid)s.innerHTML=original;return;}
  if(my!==seq||String(currentAsset?.stable_id||'')!==rootSid)return;
  if(!candidates.length){s.innerHTML=original;console.info('V39_15_RUNTIME_CHILD_NONE',rootSid,'softrefs='+String(d?.softReferenceCount||0));return;}

  /* Prefer WORK, then IDLE. If a proven child itself has no autonomous model, try the next proven state. */
  for(const c of candidates){
    if(my!==seq||String(currentAsset?.stable_id||'')!==rootSid)return;
    const ok=await showCandidate(rootSid,candidates,c);
    if(ok)return;
  }
  if(my!==seq)return;
  s.innerHTML='<div id="wfggV3915Probe"><b>Sous-prefabs runtime retrouvés, mais aucun Mesh autonome n’est encore rendu.</b><br><span class="v3915warn">Les références sont conservées sans substitution.</span><br>'+candidates.slice(0,8).map(c=>'<div class="v3915code">'+esc(String(c.variant).toUpperCase())+' · '+esc(c.best.stable_id)+' · '+esc(c.best.asset_path||'')+'</div>').join('')+'</div>'+navMarkup();bindNativeNav();
}

function maybe(a){
  if(!a?.stable_id)return;
  if(needsRuntimePreview(a)){
    const sid=String(a.stable_id).toUpperCase();
    if(activeRoot!==sid||!runtimeState)setTimeout(()=>resolveAndRender(a),0);
  }
}
function install(){
  if(installed||typeof select!=='function')return false;installed=true;injectStyle();
  const base=select;
  select=async function(i){
    activeRoot='';runtimeState=null;const r=await base(i);const a=currentAsset;setTimeout(()=>maybe(a),20);return r;
  };
  new MutationObserver(()=>{try{if(currentAsset?.stable_id)maybe(currentAsset)}catch{}}).observe(document.getElementById('stage')||document.body,{childList:true,subtree:true});
  if(currentAsset?.stable_id)setTimeout(()=>maybe(currentAsset),100);
  window.WFGGRuntimePrefabPreviewV3915={version:VERSION,ready:true,get state(){return runtimeState;},refresh:()=>{activeRoot='';runtimeState=null;currentAsset&&maybe(currentAsset)}};
  console.info('V39_15_RUNTIME_PREFAB_PREVIEW installed exact-softrefs-only=ON WORK-first=ON child-model=ON synthetic=OFF');
  return true;
}
injectStyle();if(!install()){let n=0,t=setInterval(()=>{if(install()||++n>40)clearInterval(t)},120);}
})();
