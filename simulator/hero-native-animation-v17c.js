(() => {
  'use strict';

  const MANIFEST='data/hero-native-animations.v17.json';
  const SYNTH=['wfgg-live-card','wfgg-v10-live','wfgg-v12-live','wfgg-v13-live','wfgg-v14-live','wfgg-v15-live'];
  const ACTIVE_MS=3600;
  const REST_MS=1500;
  const START_DELAY_MS=900;
  const CROP={
    monica:{x:'0%',y:'-9%',zoom:1.03},
    murphy:{x:'1%',y:'-20%',zoom:1.55},
    schuyler:{x:'0%',y:'5%',zoom:.94},
    sarah:{x:'0%',y:'1%',zoom:1.04},
    gump:{x:'0%',y:'2%',zoom:1.00},
    loki:{x:'0%',y:'0%',zoom:1.00}
  };

  let manifest={animated:{}};
  let timer=0;
  let running=false;
  let generation=0;
  let active=[];
  let stepObserver=null;
  let gridObserver=null;

  window.WfGgHeroMotionOwner='native-v17c';
  window.WfGgHeroNativeAnimationV17C={version:'17.2.0-nonblocking'};
  document.documentElement.dataset.wfggRosterMotion='native-gifs-v17c-nonblocking';
  document.documentElement.dataset.wfggV17cPhase='idle';

  const info=id=>manifest.animated?.[id]||null;
  const heroStep=()=>document.getElementById('step-heroes');
  const grid=()=>document.getElementById('gameHeroGrid');
  const stepVisible=()=>{
    const s=heroStep();
    return !!s && !s.classList.contains('hidden') && document.visibilityState==='visible';
  };
  const allCards=()=>[...document.querySelectorAll('#gameHeroGrid .game-hero-card[data-hero-id]')];
  const viewportCards=()=>allCards().filter(card=>{
    if(card.offsetParent===null)return false;
    const r=card.getBoundingClientRect();
    return r.bottom>0 && r.top<innerHeight && r.right>0 && r.left<innerWidth;
  });
  const shuffle=a=>{
    a=a.slice();
    for(let i=a.length-1;i>0;i--){
      const j=Math.floor(Math.random()*(i+1));
      [a[i],a[j]]=[a[j],a[i]];
    }
    return a;
  };
  const imgFor=card=>card.querySelector('.wfgg-v15-motion-layer > img')||card.querySelector('.hero-card-portrait img');

  function neutralize(card){
    SYNTH.forEach(cls=>card.classList.remove(cls));
    card.style.removeProperty('--wfgg-v15-delay');
  }

  function applyCrop(card){
    const c=CROP[card.dataset.heroId];
    if(!c)return;
    card.style.setProperty('--wfgg-v15-x',c.x);
    card.style.setProperty('--wfgg-v15-y',c.y);
    card.style.setProperty('--wfgg-v15-zoom',String(c.zoom));
    card.dataset.wfggV17cCrop=`${c.x},${c.y},${c.zoom}`;
  }

  function toStill(card){
    const a=info(card.dataset.heroId);
    const img=imgFor(card);
    if(!img)return;
    neutralize(card);
    card.classList.remove('wfgg-native-gif-active-v17b','wfgg-native-gif-active-v17c','wfgg-native-animated-monica');
    if(a?.still){
      if(img.getAttribute('src')!==a.still)img.src=a.still;
      card.classList.add('wfgg-native-gif-capable-v17c');
      card.classList.remove('wfgg-native-gif-capable-v17b');
      card.dataset.wfggNativeAnimation='native-gif-ready-v17c';
      applyCrop(card);
    }
  }

  function stop({restore=true}={}){
    generation++;
    running=false;
    clearTimeout(timer);
    timer=0;
    if(restore){
      active.forEach(toStill);
      active=[];
    }
    document.documentElement.dataset.wfggV17cPhase='idle';
    document.documentElement.dataset.wfggV17cActive='0';
  }

  function preload(url,token){
    return new Promise(resolve=>{
      if(!url || token!==generation){resolve(false);return;}
      const img=new Image();
      let done=false;
      const finish=ok=>{if(done)return;done=true;resolve(ok)};
      img.onload=()=>finish(true);
      img.onerror=()=>finish(false);
      img.src=url;
      if(img.complete)finish(true);
      setTimeout(()=>finish(false),2500);
    });
  }

  async function activateNext(token){
    if(token!==generation || !running || !stepVisible())return;

    const candidates=shuffle(viewportCards().filter(card=>info(card.dataset.heroId)));
    if(!candidates.length){
      timer=setTimeout(()=>activateNext(token),1200);
      return;
    }

    // Mobile stability first: only 3 real GIF decoders at once; 4 on wider screens.
    const maxActive=innerWidth<=600?3:4;
    const group=candidates.slice(0,Math.min(maxActive,candidates.length));

    document.documentElement.dataset.wfggV17cPhase='preload';
    const loaded=[];
    // Preload sequentially to avoid a CPU/memory spike on Android.
    for(const card of group){
      if(token!==generation || !running || !stepVisible())return;
      const a=info(card.dataset.heroId);
      if(await preload(a?.src||'',token))loaded.push(card);
    }

    if(token!==generation || !running || !stepVisible())return;
    active=loaded.filter(card=>card.isConnected && card.offsetParent!==null);
    for(const card of active){
      neutralize(card);
      applyCrop(card);
      const a=info(card.dataset.heroId);
      const img=imgFor(card);
      if(a?.src && img){
        img.src=a.src;
        card.classList.add('wfgg-native-gif-active-v17c');
        card.dataset.wfggNativeAnimation='native-gif-playing-v17c';
      }
    }

    document.documentElement.dataset.wfggV17cPhase='active';
    document.documentElement.dataset.wfggV17cActive=String(active.length);
    document.documentElement.dataset.wfggV17cBatch=active.map(c=>c.dataset.heroId).join(',');

    timer=setTimeout(()=>{
      if(token!==generation || !running)return;
      active.forEach(toStill);
      active=[];
      document.documentElement.dataset.wfggV17cPhase='rest';
      document.documentElement.dataset.wfggV17cActive='0';
      timer=setTimeout(()=>activateNext(token),REST_MS);
    },ACTIVE_MS);
  }

  function start(){
    if(running || !stepVisible())return;
    running=true;
    const token=++generation;

    // Prime only the visible cards, only after the Heroes panel is actually open.
    viewportCards().forEach(card=>{
      neutralize(card);
      if(info(card.dataset.heroId))toStill(card);
    });

    const launch=()=>{
      if(token!==generation || !running || !stepVisible())return;
      activateNext(token);
    };
    if('requestIdleCallback' in window){
      requestIdleCallback(launch,{timeout:START_DELAY_MS+1000});
    }else{
      timer=setTimeout(launch,START_DELAY_MS);
    }
  }

  function syncVisibility(){
    if(stepVisible()){
      if(!running){
        clearTimeout(timer);
        timer=setTimeout(start,START_DELAY_MS);
      }
    }else{
      stop({restore:true});
    }
  }

  async function init(){
    // Nothing touches hero images/classes before the app itself is interactive.
    try{
      const r=await fetch(MANIFEST,{cache:'force-cache'});
      if(r.ok)manifest=await r.json();
    }catch(_){
      manifest={animated:{}};
    }

    const s=heroStep();
    if(s){
      stepObserver=new MutationObserver(syncVisibility);
      stepObserver.observe(s,{attributes:true,attributeFilter:['class']});
    }

    const g=grid();
    if(g){
      gridObserver=new MutationObserver(()=>{
        if(stepVisible()){
          viewportCards().forEach(card=>{
            neutralize(card);
            if(info(card.dataset.heroId) && !card.classList.contains('wfgg-native-gif-active-v17c'))toStill(card);
          });
        }
      });
      gridObserver.observe(g,{childList:true,subtree:false});
    }

    document.addEventListener('visibilitychange',syncVisibility,{passive:true});
    window.addEventListener('pagehide',()=>stop({restore:false}),{once:true});
    window.addEventListener('scroll',()=>{
      if(!stepVisible() || !running)return;
      // Do not mutate while scrolling; restart cleanly after scrolling settles.
      clearTimeout(timer);
      timer=setTimeout(()=>{
        if(stepVisible()){
          active.forEach(toStill);
          active=[];
          const token=generation;
          activateNext(token);
        }
      },450);
    },{passive:true});

    syncVisibility();
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
