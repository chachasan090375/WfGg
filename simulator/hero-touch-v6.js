(() => {
  'use strict';
  const actionable = '.hero-sheet-close,.hero-sheet-tab,.hero-owned-action,.lw4-skill-btn,.lw4-tier-pip,.lw4-weapon-control button,.lw4-skill-level-row button';
  function bindButton(btn){
    if(!btn || btn.dataset.wfggTouchV6==='1') return;
    btn.dataset.wfggTouchV6='1';
    btn.addEventListener('touchend', e=>{
      e.preventDefault();
      e.stopPropagation();
      const sheet=btn.closest('#heroGameSheet');
      btn.click();
      if(btn.id==='heroSheetClose') requestAnimationFrame(()=>{
        if(sheet?.classList.contains('open')){
          sheet.classList.remove('open');
          document.querySelector('#heroGameBackdrop')?.classList.remove('open');
        }
      });
    },{passive:false});
  }
  function fixPortraits(root=document){
    root.querySelectorAll?.('.hero-card-portrait,.hero-sheet-portrait').forEach(box=>{
      const img=box.querySelector('img');
      const fallback=box.querySelector('.hero-fallback');
      if(!img){ if(fallback) fallback.style.display='grid'; return; }
      const good=()=>{ if(fallback) fallback.style.display='none'; box.classList.add('has-portrait'); };
      const bad=()=>{ try{img.remove()}catch(_){}; if(fallback) fallback.style.display='grid'; box.classList.remove('has-portrait'); };
      if(img.complete) (img.naturalWidth>0?good:bad)();
      else { img.addEventListener('load',good,{once:true}); img.addEventListener('error',bad,{once:true}); }
    });
  }
  function scan(){
    document.querySelectorAll(actionable).forEach(bindButton);
    fixPortraits();
  }
  const mo=new MutationObserver(()=>requestAnimationFrame(scan));
  document.addEventListener('DOMContentLoaded',()=>{scan();mo.observe(document.body,{subtree:true,childList:true});},{once:true});
  if(document.readyState!=='loading'){scan();mo.observe(document.body,{subtree:true,childList:true});}
})();
