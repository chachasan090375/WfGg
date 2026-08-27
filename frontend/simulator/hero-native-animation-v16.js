(() => {
  'use strict';

  const MONICA_GIF='assets/heroes/animated/monica.gif';
  let queued=false;

  window.WfGgHeroNativeAnimationV16={version:'16.0.0',monica:MONICA_GIF};

  function applyMonica(){
    const card=document.querySelector('#gameHeroGrid .game-hero-card[data-hero-id="monica"]');
    if(!card)return false;
    const img=card.querySelector('.wfgg-v15-motion-layer > img')||card.querySelector('.hero-card-portrait img');
    if(!img)return false;

    card.classList.add('wfgg-native-animated','wfgg-native-animated-monica');
    card.dataset.wfggNativeAnimation='monica-original-gif';
    img.classList.add('wfgg-native-animated-image');

    if(!img.dataset.wfggStaticSrc)img.dataset.wfggStaticSrc=img.getAttribute('src')||'';
    const current=img.getAttribute('src')||'';
    if(!current.includes('/animated/monica.gif')&&!current.endsWith('animated/monica.gif')){
      img.src=MONICA_GIF;
    }
    if(!img.dataset.wfggNativeErrorBound){
      img.dataset.wfggNativeErrorBound='1';
      img.addEventListener('error',()=>{
        const fallback=img.dataset.wfggStaticSrc;
        if(fallback&&img.getAttribute('src')!==fallback){
          card.classList.remove('wfgg-native-animated','wfgg-native-animated-monica');
          card.dataset.wfggNativeAnimation='fallback-static';
          img.src=fallback;
        }
      });
    }
    return true;
  }

  function queueApply(){
    if(queued)return;
    queued=true;
    requestAnimationFrame(()=>{queued=false;applyMonica()});
  }

  function init(){
    applyMonica();
    const mo=new MutationObserver(mutations=>{
      if(mutations.some(m=>m.type==='childList'))queueApply();
    });
    mo.observe(document.body,{childList:true,subtree:true});
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)queueApply()});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
