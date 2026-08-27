(() => {
  'use strict';
  const PROFILE_KEY='wfgg-simulator-profile-v1';
  const CATALOG_URL='data/hero-catalog.v2.json';
  const AWAKENING_S6=new Set(['kimberly','dva','tesla']);
  const ROLE_FR={attack:'ATK',defense:'DEF',support:'SUP'};
  const ROLE_LONG_FR={attack:'Attaque',defense:'Défense',support:'Soutien'};
  const TYPE_FR={tank:'Tank',aircraft:'Avion',missile:'Missile'};
  const PORTRAIT_Y={
    williams:'4%',murphy:'0%',kimberly:'2%',marshall:'0%',stetmann:'0%',dva:'0%',carlie:'0%',lucius:'0%',schuyler:'0%',morrison:'0%',tesla:'0%',swift:'0%',fiona:'0%',adam:'0%',mcgregor:'0%',monica:'0%',mason:'0%',violet:'0%',scarlett:'0%',richard:'0%',farhad:'0%',sarah:'0%',maxwell:'0%',cage:'0%',venom:'0%',braz:'0%',elsa:'0%',gump:'0%',loki:'0%',ambolt:'0%',kane:'0%'
  };
  let catalog=[];
  let liveTimer=null;
  let liveCards=[];
  let lastIds=new Set();
  let scanQueued=false;

  const norm=v=>String(v||'').trim().toLowerCase();
  const esc=v=>String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
  const profile=()=>{try{return window.WfGgProfilePersistence?.profile?.()||JSON.parse(localStorage.getItem(PROFILE_KEY)||'{}')||{}}catch{return {}}};
  const catById=id=>catalog.find(h=>h.id===id)||null;
  const ownedByName=name=>(profile().heroes||[]).find(h=>norm(h.heroId)===norm(name))||null;

  function troopSvg(type){
    if(type==='aircraft')return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M28 15.2 18.8 11l-3.6-8H12l1.4 8.5-6.7 2.1-3.2-2.2H1.2l2 4.6-2 4.6h2.3l3.2-2.2 6.7 2.1L12 29h3.2l3.6-8 9.2-4.2z"/></svg>';
    if(type==='missile')return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M4 20h17l6-5-6-5H4l4 5-4 5zm0 3h18v4H4zm2-18h16v3H6z"/></svg>';
    return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M6 10h17l4 5v8H5v-9l1-4zm4-5h9l2 4H9l1-4zM8 24a3 3 0 1 0 0 6 3 3 0 0 0 0-6zm15 0a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"/></svg>';
  }
  function starText(v){const n=Number(v)||0;return n>0?`★${n.toFixed(n%1?1:0)}`:''}
  function rarityOf(cat,owned){return owned?.rarity||cat?.rarity||'R'}
  function promoText(cat){
    if(!cat)return'';
    if(AWAKENING_S6.has(cat.id))return 'S6 · ✦ Éveil';
    if(cat.promotableTo&&cat.promotionSeason)return `S${cat.promotionSeason} · ${cat.rarity}→${cat.promotableTo}`;
    return'';
  }
  function roleTitle(role){return ROLE_LONG_FR[role]||role||''}

  function decorateCard(card){
    const id=card.dataset.heroId;if(!id)return;
    const cat=catById(id);if(!cat)return;
    const own=ownedByName(cat.name);const rarity=rarityOf(cat,own);
    card.style.setProperty('--wfgg-portrait-y',PORTRAIT_Y[id]||'0%');
    card.dataset.wfggRole=cat.role||'';card.dataset.wfggType=cat.troopType||'';card.dataset.wfggRarity=rarity;
    const footer=card.querySelector('.hero-card-footer');if(!footer)return;
    const level=own?.level||'';const stars=starText(own?.stars);const promo=promoText(cat);
    footer.innerHTML=`<div class="wfgg-v10-footer"><strong class="wfgg-v10-name">${esc(cat.name)}</strong><div class="wfgg-v10-meta"><span class="wfgg-v10-pill rarity-${esc(rarity)}">${esc(rarity)}</span>${level?`<span class="wfgg-v10-pill wfgg-v10-level">Lv.${esc(level)}</span>`:''}${stars?`<span class="wfgg-v10-pill">${esc(stars)}</span>`:''}</div><div class="wfgg-v10-flags"><span class="wfgg-v10-pill wfgg-v10-type" title="${esc(TYPE_FR[cat.troopType]||cat.troopType)}">${troopSvg(cat.troopType)}${esc(TYPE_FR[cat.troopType]||cat.troopType)}</span><span class="wfgg-v10-pill wfgg-v10-role" title="${esc(roleTitle(cat.role))}">${esc(ROLE_FR[cat.role]||cat.role||'')}</span>${promo?`<span class="wfgg-v10-pill ${AWAKENING_S6.has(cat.id)?'wfgg-v10-awaken':'wfgg-v10-promo'}">${esc(promo)}</span>`:''}</div></div>`;
  }

  function decorateCards(){document.querySelectorAll('.game-hero-card[data-hero-id]').forEach(decorateCard)}

  function clearLive(){liveCards.forEach(card=>{if(card?.isConnected){card.classList.remove('wfgg-v10-live');card.style.removeProperty('--wfgg-v10-delay');card.style.removeProperty('--wfgg-v10-duration')}});liveCards=[]}
  function shuffled(list){const a=list.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a}
  function nextLiveBatch(){
    clearTimeout(liveTimer);clearLive();
    const grid=document.querySelector('.game-hero-grid:not(.is-selecting)');
    const cards=grid?[...grid.querySelectorAll('.game-hero-card[data-hero-id]')].filter(c=>c.offsetParent!==null):[];
    if(!cards.length||document.hidden){liveTimer=setTimeout(nextLiveBatch,1000);return}
    const count=Math.min(cards.length,5+Math.floor(Math.random()*2));
    let pool=cards.filter(c=>!lastIds.has(c.dataset.heroId));if(pool.length<count)pool=cards;
    liveCards=shuffled(pool).slice(0,count);lastIds=new Set(liveCards.map(c=>c.dataset.heroId));
    liveCards.forEach(card=>{card.style.setProperty('--wfgg-v10-delay',`${Math.floor(Math.random()*140)}ms`);card.style.setProperty('--wfgg-v10-duration',`${(1.4+Math.random()*.35).toFixed(2)}s`);card.classList.add('wfgg-v10-live')});
    setTimeout(clearLive,1850);liveTimer=setTimeout(nextLiveBatch,2200+Math.floor(Math.random()*420));
  }
  function startLive(){if(liveTimer)return;liveTimer=setTimeout(nextLiveBatch,500)}

  function localizeTabs(sheet){
    if(document.documentElement.lang!=='fr')return;
    const labels={attributes:'Attributs',grade:'Compétences',wall:'Grade',weapon:'Armes exclusives'};
    sheet.querySelectorAll('[data-sheet-tab]').forEach(btn=>{const id=btn.dataset.sheetTab;const span=btn.querySelector('span');if(span&&labels[id])span.textContent=labels[id];btn.setAttribute('aria-label',labels[id]||id)});
  }
  function compactSheet(){
    const sheet=document.querySelector('#heroGameSheet');if(!sheet)return;
    sheet.classList.add('wfgg-v10-sheet');localizeTabs(sheet);
    const name=sheet.querySelector('.hero-sheet-title h3')?.textContent?.trim();if(!name)return;
    const cat=catalog.find(h=>norm(h.name)===norm(name));if(!cat)return;
    const tags=sheet.querySelector('.hero-sheet-tags');
    if(tags){
      tags.innerHTML=`<span class="hero-sheet-tag">${troopSvg(cat.troopType)} ${esc(TYPE_FR[cat.troopType]||cat.troopType)}</span><span class="hero-sheet-tag">${esc(roleTitle(cat.role))}</span><span class="hero-sheet-tag rarity-tag">${esc(rarityOf(cat,ownedByName(cat.name)))}</span>${promoText(cat)?`<span class="hero-sheet-tag awakening-tag">${esc(promoText(cat))}</span>`:''}`;
    }
    const adv=sheet.querySelector('.hero-advanced-jump');if(adv){adv.textContent='';adv.setAttribute('aria-label','Réglages avancés');adv.title='Réglages avancés'}
  }

  function scan(){scanQueued=false;decorateCards();compactSheet()}
  function queueScan(){if(scanQueued)return;scanQueued=true;requestAnimationFrame(scan)}

  async function init(){
    try{const r=await fetch(CATALOG_URL,{cache:'no-store'});if(r.ok)catalog=(await r.json()).heroes||[]}catch(e){console.error('WfGg hero UX v10 catalog',e)}
    scan();
    const mo=new MutationObserver(queueScan);mo.observe(document.body,{childList:true,subtree:true});
    document.addEventListener('visibilitychange',()=>{if(!document.hidden){queueScan();if(!liveTimer)startLive()}});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
  window.WfGgHeroUxV10=Object.freeze({version:'10.0.0',refresh:queueScan,awakeningS6:[...AWAKENING_S6]});
})();
