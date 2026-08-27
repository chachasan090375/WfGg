(()=>{
  'use strict';
  const BASE=id=>`assets/heroes/cutout-v21/${id}.webp`;
  const FALLBACK=id=>`assets/heroes/master-v20/${id}.webp`;
  const step=()=>document.getElementById('step-heroes');
  const cards=()=>[...document.querySelectorAll('#gameHeroGrid .game-hero-card[data-hero-id]')];
  const imgFor=c=>c.querySelector('.wfgg-v15-motion-layer>img')||c.querySelector('.hero-card-portrait img');
  let queued=false;
  function apply(){
    if(step()?.classList.contains('hidden'))return;
    for(const c of cards()){
      const id=c.dataset.heroId,img=imgFor(c);if(!id||!img)continue;
      c.dataset.wfggCutout='v21';
      c.style.setProperty('--wfgg-v15-x','0%');
      c.style.setProperty('--wfgg-v15-y','0%');
      c.style.setProperty('--wfgg-v15-zoom','1');
      const wanted=BASE(id);
      if(!img.src.includes(`/cutout-v21/${id}.webp`)){
        img.dataset.wfggV21Fallback=FALLBACK(id);img.src=wanted;
      }
    }
    document.documentElement.dataset.wfggHeroCutout='v21';
    document.documentElement.dataset.wfggHeroCutoutCount=String(cards().length);
  }
  function schedule(){if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;apply()})}
  function err(e){const img=e.target;if(!(img instanceof HTMLImageElement))return;const c=img.closest('.game-hero-card[data-hero-id]');if(!c)return;const fb=img.dataset.wfggV21Fallback;if(fb&&img.getAttribute('src')!==fb)img.src=fb}
  function init(){
    const s=step();if(s)new MutationObserver(schedule).observe(s,{attributes:true,attributeFilter:['class']});
    const g=document.getElementById('gameHeroGrid');if(g){g.addEventListener('error',err,true);new MutationObserver(schedule).observe(g,{childList:true,subtree:true})}
    schedule();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
