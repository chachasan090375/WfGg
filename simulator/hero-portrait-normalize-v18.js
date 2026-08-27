(() => {
  'use strict';
  const BASE=id=>`assets/heroes/master-v20/${id}.webp`;
  const FALLBACK=id=>`assets/heroes/${id}.webp`;
  const NAMES={fr:{schuyler:'Skyler'},en:{schuyler:'Schuyler'},it:{schuyler:'Schuyler'},es:{schuyler:'Schuyler'}};
  let scheduled=false;
  const step=()=>document.getElementById('step-heroes');
  const grid=()=>document.getElementById('gameHeroGrid');
  const visible=()=>{const s=step();return !!s&&!s.classList.contains('hidden')};
  const cards=()=>[...document.querySelectorAll('#gameHeroGrid .game-hero-card[data-hero-id]')];
  const imgFor=c=>c.querySelector('.wfgg-v15-motion-layer > img')||c.querySelector('.hero-card-portrait img');
  const locale=()=>String(document.documentElement.lang||'fr').toLowerCase().split('-')[0];
  function decorate(c){
    const id=c.dataset.heroId,img=imgFor(c);if(!id||!img)return;
    c.style.setProperty('--wfgg-v15-x','0%');c.style.setProperty('--wfgg-v15-y','0%');c.style.setProperty('--wfgg-v15-zoom','1');
    c.dataset.wfggMasterFrame='kimberly-v20-static';c.dataset.wfggV18Crop='0%,0%,1';
    const translated=(NAMES[locale()]||NAMES.en)[id];if(translated){const n=c.querySelector('.wfgg-v10-name');if(n)n.textContent=translated;img.alt=translated}
    const wanted=BASE(id);if(img.getAttribute('src')!==wanted){img.dataset.wfggV20Fallback=FALLBACK(id);img.src=wanted}
  }
  function apply(){if(!visible())return;cards().forEach(decorate);document.documentElement.dataset.wfggPortraitNormalize='v20-static-kimberly-master';document.documentElement.dataset.wfggPortraitCount=String(cards().length)}
  function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;apply()})}
  function onError(ev){const img=ev.target;if(!(img instanceof HTMLImageElement))return;const c=img.closest('.game-hero-card[data-hero-id]');if(!c)return;const fb=img.dataset.wfggV20Fallback||FALLBACK(c.dataset.heroId);if(img.getAttribute('src')!==fb){img.src=fb;c.dataset.wfggV20Recovered='1'}}
  function init(){const s=step();if(s)new MutationObserver(schedule).observe(s,{attributes:true,attributeFilter:['class']});const g=grid();if(g){g.addEventListener('error',onError,true);new MutationObserver(schedule).observe(g,{childList:true,subtree:true})}new MutationObserver(schedule).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});window.WfGgHeroPortraitV18={version:'20.2.0-static-kimberly-master',master:{id:'kimberly',topGapPct:5,canvas:400},profileFor:()=>({x:'0%',y:'0%',zoom:1}),apply};schedule()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
