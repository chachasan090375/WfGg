(() => {
  'use strict';

  const MANIFEST='data/hero-native-animations.v17.json';
  const BASE=id=>`assets/heroes/${id}.webp`;
  const SPECIAL_STILL={
    elsa:'https://theriagames.com/wp-content/uploads/2024/12/Elsa.png',
    kane:'https://theriagames.com/wp-content/uploads/2024/12/Kane-1024x1024.png'
  };
  const NAMES={fr:{schuyler:'Skyler'},en:{schuyler:'Schuyler'},it:{schuyler:'Schuyler'},es:{schuyler:'Schuyler'}};
  const MASTER={id:'kimberly',version:'v19',topGapPct:5,composition:'head-shoulders-half-body'};
  const PROFILE={
    williams:{x:'0%',y:'4%',zoom:.84}, murphy:{x:'0%',y:'4%',zoom:.88}, kimberly:{x:'0%',y:'1%',zoom:.96}, marshall:{x:'0%',y:'-7%',zoom:.90},
    stetmann:{x:'0%',y:'-7%',zoom:.89}, dva:{x:'0%',y:'2%',zoom:.89}, carlie:{x:'0%',y:'1%',zoom:.91}, lucius:{x:'0%',y:'-8%',zoom:.87},
    schuyler:{x:'0%',y:'-9%',zoom:.87}, morrison:{x:'0%',y:'4%',zoom:.82}, tesla:{x:'0%',y:'3%',zoom:.89}, swift:{x:'0%',y:'-3%',zoom:.87},
    fiona:{x:'0%',y:'2%',zoom:.89}, adam:{x:'0%',y:'5%',zoom:.83}, mcgregor:{x:'0%',y:'3%',zoom:.89}, monica:{x:'0%',y:'1%',zoom:.93},
    mason:{x:'0%',y:'5%',zoom:.79}, violet:{x:'0%',y:'4%',zoom:.83}, scarlett:{x:'0%',y:'3%',zoom:.87}, richard:{x:'0%',y:'1%',zoom:.89},
    farhad:{x:'0%',y:'-8%',zoom:.88}, sarah:{x:'0%',y:'-6%',zoom:.89}, maxwell:{x:'0%',y:'-8%',zoom:.87}, cage:{x:'0%',y:'-6%',zoom:.87},
    venom:{x:'0%',y:'2%',zoom:.89}, braz:{x:'0%',y:'-7%',zoom:.89}, elsa:{x:'0%',y:'1%',zoom:.90}, gump:{x:'0%',y:'2%',zoom:.89},
    loki:{x:'0%',y:'5%',zoom:.72}, ambolt:{x:'0%',y:'4%',zoom:.80}, kane:{x:'0%',y:'1%',zoom:.90}
  };

  let manifest={animated:{}};
  let scheduled=false;
  const step=()=>document.getElementById('step-heroes');
  const grid=()=>document.getElementById('gameHeroGrid');
  const stepVisible=()=>{const s=step();return !!s&&!s.classList.contains('hidden')};
  const cards=()=>[...document.querySelectorAll('#gameHeroGrid .game-hero-card[data-hero-id]')];
  const imgFor=card=>card.querySelector('.wfgg-v15-motion-layer > img')||card.querySelector('.hero-card-portrait img');
  const animated=id=>manifest.animated?.[id]||null;
  const stillFor=id=>animated(id)?.still||SPECIAL_STILL[id]||BASE(id);
  const isPlaying=card=>card.classList.contains('wfgg-native-gif-active-v17c');
  const locale=()=>String(document.documentElement.lang||'fr').toLowerCase().split('-')[0];

  function installMasterCss(){
    if(document.getElementById('wfgg-kimberly-master-v19'))return;
    const style=document.createElement('style');
    style.id='wfgg-kimberly-master-v19';
    style.textContent='.game-hero-card .wfgg-v15-motion-layer{transform-origin:50% 0%!important}.game-hero-card .wfgg-v15-motion-layer>img{object-position:50% 0%!important;transform-origin:50% 0%!important}';
    document.head.appendChild(style);
  }

  function localize(card){
    const id=card.dataset.heroId;
    const translated=(NAMES[locale()]||NAMES.en)[id];
    if(!translated)return;
    const name=card.querySelector('.wfgg-v10-name');
    if(name)name.textContent=translated;
    const img=imgFor(card);
    if(img)img.alt=translated;
  }

  function applyProfile(card){
    const id=card.dataset.heroId;
    const p=PROFILE[id]||PROFILE.kimberly;
    card.style.setProperty('--wfgg-v15-x',p.x);
    card.style.setProperty('--wfgg-v15-y',p.y);
    card.style.setProperty('--wfgg-v15-zoom',String(p.zoom));
    card.dataset.wfggV18Crop=`${p.x},${p.y},${p.zoom}`;
    card.dataset.wfggV18Portrait='1';
    card.dataset.wfggMasterFrame='kimberly-v19';
    card.dataset.wfggMasterTop=String(MASTER.topGapPct);
    localize(card);
  }

  function ensureSource(card){
    const id=card.dataset.heroId;
    const img=imgFor(card);
    if(!id||!img||isPlaying(card))return;
    const wanted=stillFor(id);
    const current=img.getAttribute('src')||'';
    if(current!==wanted){
      img.dataset.wfggV18Fallback=BASE(id);
      img.src=wanted;
    }
    card.dataset.wfggV18Source=SPECIAL_STILL[id]?'official-web-fallback':'local';
  }

  function decorate(card){applyProfile(card);ensureSource(card)}
  function applyAll(){
    if(!stepVisible())return;
    cards().forEach(decorate);
    document.documentElement.dataset.wfggPortraitNormalize='v19-kimberly-master';
    document.documentElement.dataset.wfggPortraitCount=String(cards().length);
  }
  function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;applyAll()})}

  function onImageError(ev){
    const img=ev.target;
    if(!(img instanceof HTMLImageElement))return;
    const card=img.closest('.game-hero-card[data-hero-id]');
    if(!card)return;
    const fallback=BASE(card.dataset.heroId);
    if(img.getAttribute('src')!==fallback){img.src=fallback;card.dataset.wfggV18Recovered='1';card.dataset.wfggV18Source='fallback-local'}
  }

  async function init(){
    installMasterCss();
    try{const r=await fetch(MANIFEST,{cache:'force-cache'});if(r.ok)manifest=await r.json()}catch(_){manifest={animated:{}}}
    const s=step();if(s)new MutationObserver(schedule).observe(s,{attributes:true,attributeFilter:['class']});
    const g=grid();if(g){
      g.addEventListener('error',onImageError,true);
      new MutationObserver(muts=>{
        let needed=false;
        for(const m of muts){
          if(m.type==='childList')needed=true;
          if(m.type==='attributes'){
            const card=m.target?.classList?.contains('game-hero-card')?m.target:m.target?.closest?.('.game-hero-card[data-hero-id]');
            if(card){applyProfile(card);if(!isPlaying(card))ensureSource(card)}
          }
        }
        if(needed)schedule();
      }).observe(g,{subtree:true,childList:true,attributes:true,attributeFilter:['class','src']});
    }
    new MutationObserver(schedule).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
    document.getElementById('languageStrip')?.addEventListener('click',()=>setTimeout(schedule,40));
    let scrollTimer=0;
    window.addEventListener('scroll',()=>{if(!stepVisible())return;clearTimeout(scrollTimer);scrollTimer=setTimeout(applyAll,120)},{passive:true});
    window.WfGgHeroPortraitV18={version:'19.1.0-kimberly-master',master:MASTER,profileFor:id=>PROFILE[id]||PROFILE.kimberly,apply:applyAll};
    schedule();
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();