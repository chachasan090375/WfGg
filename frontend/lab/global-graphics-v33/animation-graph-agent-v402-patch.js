(()=>{
'use strict';
/* V40.2 UI patch: enrich the existing V40 modal with lifecycle-aware motion evidence. */
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function inject(){
  const modal=document.getElementById('wfggV40Modal');if(!modal)return;
  const d=window.WFGGAnimationGraphV40?.last;if(!d||String(d.version)!=='40.2')return;
  const h=modal.querySelector('h2');if(h)h.textContent='🧠 Animation Graph Agent — V40.2';
  if(modal.querySelector('#wfggV402Phase'))return;
  const body=modal.querySelector('.body'),hero=body?.querySelector('.hero');if(!body||!hero)return;
  const a=d.motionAnalysis||{},xs=d.motionRecipe||[];
  const box=document.createElement('details');box.id='wfggV402Phase';box.open=true;
  box.innerHTML=`<summary>V40.2 · Mouvement continu vs initialisation</summary>
    <div class="grid">
      <div class="stat"><b>${esc(a.continuousCount||0)}</b><small>mouvements continus prouvés</small></div>
      <div class="stat"><b>${esc(a.initializationCount||0)}</b><small>initialisations</small></div>
      <div class="stat"><b>${esc(a.stateEventCount||0)}</b><small>événements d’état</small></div>
      <div class="stat"><b>${esc(a.methodsVisited||0)}</b><small>méthodes suivies récursivement</small></div>
    </div>
    ${xs.length?`<table><thead><tr><th>Phase</th><th>Mouvement</th><th>Confiance</th><th>Chaîne d'appel</th><th>Source</th></tr></thead><tbody>${xs.slice(0,18).map(x=>`<tr><td><span class="v40pill ${x.continuous?'v40good':'v40warn'}">${esc(x.phase||'—')}</span></td><td><b>${esc(x.type||'')}</b></td><td>${Math.round(Number(x.confidence||0)*100)} %</td><td><code>${esc(x.evidence?.method||'')}</code><br>${esc(x.evidence?.call||'')}</td><td>${esc(x.evidence?.className||'')}<br><code>${esc(x.evidence?.gameObject||x.evidence?.asset||'')}</code></td></tr>`).join('')}</tbody></table>`:'<div class="muted">Aucun appel moteur de mouvement prouvé.</div>'}`;
  hero.insertAdjacentElement('afterend',box);
  const btn=document.getElementById('wfggV40Btn');if(btn)btn.textContent=a.continuousCount?'🧠 V40.2 · mouvement continu':'🧠 V40.2 · graphe';
}
setInterval(inject,180);
console.info('V40_2_UI lifecycle-motion-panel=ON continuous-vs-init=ON');
})();
