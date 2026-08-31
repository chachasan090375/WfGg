(()=>{
  const $=s=>document.querySelector(s);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const list=$('#candidateList'),notice=$('#familyNotice');
  fetch('/lab/bundle-reconstruction-data/family-14169.json?ts='+Date.now(),{cache:'no-store'})
    .then(r=>{if(!r.ok)throw new Error('manifest '+r.status);return r.json();})
    .then(m=>{
      const items=Array.isArray(m.candidates)?m.candidates:[];
      $('#candidateCount').textContent=items.length;
      $('#hitCount').textContent=m.hitCount??0;
      $('#readyCount').textContent=items.filter(x=>x.ready).length;
      notice.textContent=items.length
        ? 'Les bundles ci-dessous référencent exactement un ou plusieurs des 5 matériaux de 14169. Ouvre-les un par un : Reconstruction tente uniquement les liens réellement sérialisés.'
        : 'Aucun bundle candidat n’a encore été matérialisé. Relance le constructeur de famille dans Termux.';
      if(!items.length){list.innerHTML='<div class="status">Aucun candidat disponible.</div>';return;}
      list.innerHTML=items.map((x,i)=>{
        const mats=Array.isArray(x.materials)?x.materials:[];
        const types=Array.isArray(x.consumerTypes)?x.consumerTypes:[];
        const href='/lab/lastwar-bundle-reconstruction-viewer.html?bundle='+encodeURIComponent(x.bundleId);
        return `<article class="object-card">
          <strong>Bundle ${esc(x.bundleId)}</strong>
          <div class="meta">${esc(x.logicalName||x.aliasName||'nom non résolu')}</div>
          <div class="meta">Références matériau : ${esc(x.hitCount||0)}</div>
          <div class="meta">Matériaux : ${esc(mats.join(' · ')||'—')}</div>
          <div class="meta">Objets consommateurs : ${esc(types.join(' · ')||'—')}</div>
          <div class="meta">État : ${x.ready?'reconstruction locale prête':'non construit'}</div>
          ${x.ready?`<a class="back" style="display:inline-block;margin-top:10px" href="${href}">Ouvrir la reconstruction →</a>`:'<span class="tag">À construire</span>'}
        </article>`;
      }).join('');
    })
    .catch(e=>{
      $('#candidateCount').textContent='0';$('#hitCount').textContent='0';$('#readyCount').textContent='0';
      notice.textContent='La famille de bundles n’est pas encore construite.';
      list.innerHTML='<div class="status">'+esc(e.message)+'</div>';
    });
})();
