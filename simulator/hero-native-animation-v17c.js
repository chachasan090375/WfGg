(() => {
  'use strict';

  const MANIFEST='data/hero-native-animations.v17.json';
  const EXTERNAL_ANIMATED={
    elsa:{src:'https://theriagames.com/wp-content/uploads/2025/05/Elsa1.gif',still:'https://theriagames.com/wp-content/uploads/2024/12/Elsa.png'},
    kane:{src:'https://theriagames.com/wp-content/uploads/2025/05/Kane1.gif',still:'https://theriagames.com/wp-content/uploads/2024/12/Kane-1024x1024.png'}
  };
  const SYNTH=['wfgg-live-card','wfgg-v10-live','wfgg-v12-live','wfgg-v13-live','wfgg-v14-live','wfgg-v15-live'];
  const ACTIVE_MS=3600;
  const REST_MS=1500;
  const START_DELAY_MS=900;
  let manifest={animated:{}};
  let timer=0,running=false,generation=0,active=[],stepObserver=null,gridObserver=null;

  window.WfGgHeroMotionOwner='native-v17c';
  window.WfGgHeroNativeAnimationV17C={version:'17.4.0-master-plus-elsa-kane'};
  document.documentElement.dataset.wfggRosterMotion='native-gifs-v17c-nonblocking';
  document.documentElement.dataset.wfggV17cPhase='idle';

  const info=id=>manifest.animated?.[id]||EXTERNAL_ANIMATED[id]||null;
  const heroStep=()=>document.getElementById('step-heroes');
  const grid=()=>document.getElementById('gameHeroGrid');
  const stepVisible=()=>{const s=heroStep();return !!s&&!s.classList.contains('hidden')&&document.visibilityState==='visible'};
  const allCards=()=>[...document.querySelectorAll('#gameHeroGrid .game-hero-card[data-hero-id]')];
  const viewportCards=()=>allCards().filter(card=>{if(card.offsetParent===null)return false;const r=card.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth});
  const shuffle=a=>{a=a.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a};
  const imgFor=card=>card.querySelector('.wfgg-v15-motion-layer > img')||card.querySelector('.hero-card-portrait img');

  function neutralize(card){SYNTH.forEach(cls=>card.classList.remove(cls));card.style.removeProperty('--wfgg-v15-delay')}
  function applyCrop(card){
    const p=window.WfGgHeroPortraitV18?.profileFor?.(card.dataset.heroId);if(!p)return;
    card.style.setProperty('--wfgg-v15-x',p.x);card.style.setProperty('--wfgg-v15-y',p.y);card.style.setProperty('--wfgg-v15-zoom',String(p.zoom));
    card.dataset.wfggV17cCrop=`${p.x},${p.y},${p.zoom}`;
  }
  function toStill(card){
    const a=info(card.dataset.heroId),img=imgFor(card);if(!img)return;
    neutralize(card);card.classList.remove('wfgg-native-gif-active-v17b','wfgg-native-gif-active-v17c','wfgg-native-animated-monica');
    if(a?.still){if(img.getAttribute('src')!==a.still)img.src=a.still;card.classList.add('wfgg-native-gif-capable-v17c');card.classList.remove('wfgg-native-gif-capable-v17b');card.dataset.wfggNativeAnimation='native-gif-ready-v17c';applyCrop(card)}
  }
  function stop({restore=true}={}){generation++;running=false;clearTimeout(timer);timer=0;if(restore){active.forEach(toStill);active=[]}document.documentElement.dataset.wfggV17cPhase='idle';document.documentElement.dataset.wfggV17cActive='0'}
  function preload(url,token){return new Promise(resolve=>{if(!url||token!==generation){resolve(false);return}const img=new Image();let done=false;const finish=ok=>{if(done)return;done=true;resolve(ok)};img.onload=()=>finish(true);img.onerror=()=>finish(false);img.src=url;if(img.complete)finish(true);setTimeout(()=>finish(false),2500)})}

  async function activateNext(token){
    if(token!==generation||!running||!stepVisible())return;
    const candidates=shuffle(viewportCards().filter(card=>info(card.dataset.heroId)));if(!candidates.length){timer=setTimeout(()=>activateNext(token),1200);return}
    const maxActive=innerWidth<=600?3:4,group=candidates.slice(0,Math.min(maxActive,candidates.length));
    document.documentElement.dataset.wfggV17cPhase='preload';const loaded=[];
    for(const card of group){if(token!==generation||!running||!stepVisible())return;const a=info(card.dataset.heroId);if(await preload(a?.src||'',token))loaded.push(card)}
    if(token!==generation||!running||!stepVisible())return;
    active=loaded.filter(card=>card.isConnected&&card.offsetParent!==null);
    for(const card of active){neutralize(card);applyCrop(card);const a=info(card.dataset.heroId),img=imgFor(card);if(a?.src&&img){img.src=a.src;card.classList.add('wfgg-native-gif-active-v17c');card.dataset.wfggNativeAnimation='native-gif-playing-v17c'}}
    document.documentElement.dataset.wfggV17cPhase='active';document.documentElement.dataset.wfggV17cActive=String(active.length);document.documentElement.dataset.wfggV17cBatch=active.map(c=>c.dataset.heroId).join(',');
    timer=setTimeout(()=>{if(token!==generation||!running)return;active.forEach(toStill);active=[];document.documentElement.dataset.wfggV17cPhase='rest';document.documentElement.dataset.wfggV17cActive='0';timer=setTimeout(()=>activateNext(token),REST_MS)},ACTIVE_MS);
  }

  function start(){if(running||!stepVisible())return;running=true;const token=++generation;viewportCards().forEach(card=>{neutralize(card);if(info(card.dataset.heroId))toStill(card)});const launch=()=>{if(token!==generation||!running||!stepVisible())return;activateNext(token)};if('requestIdleCallback' in window)requestIdleCallback(launch,{timeout:START_DELAY_MS+1000});else timer=setTimeout(launch,START_DELAY_MS)}
  function syncVisibility(){if(stepVisible()){if(!running){clearTimeout(timer);timer=setTimeout(start,START_DELAY_MS)}}else stop({restore:true})}
  async function init(){
    try{const r=await fetch(MANIFEST,{cache:'force-cache'});if(r.ok)manifest=await r.json()}catch(_){manifest={animated:{}}}
    const s=heroStep();if(s){stepObserver=new MutationObserver(syncVisibility);stepObserver.observe(s,{attributes:true,attributeFilter:['class']})}
    const g=grid();if(g){gridObserver=new MutationObserver(()=>{if(stepVisible())viewportCards().forEach(card=>{neutralize(card);if(info(card.dataset.heroId)&&!card.classList.contains('wfgg-native-gif-active-v17c'))toStill(card)})});gridObserver.observe(g,{childList:true,subtree:false})}
    document.addEventListener('visibilitychange',syncVisibility,{passive:true});window.addEventListener('pagehide',()=>stop({restore:false}),{once:true});
    window.addEventListener('scroll',()=>{if(!stepVisible()||!running)return;clearTimeout(timer);timer=setTimeout(()=>{if(stepVisible()){active.forEach(toStill);active=[];activateNext(generation)}},450)},{passive:true});
    syncVisibility();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();