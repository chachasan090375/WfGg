(() => {
  'use strict';

  const MANIFEST='data/hero-native-animations.v17.json';
  const BASE=id=>`assets/heroes/${id}.webp`;
  const PROFILE={
    williams:{x:'0%',y:'1%',zoom:.92}, murphy:{x:'0%',y:'-11%',zoom:1.28}, kimberly:{x:'0%',y:'1%',zoom:.96}, marshall:{x:'0%',y:'2%',zoom:.94},
    stetmann:{x:'0%',y:'0%',zoom:.97}, dva:{x:'0%',y:'1%',zoom:.96}, carlie:{x:'0%',y:'0%',zoom:.99}, lucius:{x:'0%',y:'0%',zoom:.91},
    schuyler:{x:'0%',y:'1%',zoom:.91}, morrison:{x:'0%',y:'-8%',zoom:1.22}, tesla:{x:'0%',y:'1%',zoom:.95}, swift:{x:'0%',y:'1%',zoom:.91},
    fiona:{x:'0%',y:'0%',zoom:.93}, adam:{x:'0%',y:'-1%',zoom:.94}, mcgregor:{x:'0%',y:'-2%',zoom:1.00}, monica:{x:'0%',y:'-13%',zoom:1.00},
    mason:{x:'0%',y:'0%',zoom:.94}, violet:{x:'0%',y:'-1%',zoom:.96}, scarlett:{x:'0%',y:'-5%',zoom:.94}, richard:{x:'0%',y:'0%',zoom:.95},
    farhad:{x:'0%',y:'-2%',zoom:.99}, sarah:{x:'0%',y:'-7%',zoom:.98}, maxwell:{x:'0%',y:'0%',zoom:.97}, cage:{x:'0%',y:'0%',zoom:.97},
    venom:{x:'0%',y:'-3%',zoom:.96}, braz:{x:'0%',y:'-1%',zoom:.97}, elsa:{x:'0%',y:'-3%',zoom:.98}, gump:{x:'0%',y:'0%',zoom:.96},
    loki:{x:'0%',y:'-2%',zoom:.98}, ambolt:{x:'0%',y:'-24%',zoom:1.18}, kane:{x:'0%',y:'-2%',zoom:.98}
  };

  let manifest={animated:{}};
  let scheduled=false;
  const step=()=>document.getElementById('step-heroes');
  const grid=()=>document.getElementById('gameHeroGrid');
  const stepVisible=()=>{const s=step();return !!s&&!s.classList.contains('hidden')};
  const cards=()=>[...document.querySelectorAll('#gameHeroGrid .game-hero-card[data-hero-id]')];
  const imgFor=card=>card.querySelector('.wfgg-v15-motion-layer > img')||card.querySelector('.hero-card-portrait img');
  const animated=id=>manifest.animated?.[id]||null;
  const stillFor=id=>animated(id)?.still||BASE(id);
  const isPlaying=card=>card.classList.contains('wfgg-native-gif-active-v17c');

  function applyProfile(card){
    const id=card.dataset.heroId;
    const p=PROFILE[id]||{x:'0%',y:'0%',zoom:1};
    card.style.setProperty('--wfgg-v15-x',p.x);
    card.style.setProperty('--wfgg-v15-y',p.y);
    card.style.setProperty('--wfgg-v15-zoom',String(p.zoom));
    card.dataset.wfggV18Crop=`${p.x},${p.y},${p.zoom}`;
    card.dataset.wfggV18Portrait='1';
  }

  function ensureSource(card){
    const id=card.dataset.heroId;
    const img=imgFor(card);
    if(!id||!img||isPlaying(card))return;
    const wanted=stillFor(id);
    const current=img.getAttribute('src')||'';
    if(current!==wanted){img.dataset.wfggV18Fallback=BASE(id);img.src=wanted}
  }

  function decorate(card){applyProfile(card);ensureSource(card)}
  function applyAll(){
    if(!stepVisible())return;
    cards().forEach(decorate);
    document.documentElement.dataset.wfggPortraitNormalize='v18';
    document.documentElement.dataset.wfggPortraitCount=String(cards().length);
  }
  function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;applyAll()})}
  function onImageError(ev){
    const img=ev.target;if(!(img instanceof HTMLImageElement))return;
    const card=img.closest('.game-hero-card[data-hero-id]');if(!card)return;
    const fallback=BASE(card.dataset.heroId);
    if(img.getAttribute('src')!==fallback){img.src=fallback;card.dataset.wfggV18Recovered='1'}
  }

  async function init(){
    try{const r=await fetch(MANIFEST,{cache:'force-cache'});if(r.ok)manifest=await r.json()}catch(_){manifest={animated:{}}}
    const s=step();if(s)new MutationObserver(schedule).observe(s,{attributes:true,attributeFilter:['class']});
    const g=grid();
    if(g){
      g.addEventListener('error',onImageError,true);
      new MutationObserver(muts=>{
        let needed=false;
        for(const m of muts){
          if(m.type==='childList')needed=true;
          if(m.type==='attributes'&&m.target?.classList?.contains('game-hero-card')){applyProfile(m.target);if(!isPlaying(m.target))ensureSource(m.target)}
        }
        if(needed)schedule();
      }).observe(g,{subtree:true,childList:true,attributes:true,attributeFilter:['class']});
    }
    let scrollTimer=0;
    window.addEventListener('scroll',()=>{if(!stepVisible())return;clearTimeout(scrollTimer);scrollTimer=setTimeout(applyAll,120)},{passive:true});
    window.WfGgHeroPortraitV18={version:'18.0.0',profileFor:id=>PROFILE[id]||null,apply:applyAll};
    schedule();
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
