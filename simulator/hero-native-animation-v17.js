(() => {
  'use strict';
  const MANIFEST='data/hero-native-animations.v17.json';
  const CATALOG='data/hero-catalog.v2.json';
  const SYNTH=['wfgg-live-card','wfgg-v10-live','wfgg-v12-live','wfgg-v13-live','wfgg-v14-live','wfgg-v15-live'];
  const CROP={monica:{x:'0%',y:'-7%',zoom:1.02},murphy:{x:'1%',y:'-20%',zoom:1.55},schuyler:{x:'0%',y:'5%',zoom:.94},sarah:{x:'0%',y:'1%',zoom:1.04},gump:{x:'0%',y:'2%',zoom:1.00}};
  let manifest={animated:{}}; let catalog=[]; let queued=false;
  window.WfGgHeroMotionOwner='native-v17';
  window.WfGgHeroNativeAnimationV17={version:'17.0.0'};
  document.documentElement.dataset.wfggRosterMotion='native-gif-only-v17';
  const byId=id=>catalog.find(h=>h.id===id)||null;
  function neutralize(card){SYNTH.forEach(c=>card.classList.remove(c));card.style.removeProperty('--wfgg-v15-delay')}
  function apply(card){
    const id=card.dataset.heroId;if(!id)return;
    neutralize(card);
    const cat=byId(id); const anim=manifest.animated?.[id];
    const layer=card.querySelector('.wfgg-v15-motion-layer')||card.querySelector('.hero-card-portrait');
    const img=layer?.querySelector('img')||card.querySelector('.hero-card-portrait img'); if(!img)return;
    if(id==='loki'){
      img.src='assets/heroes/loki.webp';
      img.dataset.wfggStaticSrc='assets/heroes/loki.webp';
      card.dataset.wfggLokiPortrait='restored-v17';
    } else if(cat?.localPortrait && !img.dataset.wfggStaticSrc){img.dataset.wfggStaticSrc=cat.localPortrait}
    if(anim?.src){
      if(img.getAttribute('src')!==anim.src)img.src=anim.src;
      card.classList.add('wfgg-native-animated','wfgg-native-gif-v17');
      card.dataset.wfggNativeAnimation=`gif-v17:${id}`;
      const c=CROP[id];if(c){card.style.setProperty('--wfgg-v15-x',c.x);card.style.setProperty('--wfgg-v15-y',c.y);card.style.setProperty('--wfgg-v15-zoom',String(c.zoom));card.dataset.wfggV17Crop=`${c.x},${c.y},${c.zoom}`}
    }else{
      card.classList.remove('wfgg-native-animated','wfgg-native-gif-v17','wfgg-native-animated-monica');
      card.dataset.wfggNativeAnimation='static-v17';
      const fallback=id==='loki'?'assets/heroes/loki.webp':(cat?.localPortrait||img.dataset.wfggStaticSrc||cat?.portrait||'');
      if(fallback&&img.getAttribute('src')!==fallback)img.src=fallback;
    }
  }
  function applyAll(){document.querySelectorAll('#gameHeroGrid .game-hero-card[data-hero-id]').forEach(apply)}
  function queue(){if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;applyAll()})}
  async function init(){
    try{const [m,c]=await Promise.all([fetch(MANIFEST,{cache:'no-store'}),fetch(CATALOG,{cache:'no-store'})]);if(m.ok)manifest=await m.json();if(c.ok)catalog=(await c.json()).heroes||[]}catch(_){}
    applyAll();
    const mo=new MutationObserver(ms=>{for(const m of ms){if(m.type==='attributes'&&m.target?.matches?.('.game-hero-card'))neutralize(m.target)}queue()});
    mo.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class']});
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)queue()});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
