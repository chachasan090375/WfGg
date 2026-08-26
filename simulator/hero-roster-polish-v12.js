(() => {
  'use strict';
  const CATALOG_URL='data/hero-catalog.v2.json';
  const PROFILE_KEY='wfgg-simulator-profile-v1';
  const NAMES={
    fr:{schuyler:'Skyler'},
    en:{schuyler:'Schuyler'},
    it:{schuyler:'Schuyler'},
    es:{schuyler:'Schuyler'}
  };
  const CROP={
    murphy:{y:'-8%',zoom:1.18},williams:{y:'-2%',zoom:1.08},kimberly:{y:'-2%',zoom:1.08},marshall:{y:'-2%',zoom:1.07},stetmann:{y:'-2%',zoom:1.07},
    dva:{y:'-2%',zoom:1.07},carlie:{y:'-2%',zoom:1.07},lucius:{y:'-2%',zoom:1.07},schuyler:{y:'-2%',zoom:1.07},morrison:{y:'-2%',zoom:1.07},
    tesla:{y:'-1%',zoom:1.04},swift:{y:'-2%',zoom:1.07},fiona:{y:'-2%',zoom:1.07},adam:{y:'-1%',zoom:1.04},mcgregor:{y:'-2%',zoom:1.07},
    monica:{y:'-3%',zoom:1.09},mason:{y:'-2%',zoom:1.07},violet:{y:'-2%',zoom:1.07},scarlett:{y:'-2%',zoom:1.07},richard:{y:'-2%',zoom:1.07},farhad:{y:'-2%',zoom:1.07},
    sarah:{y:'-3%',zoom:1.09},maxwell:{y:'-2%',zoom:1.07},cage:{y:'-2%',zoom:1.07},venom:{y:'-2%',zoom:1.07},braz:{y:'-2%',zoom:1.07},elsa:{y:'-2%',zoom:1.07},
    gump:{y:'-2%',zoom:1.07},loki:{y:'-2%',zoom:1.07},ambolt:{y:'-2%',zoom:1.07},kane:{y:'-2%',zoom:1.07}
  };
  const HQ_REMOTE=new Set(['tesla','adam']);
  let catalog=[];
  let timer=null;
  let active=[];
  let last=new Set();
  let scanQueued=false;

  const norm=v=>String(v||'').trim().toLowerCase();
  const locale=()=>document.documentElement.lang||'fr';
  const profile=()=>{try{return window.WfGgProfilePersistence?.profile?.()||JSON.parse(localStorage.getItem(PROFILE_KEY)||'{}')||{}}catch{return {}}};
  const byId=id=>catalog.find(h=>h.id===id)||null;
  const owned=name=>(profile().heroes||[]).find(h=>norm(h.heroId)===norm(name))||null;
  const displayName=cat=>(NAMES[locale()]||NAMES.en)[cat.id]||cat.name;
  const isGif=cat=>/\.gif(?:$|\?)/i.test(cat?.portrait||'')||/giphy/i.test(cat?.portrait||'');

  function setSourceSafely(img,src,fallback){
    if(!src||img.dataset.wfggHqProbing===src||img.src===src)return;
    img.dataset.wfggHqProbing=src;
    const probe=new Image();
    probe.referrerPolicy='no-referrer';
    probe.onload=()=>{if(img.isConnected){img.dataset.wfggStaticSrc=fallback||img.currentSrc||img.src;img.src=src;img.dataset.wfggHq='1'}delete img.dataset.wfggHqProbing};
    probe.onerror=()=>{delete img.dataset.wfggHqProbing};
    probe.src=src;
  }
  function decorateCard(card){
    const cat=byId(card.dataset.heroId);if(!cat)return;
    const crop=CROP[cat.id]||{y:'-2%',zoom:1.07};
    card.style.setProperty('--wfgg-v12-base-y',crop.y);
    card.style.setProperty('--wfgg-v12-zoom',String(crop.zoom));
    card.dataset.wfggDisplayName=displayName(cat);
    const name=card.querySelector('.wfgg-v10-name');if(name)name.textContent=displayName(cat);
    const img=card.querySelector('.hero-card-portrait img');
    if(img){
      img.alt=displayName(cat);
      if(!img.dataset.wfggLocalSrc)img.dataset.wfggLocalSrc=cat.localPortrait||img.getAttribute('src')||'';
      if(HQ_REMOTE.has(cat.id)&&cat.portrait&&!isGif(cat))setSourceSafely(img,cat.portrait,img.dataset.wfggLocalSrc);
    }
  }
  function decorate(){document.querySelectorAll('.game-hero-card[data-hero-id]').forEach(decorateCard)}
  function clearActive(){
    active.forEach(card=>{
      if(!card?.isConnected)return;
      card.classList.remove('wfgg-v12-live');
      const cat=byId(card.dataset.heroId),img=card.querySelector('.hero-card-portrait img');
      if(img&&cat&&isGif(cat)&&img.dataset.wfggBeforeGif){img.src=img.dataset.wfggBeforeGif;delete img.dataset.wfggBeforeGif;delete img.dataset.wfggGifLive}
    });active=[];
  }
  function shuffled(a){a=a.slice();for(let i=a.length-1;i;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a}
  function animateBatch(){
    clearTimeout(timer);clearActive();
    const grid=document.querySelector('.game-hero-grid:not(.is-selecting)');
    const cards=grid?[...grid.querySelectorAll('.game-hero-card[data-hero-id]')].filter(x=>x.offsetParent!==null):[];
    if(document.hidden||!cards.length){timer=setTimeout(animateBatch,1100);return}
    const count=Math.min(cards.length,5+Math.floor(Math.random()*2));
    let pool=cards.filter(c=>!last.has(c.dataset.heroId));if(pool.length<count)pool=cards;
    active=shuffled(pool).slice(0,count);last=new Set(active.map(c=>c.dataset.heroId));
    active.forEach((card,i)=>{
      card.style.setProperty('--wfgg-v12-delay',`${i*34+Math.floor(Math.random()*70)}ms`);
      card.style.setProperty('--wfgg-v12-duration',`${(1.55+Math.random()*.35).toFixed(2)}s`);
      card.classList.add('wfgg-v12-live');
      const cat=byId(card.dataset.heroId),img=card.querySelector('.hero-card-portrait img');
      if(cat&&img&&isGif(cat)&&cat.portrait){
        img.dataset.wfggBeforeGif=img.currentSrc||img.src;
        const probe=new Image();probe.referrerPolicy='no-referrer';
        probe.onload=()=>{if(card.classList.contains('wfgg-v12-live')&&img.isConnected){img.src=cat.portrait;img.dataset.wfggGifLive='1'}};
        probe.src=cat.portrait;
      }
    });
    setTimeout(clearActive,2050);
    timer=setTimeout(animateBatch,2700+Math.floor(Math.random()*650));
  }
  function queue(){if(scanQueued)return;scanQueued=true;requestAnimationFrame(()=>{scanQueued=false;decorate()})}
  async function init(){
    try{const r=await fetch(CATALOG_URL,{cache:'no-store'});if(r.ok)catalog=(await r.json()).heroes||[]}catch(e){console.error('WfGg roster v12 catalog',e)}
    decorate();
    new MutationObserver(queue).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class','lang']});
    document.querySelector('#languageStrip')?.addEventListener('click',()=>setTimeout(decorate,40));
    timer=setTimeout(animateBatch,700);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
  window.WfGgHeroRosterV12=Object.freeze({version:'12.0.0',refresh:queue,localizedName:(id,lang)=>((NAMES[lang]||NAMES.en)[id]||byId(id)?.name||id)});
})();
