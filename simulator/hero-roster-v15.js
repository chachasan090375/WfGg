(() => {
  'use strict';

  const CATALOG_URL='data/hero-catalog.v2.json';
  const ACTIVE_MS=2200;
  const REST_MS=780;
  const LEGACY=['wfgg-live-card','wfgg-v10-live','wfgg-v12-live','wfgg-v13-live','wfgg-v14-live'];

  const CROP={
    williams:{x:'0%',y:'2%',zoom:.94}, murphy:{x:'1%',y:'-20%',zoom:1.55}, kimberly:{x:'0%',y:'4%',zoom:.98}, marshall:{x:'0%',y:'2%',zoom:.98},
    stetmann:{x:'0%',y:'1%',zoom:1.02}, dva:{x:'0%',y:'2%',zoom:.99}, carlie:{x:'0%',y:'3%',zoom:1.04}, lucius:{x:'0%',y:'-1%',zoom:.96},
    schuyler:{x:'0%',y:'5%',zoom:.94}, morrison:{x:'0%',y:'-14%',zoom:1.42}, tesla:{x:'0%',y:'4%',zoom:.98}, swift:{x:'0%',y:'2%',zoom:.94},
    fiona:{x:'0%',y:'5%',zoom:.96}, adam:{x:'0%',y:'-5%',zoom:1.00}, mcgregor:{x:'0%',y:'0%',zoom:1.04}, monica:{x:'0%',y:'5%',zoom:.96},
    mason:{x:'0%',y:'3%',zoom:.97}, violet:{x:'0%',y:'3%',zoom:.99}, scarlett:{x:'0%',y:'4%',zoom:.96}, richard:{x:'0%',y:'2%',zoom:.99},
    farhad:{x:'0%',y:'0%',zoom:1.04}, sarah:{x:'0%',y:'1%',zoom:1.04}, maxwell:{x:'0%',y:'2%',zoom:1.00}, cage:{x:'0%',y:'2%',zoom:1.00},
    venom:{x:'0%',y:'2%',zoom:1.00}, braz:{x:'0%',y:'2%',zoom:1.00}, elsa:{x:'0%',y:'2%',zoom:1.00}, gump:{x:'0%',y:'2%',zoom:1.00},
    loki:{x:'0%',y:'2%',zoom:1.00}, ambolt:{x:'0%',y:'2%',zoom:1.00}, kane:{x:'0%',y:'2%',zoom:1.00}
  };

  const ICON={
    tank:'assets/icons/lastwar/Tank.png',
    aircraft:'assets/icons/lastwar/Aircraft.png',
    missile:'assets/icons/lastwar/Missile.png',
    attack:'assets/icons/lastwar/Attack.png',
    defense:'assets/icons/lastwar/Defense.png',
    support:'assets/icons/lastwar/Support.png'
  };
  const LABEL={
    fr:{tank:'Tank',aircraft:'Avion',missile:'Véhicule Missile',attack:'Attaque',defense:'Défense',support:'Soutien'},
    en:{tank:'Tank',aircraft:'Aircraft',missile:'Missile',attack:'Attack',defense:'Defense',support:'Support'},
    it:{tank:'Tank',aircraft:'Aereo',missile:'Veicolo Missile',attack:'Attacco',defense:'Difesa',support:'Supporto'},
    es:{tank:'Tank',aircraft:'Avión',missile:'Vehículo de misiles',attack:'Ataque',defense:'Defensa',support:'Apoyo'}
  };

  let catalog=[];
  let queue=[];
  let groups=[];
  let active=[];
  let timer=0;
  let scanQueued=false;

  window.WfGgHeroMotionOwner='v15';
  window.WfGgHeroRosterV15={version:'15.1.0'};
  document.documentElement.dataset.wfggRosterMotion='v15';

  const norm=v=>String(v||'').trim().toLowerCase();
  const lang=()=>document.documentElement.lang||'fr';
  const label=k=>(LABEL[lang()]||LABEL.fr)[k]||k;
  const visibleCards=()=>{
    const grid=document.querySelector('#gameHeroGrid.game-hero-grid:not(.is-selecting)');
    return grid?[...grid.querySelectorAll('.game-hero-card[data-hero-id]')].filter(c=>c.offsetParent!==null):[];
  };
  const byId=id=>catalog.find(h=>h.id===id)||null;
  function byDisplayName(name){const n=norm(name);if(n==='skyler')return byId('schuyler');return catalog.find(h=>norm(h.name)===n)||null}
  function shuffled(list){const a=list.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a}
  function groupSizes(n){if(!n)return[];const count=Math.ceil(n/6),base=Math.floor(n/count),extra=n%count;return Array.from({length:count},(_,i)=>base+(i<extra?1:0))}
  function icon(kind){return `<span class="wfgg-v15-semantic-icon" title="${label(kind)}" aria-label="${label(kind)}"><img src="${ICON[kind]}" alt="" aria-hidden="true"><span class="wfgg-v15-sr-only">${label(kind)}</span></span>`}
  function stripLegacy(root=document){root.querySelectorAll?.('.game-hero-card').forEach(c=>LEGACY.forEach(k=>c.classList.remove(k)))}

  function decorateCard(card){
    const id=card.dataset.heroId;if(!id)return;
    const cat=byId(id);if(!cat)return;
    const c=CROP[id]||{x:'0%',y:'2%',zoom:1};
    card.style.setProperty('--wfgg-v15-x',c.x);
    card.style.setProperty('--wfgg-v15-y',c.y);
    card.style.setProperty('--wfgg-v15-zoom',String(c.zoom));
    card.dataset.wfggV15Crop=`${c.x},${c.y},${c.zoom}`;
    card.dataset.wfggV15Rarity=card.classList.contains('rarity-SSR')?'SSR':card.classList.contains('rarity-SR')?'SR':'UR';
    let layer=card.querySelector(':scope > .wfgg-v15-card-semantics');
    if(!layer){layer=document.createElement('div');layer.className='wfgg-v15-card-semantics';layer.setAttribute('aria-label',`${label(cat.troopType)}, ${label(cat.role)}`);card.appendChild(layer)}
    const signature=`${cat.troopType}|${cat.role}|${lang()}`;
    if(layer.dataset.signature!==signature){layer.innerHTML=`${icon(cat.troopType)}${icon(cat.role)}`;layer.dataset.signature=signature}
  }
  function decorateSheet(){
    const sheet=document.querySelector('#heroGameSheet.open');if(!sheet)return;
    const cat=byDisplayName(sheet.querySelector('.hero-sheet-title h3')?.textContent||'');if(!cat)return;
    const title=sheet.querySelector('.hero-sheet-title');if(!title)return;
    let layer=title.querySelector(':scope > .wfgg-v15-sheet-semantics');
    if(!layer){layer=document.createElement('div');layer.className='wfgg-v15-sheet-semantics';title.appendChild(layer)}
    const signature=`${cat.troopType}|${cat.role}|${lang()}`;
    if(layer.dataset.signature!==signature){layer.innerHTML=`${icon(cat.troopType)}${icon(cat.role)}`;layer.dataset.signature=signature}
  }
  function decorateAll(){visibleCards().forEach(decorateCard);decorateSheet();stripLegacy()}

  function rebuild(){queue=shuffled(visibleCards());groups=groupSizes(queue.length);visibleCards().forEach(c=>delete c.dataset.wfggV15Seen);document.documentElement.dataset.wfggV15CycleSize=String(queue.length)}
  function clearActive(){active.forEach(c=>c?.classList.remove('wfgg-v15-live'));active=[]}
  function rest(){clearActive();stripLegacy();document.documentElement.dataset.wfggV15Phase='rest';clearTimeout(timer);timer=setTimeout(startBatch,REST_MS)}
  function startBatch(){
    clearTimeout(timer);stripLegacy();
    if(window.WfGgHeroMotionOwner!=='v15')return;
    if(document.hidden||!visibleCards().length){document.documentElement.dataset.wfggV15Phase='idle';timer=setTimeout(startBatch,700);return}
    if(!groups.length||!queue.length)rebuild();
    const size=groups.shift()||Math.min(6,queue.length);
    active=queue.splice(0,size).filter(c=>c?.isConnected&&c.offsetParent!==null);
    if(!active.length){rebuild();timer=setTimeout(startBatch,100);return}
    document.documentElement.dataset.wfggV15Phase='active';document.documentElement.dataset.wfggV15Batch=active.map(c=>c.dataset.heroId).join(',');
    active.forEach((card,i)=>{decorateCard(card);card.style.setProperty('--wfgg-v15-delay',`${i*32}ms`);card.classList.add('wfgg-v15-live');card.dataset.wfggV15Seen='1'});
    timer=setTimeout(rest,ACTIVE_MS);
  }
  function queueScan(){if(scanQueued)return;scanQueued=true;requestAnimationFrame(()=>{scanQueued=false;decorateAll()})}

  async function init(){
    try{const r=await fetch(CATALOG_URL,{cache:'no-store'});if(r.ok)catalog=(await r.json()).heroes||[]}catch(_){}
    decorateAll();rebuild();
    const mo=new MutationObserver(muts=>{let rescan=false;for(const m of muts){if(m.type==='attributes'&&m.target?.classList?.contains('game-hero-card')&&LEGACY.some(k=>m.target.classList.contains(k)))LEGACY.forEach(k=>m.target.classList.remove(k));if(m.type==='childList')rescan=true}if(rescan)queueScan()});
    mo.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
    document.addEventListener('visibilitychange',()=>{if(!document.hidden){clearActive();rebuild();clearTimeout(timer);timer=setTimeout(startBatch,250)}});
    timer=setTimeout(startBatch,450);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
