(() => {
  'use strict';
  const CATALOG_URL='data/hero-catalog.v2.json';
  const CROP={
    williams:{x:'0%',y:'2%',zoom:.94}, murphy:{x:'1%',y:'-14%',zoom:1.48}, kimberly:{x:'0%',y:'0%',zoom:1.00}, marshall:{x:'0%',y:'0%',zoom:.98},
    stetmann:{x:'0%',y:'-1%',zoom:1.03}, dva:{x:'0%',y:'0%',zoom:1.00}, carlie:{x:'0%',y:'-2%',zoom:1.08}, lucius:{x:'0%',y:'3%',zoom:.90},
    schuyler:{x:'0%',y:'3%',zoom:.92}, morrison:{x:'0%',y:'-11%',zoom:1.40}, tesla:{x:'0%',y:'0%',zoom:1.00}, swift:{x:'0%',y:'4%',zoom:.90},
    fiona:{x:'0%',y:'2%',zoom:.96}, adam:{x:'0%',y:'3%',zoom:.92}, mcgregor:{x:'0%',y:'-1%',zoom:1.05}, monica:{x:'0%',y:'2%',zoom:.96},
    mason:{x:'0%',y:'2%',zoom:.96}, violet:{x:'0%',y:'1%',zoom:.99}, scarlett:{x:'0%',y:'2%',zoom:.96}, richard:{x:'0%',y:'1%',zoom:.99},
    farhad:{x:'0%',y:'-2%',zoom:1.07}, sarah:{x:'0%',y:'-2%',zoom:1.07}, maxwell:{x:'0%',y:'0%',zoom:1.02}, cage:{x:'0%',y:'0%',zoom:1.02},
    venom:{x:'0%',y:'0%',zoom:1.02}, braz:{x:'0%',y:'0%',zoom:1.02}, elsa:{x:'0%',y:'0%',zoom:1.02}, gump:{x:'0%',y:'0%',zoom:1.02},
    loki:{x:'0%',y:'0%',zoom:1.02}, ambolt:{x:'0%',y:'0%',zoom:1.02}, kane:{x:'0%',y:'0%',zoom:1.02}
  };
  const ACTIVE_MS=1600;
  const REST_MS=650;
  const LEGACY=['wfgg-live-card','wfgg-v10-live','wfgg-v12-live','wfgg-v13-live'];
  let catalog=[];
  let queue=[];
  let groups=[];
  let active=[];
  let timer=0;
  let observerQueued=false;

  window.WfGgHeroMotionOwner='v14';
  window.WfGgHeroRosterV14={version:'14.0.0'};
  document.documentElement.dataset.wfggRosterMotion='v14';

  const visibleCards=()=>{
    const grid=document.querySelector('#gameHeroGrid.game-hero-grid:not(.is-selecting)');
    return grid?[...grid.querySelectorAll('.game-hero-card[data-hero-id]')].filter(c=>c.offsetParent!==null):[];
  };
  const byId=id=>catalog.find(h=>h.id===id)||null;
  const isGif=src=>/\.gif(?:$|\?)/i.test(String(src||''))||/giphy/i.test(String(src||''));
  function shuffled(list){const a=list.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a}
  function groupSizes(n){if(n<=0)return[];const count=Math.ceil(n/6),base=Math.floor(n/count),extra=n%count;return Array.from({length:count},(_,i)=>base+(i<extra?1:0))}
  function stripLegacy(root=document){
    root.querySelectorAll?.('.game-hero-card').forEach(card=>LEGACY.forEach(cls=>card.classList.remove(cls)));
  }
  function preferHq(card){
    const cat=byId(card.dataset.heroId),img=card.querySelector('.hero-card-portrait img');
    if(!cat||!img||!cat.portrait||isGif(cat.portrait))return;
    if(img.dataset.wfggV14Hq===cat.portrait)return;
    const fallback=cat.localPortrait||img.getAttribute('src')||'';
    const probe=new Image();probe.referrerPolicy='no-referrer';
    probe.onload=()=>{if(img.isConnected){img.src=cat.portrait;img.dataset.wfggV14Hq=cat.portrait;img.dataset.wfggV14Fallback=fallback}};
    probe.onerror=()=>{img.dataset.wfggV14Hq='failed'};
    probe.src=cat.portrait;
  }
  function decorate(card){
    const id=card.dataset.heroId;if(!id)return;
    const c=CROP[id]||{x:'0%',y:'0%',zoom:1};
    card.style.setProperty('--wfgg-v14-x',c.x);
    card.style.setProperty('--wfgg-v14-y',c.y);
    card.style.setProperty('--wfgg-v14-zoom',String(c.zoom));
    card.dataset.wfggV14Crop=`${c.x},${c.y},${c.zoom}`;
    preferHq(card);
  }
  function decorateAll(){visibleCards().forEach(decorate);stripLegacy()}
  function rebuild(){
    queue=shuffled(visibleCards());groups=groupSizes(queue.length);
    document.documentElement.dataset.wfggV14CycleSize=String(queue.length);
    visibleCards().forEach(c=>delete c.dataset.wfggV14Seen);
  }
  function clearActive(){
    active.forEach(card=>card?.classList.remove('wfgg-v14-live'));
    active=[];
  }
  function rest(){
    clearActive();stripLegacy();
    document.documentElement.dataset.wfggV14Phase='rest';
    clearTimeout(timer);timer=setTimeout(startBatch,REST_MS);
  }
  function startBatch(){
    clearTimeout(timer);stripLegacy();
    if(document.hidden||!visibleCards().length){document.documentElement.dataset.wfggV14Phase='idle';timer=setTimeout(startBatch,800);return}
    if(!groups.length||!queue.length)rebuild();
    const size=groups.shift()||Math.min(6,queue.length);
    active=queue.splice(0,size).filter(c=>c?.isConnected&&c.offsetParent!==null);
    if(!active.length){rebuild();timer=setTimeout(startBatch,100);return}
    document.documentElement.dataset.wfggV14Phase='active';
    document.documentElement.dataset.wfggV14Batch=active.map(c=>c.dataset.heroId).join(',');
    active.forEach((card,i)=>{
      decorate(card);
      card.style.setProperty('--wfgg-v14-delay',`${i*22}ms`);
      card.classList.add('wfgg-v14-live');
      card.dataset.wfggV14Seen='1';
    });
    timer=setTimeout(rest,ACTIVE_MS);
  }
  function queueDecorate(){if(observerQueued)return;observerQueued=true;requestAnimationFrame(()=>{observerQueued=false;decorateAll()})}
  async function init(){
    try{const r=await fetch(CATALOG_URL,{cache:'no-store'});if(r.ok)catalog=(await r.json()).heroes||[]}catch(_){}
    decorateAll();rebuild();
    const mo=new MutationObserver(muts=>{
      let refresh=false;
      for(const m of muts){
        if(m.type==='attributes'&&m.target?.classList?.contains('game-hero-card')){
          if(LEGACY.some(cls=>m.target.classList.contains(cls)))LEGACY.forEach(cls=>m.target.classList.remove(cls));
        }
        if(m.type==='childList')refresh=true;
      }
      if(refresh)queueDecorate();
    });
    mo.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
    document.addEventListener('visibilitychange',()=>{if(!document.hidden){clearActive();rebuild();clearTimeout(timer);timer=setTimeout(startBatch,250)}});
    timer=setTimeout(startBatch,350);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
