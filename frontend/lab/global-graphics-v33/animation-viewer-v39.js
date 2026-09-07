(()=>{
'use strict';
/* WfGg V39 — exact animated-prefab diagnostics.
   This UI never fabricates movement. It reports only evidence returned by /api/v39/animation.
*/

const VERSION='39.0';
let installed=false;
let lastSid='';
let lastData=null;
let requestToken=0;
let modal=null;

function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fmt(n,d=2){const x=Number(n);return Number.isFinite(x)?x.toFixed(d):'—';}
function plural(n,s,p=s+'s'){return `${n} ${Number(n)===1?s:p}`;}
function byId(id){return document.getElementById(id);}

function injectStyle(){
  if(byId('wfgg-v39-style'))return;
  const s=document.createElement('style');s.id='wfgg-v39-style';s.textContent=`
#wfggV39Badge{position:absolute;z-index:24;left:12px;top:12px;display:flex;gap:7px;align-items:center;max-width:calc(100% - 24px);font:700 11px/1.2 system-ui,sans-serif}
#wfggV39Badge button{border:1px solid rgba(255,255,255,.18);border-radius:999px;padding:7px 10px;background:rgba(20,20,27,.90);color:#eee;box-shadow:0 5px 18px rgba(0,0,0,.28);backdrop-filter:blur(7px);cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:min(440px,80vw)}
#wfggV39Badge button[data-state="animated-transform"]{border-color:#66d9cf;color:#c8fff9}
#wfggV39Badge button[data-state="animated-clip"]{border-color:#8bc8ff;color:#d8efff}
#wfggV39Badge button[data-state="animated-particles"]{border-color:#e5b9ff;color:#f1ddff}
#wfggV39Badge button[data-state="animated-script"]{border-color:#ffd07d;color:#ffe8b8}
#wfggV39Badge button[data-state="error"]{border-color:#ff8e8e;color:#ffd0d0}
#wfggV39Badge .spin{width:9px;height:9px;border:2px solid #777;border-top-color:#eee;border-radius:50%;display:inline-block;animation:wfgg39spin .8s linear infinite;margin-right:5px;vertical-align:-1px}@keyframes wfgg39spin{to{transform:rotate(360deg)}}
#wfggV39Modal{position:fixed;z-index:10040;inset:0;background:rgba(0,0,0,.72);display:flex;align-items:center;justify-content:center;padding:16px;font-family:system-ui,sans-serif;color:#eee}
#wfggV39Modal .v39box{width:min(980px,96vw);height:min(820px,92vh);background:#17171f;border:1px solid #383844;border-radius:18px;overflow:hidden;box-shadow:0 24px 80px rgba(0,0,0,.55);display:flex;flex-direction:column}
#wfggV39Modal .v39head{display:flex;align-items:flex-start;gap:12px;padding:15px 16px;border-bottom:1px solid #32323d;background:#1e1e28}
#wfggV39Modal .v39head h2{font-size:16px;margin:0 0 3px}.v39muted{color:#9d9daa;font-size:12px}.v39grow{flex:1}
#wfggV39Modal .v39close{border:0;background:#30303b;color:#eee;border-radius:9px;padding:7px 10px;cursor:pointer}
#wfggV39Modal .v39body{padding:14px 16px 24px;overflow:auto}
#wfggV39Modal .v39hero{padding:12px 13px;border:1px solid #393946;background:#20202a;border-radius:12px;margin-bottom:12px}
#wfggV39Modal .v39hero strong{display:block;font-size:15px;margin-bottom:4px}
#wfggV39Modal .v39grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:8px;margin:10px 0 14px}
#wfggV39Modal .v39stat{background:#20202a;border:1px solid #33333f;border-radius:10px;padding:9px}.v39stat b{display:block;font-size:15px}.v39stat span{font-size:11px;color:#aaa}
#wfggV39Modal details{border-top:1px solid #30303a;padding:9px 0}#wfggV39Modal summary{cursor:pointer;font-weight:700;font-size:13px}
#wfggV39Modal table{width:100%;border-collapse:collapse;margin-top:8px;font-size:11px}#wfggV39Modal td,#wfggV39Modal th{text-align:left;vertical-align:top;border-bottom:1px solid #2e2e38;padding:6px 5px;word-break:break-word}
#wfggV39Modal th{color:#aaa;font-weight:600}.v39pill{display:inline-block;border:1px solid #4a4a58;border-radius:999px;padding:3px 7px;margin:2px 3px 2px 0;font-size:10px;background:#262631}
#wfggV39Modal .v39warning{border-left:3px solid #d8a851;background:#272319;padding:9px 11px;border-radius:8px;margin:8px 0;color:#ead8b5;font-size:12px}
#wfggV39Modal .v39ok{border-left:3px solid #69cdbf;background:#182624;padding:9px 11px;border-radius:8px;margin:8px 0;color:#c8f6ef;font-size:12px}
#wfggV39Modal .v39controls{display:flex;gap:7px;flex-wrap:wrap;margin-top:9px}#wfggV39Modal .v39controls button{border:1px solid #40404c;border-radius:8px;background:#282833;color:#aaa;padding:7px 10px}#wfggV39Modal .v39controls button:not(:disabled){color:#fff;cursor:pointer;border-color:#6b6b7a}
#wfggV39Modal code{font-size:10px;color:#b8d9ff}.v39tree{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:10px;white-space:pre-wrap;word-break:break-word;background:#121218;padding:9px;border-radius:8px;max-height:280px;overflow:auto}
`;
  document.head.appendChild(s);
}

function stage(){return document.querySelector('#stage');}
function ensureStagePosition(el){try{if(getComputedStyle(el).position==='static')el.style.position='relative';}catch{}}
function removeBadge(){byId('wfggV39Badge')?.remove();}
function badge(label,state='loading',loading=false){
  const st=stage();if(!st)return;ensureStagePosition(st);removeBadge();
  const box=document.createElement('div');box.id='wfggV39Badge';
  const b=document.createElement('button');b.type='button';b.dataset.state=state;
  b.innerHTML=(loading?'<span class="spin"></span>':'')+esc(label);
  b.title='Diagnostic animation Unity V39';
  if(!loading)b.onclick=()=>openModal();
  box.appendChild(b);st.appendChild(box);
}

function statusLabel(d){return d?.classification?.status||'ANIMATION À ANALYSER';}
function clipRows(d){
  const clips=d?.clips?.items||[];
  if(!clips.length)return '<div class="v39muted">Aucun AnimationClip résolu dans la fermeture inspectée.</div>';
  return `<table><thead><tr><th>Clip</th><th>Liaison</th><th>Durée</th><th>Courbes</th><th>Échant.</th></tr></thead><tbody>${clips.slice(0,80).map(c=>{
    const cc=c.curveCounts||{};const curves=['position','rotation','euler','scale','compressedRotation','float'].map(k=>`${k}:${cc[k]||0}`).join(' · ');
    return `<tr><td><b>${esc(c.name||'(sans nom)')}</b><br><code>PathID ${esc(c.pathId)}</code></td><td>${esc(c.linkage||'')}<br><span class="v39muted">${esc((c.evidence||[]).join(' · '))}</span></td><td>${c.duration==null?'—':fmt(c.duration,3)+' s'}</td><td>${esc(curves)}<br><span class="v39muted">${plural(c.simpleTransformKeyCount||0,'clé')}</span></td><td>${c.sampleRate==null?'—':fmt(c.sampleRate,1)+' Hz'}</td></tr>`;
  }).join('')}</tbody></table>`;
}

function scriptRows(d){
  const xs=d?.components?.scripts||[];if(!xs.length)return '<div class="v39muted">Aucun MonoBehaviour sur le prefab ancré.</div>';
  return `<table><thead><tr><th>GameObject</th><th>Script</th><th>Signal animation</th></tr></thead><tbody>${xs.slice(0,120).map(x=>`<tr><td>${esc(x.nodePath||x.gameObject||'(root)')}</td><td><b>${esc(x.className||x.scriptName||'(non résolu)')}</b><br><span class="v39muted">${esc(x.namespace||'')} ${esc(x.assembly||'')}</span></td><td>${x.animationHint?'<span class="v39pill">animation probable</span>':'—'}</td></tr>`).join('')}</tbody></table>`;
}

function treeText(d){
  const nodes=d?.hierarchy?.nodes||[];
  return nodes.slice(0,480).map(n=>{
    const p=n.path||'(root)';const c=(n.components||[]).filter(x=>x!=='Transform'&&x!=='RectTransform');
    const tr=n.localTransform||{};return `${p}\n  components: ${c.join(', ')||'—'}\n  pos: ${JSON.stringify(tr.position||[])} rot: ${JSON.stringify(tr.rotation||[])} scale: ${JSON.stringify(tr.scale||[])}`;
  }).join('\n');
}

function modalHtml(d){
  const play=d?.playback||{},h=d?.hierarchy||{},comp=d?.components||{},clips=d?.clips||{};
  const unresolved=play.unresolvedReasons||[];
  const exactCurves=!!play.tracksDecodable;
  return `<div class="v39box" role="dialog" aria-modal="true" aria-label="Diagnostic animation V39">
    <div class="v39head"><div class="v39grow"><h2>Animation / prefab — V39</h2><div class="v39muted">${esc(d?.stableId||lastSid)} · racine ${esc(d?.rootGameObject||'—')}</div></div><button class="v39close" id="wfggV39Close">Fermer</button></div>
    <div class="v39body">
      <div class="v39hero"><strong>${esc(statusLabel(d))}</strong><div class="v39muted">${esc(play.label||'')}</div>${exactCurves?'<div class="v39ok">Des courbes Transform exactes sont décodées. Elles ne sont pas encore appliquées aux OBJ dont les coordonnées monde sont figées.</div>':''}${unresolved.map(x=>`<div class="v39warning">${esc(x)}</div>`).join('')}</div>
      <div class="v39grid">
        <div class="v39stat"><b>${h.nodeCount||0}</b><span>GameObjects / nœuds</span></div>
        <div class="v39stat"><b>${comp.animatorOrAnimationCount||0}</b><span>Animator / Animation</span></div>
        <div class="v39stat"><b>${clips.directLinkedCount||0}</b><span>clips liés exactement</span></div>
        <div class="v39stat"><b>${play.exactTransformTrackCount||0}</b><span>pistes Transform décodées</span></div>
        <div class="v39stat"><b>${comp.particleSystemCount||0}</b><span>ParticleSystem</span></div>
        <div class="v39stat"><b>${comp.animationHintScriptCount||0}</b><span>scripts à signal animation</span></div>
      </div>
      <div><b>Lecture</b><div class="v39muted">La lecture reste verrouillée tant que le moteur ne peut pas appliquer les pistes à la hiérarchie sans approximation.</div><div class="v39controls"><button disabled>▶ Lecture</button><button disabled>⏸ Pause</button><button disabled>↻ Boucle</button><button disabled>0,5×</button><button disabled>1×</button><button disabled>2×</button></div></div>
      <details open><summary>AnimationClips (${(clips.items||[]).length})</summary>${clipRows(d)}</details>
      <details><summary>ParticleSystem (${comp.particleSystemCount||0})</summary>${(comp.particles||[]).length?`<table><tbody>${comp.particles.map(x=>`<tr><td>${esc(x.nodePath||'(root)')}</td><td><code>PathID ${esc(x.pathId)}</code></td></tr>`).join('')}</tbody></table>`:'<div class="v39muted">Aucun.</div>'}</details>
      <details><summary>MonoBehaviours (${comp.monoBehaviourCount||0})</summary>${scriptRows(d)}</details>
      <details><summary>Hiérarchie exacte (${h.nodeCount||0} nœuds)</summary><div class="v39tree">${esc(treeText(d))}</div></details>
      <details><summary>Provenance / garde-fous</summary><div class="v39muted">Ancrage : <code>${esc(d?.rootAnchor||'—')}</code><br>Cache : ${d?.cacheHit?'hit':'miss'} · scan ${fmt(d?.scanSeconds,3)} s<br>${esc(d?.policy||'')}</div></details>
    </div></div>`;
}

function closeModal(){modal?.remove();modal=null;}
function openModal(){
  if(!lastData)return;closeModal();modal=document.createElement('div');modal.id='wfggV39Modal';modal.innerHTML=modalHtml(lastData);document.body.appendChild(modal);
  byId('wfggV39Close')?.addEventListener('click',closeModal);modal.addEventListener('click',e=>{if(e.target===modal)closeModal();});
}

async function loadFor(a){
  const sid=String(a?.stable_id||'');if(!/^LWGA-[A-Z0-9]+$/.test(sid))return;
  const token=++requestToken;lastSid=sid;lastData=null;badge('Analyse animation Unity…','loading',true);
  try{
    const r=await fetch('/api/v39/animation?id='+encodeURIComponent(sid),{cache:'no-store'});
    const d=await r.json().catch(()=>({}));
    if(token!==requestToken||String(currentAsset?.stable_id||'')!==sid)return;
    if(!r.ok)throw new Error(d.message||d.error||('HTTP '+r.status));
    lastData=d;badge(statusLabel(d),d?.classification?.code||'static-or-undetected',false);
    window.WFGGAnimationV39.last=d;
    console.info('V39_ANIMATION_DIAGNOSTIC',sid,d.classification,d.playback);
  }catch(e){
    if(token!==requestToken||String(currentAsset?.stable_id||'')!==sid)return;
    lastData={stableId:sid,classification:{status:'ANIMATION — DIAGNOSTIC INDISPONIBLE',code:'error'},playback:{label:String(e)}};
    badge('Animation : diagnostic indisponible','error',false);console.warn('V39_ANIMATION_DIAGNOSTIC_FAIL',sid,e);
  }
}

function install(){
  if(installed||typeof select!=='function')return false;installed=true;injectStyle();
  const baseSelect=select;
  select=async function(i){
    const expected=items?.[i];const task=baseSelect(i);try{await task;}catch(e){throw e;}finally{
      const a=currentAsset;if(a?.stable_id&&a.stable_id===expected?.stable_id)setTimeout(()=>loadFor(a),0);
      else if(a?.stable_id&&a.stable_id!==lastSid)setTimeout(()=>loadFor(a),0);
    }
  };
  if(currentAsset?.stable_id)setTimeout(()=>loadFor(currentAsset),80);
  window.WFGGAnimationV39={version:VERSION,ready:true,get last(){return lastData;},refresh:()=>currentAsset&&loadFor(currentAsset),open:openModal};
  console.info('V39_ANIMATION_VIEWER installed exact-diagnostics=ON synthetic-motion=OFF');return true;
}

injectStyle();
if(!install()){let tries=0;const t=setInterval(()=>{tries++;if(install()||tries>30)clearInterval(t);},120);}
})();
