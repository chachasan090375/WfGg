(() => {
  'use strict';
  const KEY='wfgg-simulator-wall-honor-v11';
  let queued=false;
  const norm=v=>String(v||'').trim().toLowerCase();
  const read=()=>{try{return JSON.parse(localStorage.getItem(KEY)||'{}')||{}}catch{return {}}};
  const write=s=>localStorage.setItem(KEY,JSON.stringify(s));
  function heroOf(el){return el?.closest?.('.v11-honor-page')?.dataset?.v11Hero||''}
  function save(el){
    const hero=heroOf(el);if(!hero)return;
    const key=norm(hero),s=read(),d=s[key]||{};
    if(el.matches('[data-v11-honor-level]'))d.level=Math.max(0,Math.round(Number(el.value)||0));
    if(el.matches('[data-v11-honor-bonus]'))d[el.dataset.v11HonorBonus]=Math.max(0,Number(el.value)||0);
    s[key]=d;write(s);
  }
  function hydrate(){
    queued=false;
    document.querySelectorAll('.v11-honor-page[data-v11-hero]').forEach(page=>{
      const d=read()[norm(page.dataset.v11Hero)];if(!d)return;
      const level=page.querySelector('[data-v11-honor-level]'),label=page.querySelector('[data-v11-honor-level-label]');
      if(level&&d.level!=null&&level!==document.activeElement)level.value=String(d.level);
      if(label&&d.level!=null)label.textContent=String(d.level);
      page.querySelectorAll('[data-v11-honor-bonus]').forEach(el=>{const v=d[el.dataset.v11HonorBonus];if(v!=null&&el!==document.activeElement)el.value=String(v)});
    });
  }
  function queue(){if(queued)return;queued=true;requestAnimationFrame(hydrate)}
  document.addEventListener('input',e=>{if(e.target?.matches?.('[data-v11-honor-level],[data-v11-honor-bonus]'))save(e.target)},{capture:true});
  document.addEventListener('change',e=>{if(e.target?.matches?.('[data-v11-honor-level],[data-v11-honor-bonus]'))save(e.target)},{capture:true});
  if(document.body)new MutationObserver(queue).observe(document.body,{childList:true,subtree:true});
  else document.addEventListener('DOMContentLoaded',()=>new MutationObserver(queue).observe(document.body,{childList:true,subtree:true}),{once:true});
  window.WfGgWallHonorPersistence=Object.freeze({version:'12.1.0',key:KEY,refresh:queue});
})();
