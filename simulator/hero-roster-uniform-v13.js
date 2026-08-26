(() => {
  'use strict';
  const CATALOG_URL='data/hero-catalog.v2.json';
  const CROP={
    williams:{x:'0%',y:'-3%',zoom:1.10},murphy:{x:'1%',y:'-13%',zoom:1.30},kimberly:{x:'0%',y:'-3%',zoom:1.08},marshall:{x:'0%',y:'-1%',zoom:1.04},
    stetmann:{x:'0%',y:'-1%',zoom:1.04},dva:{x:'0%',y:'-3%',zoom:1.08},carlie:{x:'0%',y:'-3%',zoom:1.10},lucius:{x:'0%',y:'1%',zoom:.95},
    schuyler:{x:'0%',y:'1%',zoom:.96},morrison:{x:'0%',y:'-5%',zoom:1.12},tesla:{x:'0%',y:'-2%',zoom:1.06},swift:{x:'0%',y:'0%',zoom:1.00},
    fiona:{x:'0%',y:'0%',zoom:1.00},adam:{x:'0%',y:'-2%',zoom:1.06},mcgregor:{x:'0%',y:'-2%',zoom:1.06},monica:{x:'0%',y:'0%',zoom:1.00},
    mason:{x:'0%',y:'-2%',zoom:1.05},violet:{x:'0%',y:'0%',zoom:1.00},scarlett:{x:'0%',y:'1%',zoom:.98},richard:{x:'0%',y:'-1%',zoom:1.03},
    farhad:{x:'0%',y:'-2%',zoom:1.06},sarah:{x:'0%',y:'-2%',zoom:1.06},maxwell:{x:'0%',y:'-2%',zoom:1.06},cage:{x:'0%',y:'-2%',zoom:1.06},
    venom:{x:'0%',y:'-2%',zoom:1.06},braz:{x:'0%',y:'-2%',zoom:1.06},elsa:{x:'0%',y:'-2%',zoom:1.06},gump:{x:'0%',y:'-2%',zoom:1.06},
    loki:{x:'0%',y:'-2%',zoom:1.06},ambolt:{x:'0%',y:'-2%',zoom:1.06},kane:{x:'0%',y:'-2%',zoom:1.06}
  };
  const ACTIVE_MS=1480;
  const REST_MS=520;
  let catalog=[];
  let cycle=[];
  let groups=[];
  let active=[];
  let timer=0;
  let scanQueued=false;

  // Used by the test harness and also by older motion layers to know V13 owns roster motion.
  window.WfGgHeroRosterV13={version:'13.0.0'};
  document.documentElement.dataset.wfggRosterMotion='v13';

  const visibleCards=()=>{
    const grid=document.querySelector('.game-hero-grid:not(.is-selecting)');
    return grid?[...grid.querySelectorAll('.game-hero-card[data-hero-id]')].filter(c=>c.offsetParent!==null):[];
  };
  function shuffled(list){const a=list.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a}
  function groupSizes(n){
    if(n<=0)return[];
    if(n<=6)return[n];
    const groups=Math.ceil(n/6),base=Math.floor(n/groups),extra=n%groups;
    return Array.from({length:groups},(_,i)=>base+(i<extra?1:0));
  }
  function rebuildCycle(){
    cycle=shuffled(visibleCards());
    groups=groupSizes(cycle.length);
    document.documentElement.dataset.wfggV13CycleSize=String(cycle.length);
  }
  function suppressLegacyMotion(root=document){
    root.querySelectorAll?.('.game-hero-card.wfgg-v10-live,.game-hero-card.wfgg-v12-live').forEach(card=>{
      card.classList.remove('wfgg-v10-live','wfgg-v12-live');
    });
  }
  function decorate(card){
    const id=card.dataset.heroId;if(!id)return;
    const c=CROP[id]||{x:'0%',y:'-2%',zoom:1.05};
    card.style.setProperty('--wfgg-v13-x',c.x);
    card.style.setProperty('--wfgg-v13-y',c.y);
    card.style.setProperty('--wfgg-v13-zoom',String(c.zoom));
    card.dataset.wfggV13Crop=`${c.x},${c.y},${c.zoom}`;
  }
  function decorateAll(){visibleCards().forEach(decorate);suppressLegacyMotion()}
  function endBatch(){
    active.forEach(card=>card?.classList.remove('wfgg-v13-live'));
    active=[];
    document.documentElement.dataset.wfggV13Phase='rest';
    clearTimeout(timer);
    timer=setTimeout(startBatch,REST_MS);
  }
  function startBatch(){
    clearTimeout(timer);
    suppressLegacyMotion();
    if(document.hidden||!visibleCards().length){document.documentElement.dataset.wfggV13Phase='idle';timer=setTimeout(startBatch,900);return}
    if(!groups.length||!cycle.length)rebuildCycle();
    const size=groups.shift()||Math.min(6,cycle.length);
    active=cycle.splice(0,size).filter(card=>card?.isConnected);
    if(!active.length){rebuildCycle();timer=setTimeout(startBatch,100);return}
    document.documentElement.dataset.wfggV13Phase='active';
    document.documentElement.dataset.wfggV13Batch=active.map(c=>c.dataset.heroId).join(',');
    active.forEach((card,i)=>{
      decorate(card);
      card.style.setProperty('--wfgg-v13-delay',`${i*24}ms`);
      card.classList.add('wfgg-v13-live');
      card.dataset.wfggV13Seen='1';
    });
    timer=setTimeout(endBatch,ACTIVE_MS);
  }
  function queueScan(){
    if(scanQueued)return;scanQueued=true;
    requestAnimationFrame(()=>{scanQueued=false;decorateAll()});
  }
  async function init(){
    try{const r=await fetch(CATALOG_URL,{cache:'no-store'});if(r.ok)catalog=(await r.json()).heroes||[]}catch(_){}
    decorateAll();rebuildCycle();
    const mo=new MutationObserver(muts=>{
      let need=false;
      for(const m of muts){
        if(m.type==='attributes'&&m.target?.classList?.contains('game-hero-card')){
          if(m.target.classList.contains('wfgg-v10-live')||m.target.classList.contains('wfgg-v12-live'))suppressLegacyMotion(m.target.parentElement||document);
        }
        if(m.type==='childList')need=true;
      }
      if(need)queueScan();
    });
    mo.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
    document.addEventListener('visibilitychange',()=>{if(!document.hidden){rebuildCycle();clearTimeout(timer);timer=setTimeout(startBatch,250)}});
    timer=setTimeout(startBatch,420);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
