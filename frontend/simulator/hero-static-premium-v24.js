(()=>{
  'use strict';

  const VERSION='24.1-static-premium-lean';
  const CATALOG_URL='data/hero-catalog.v2.json';
  const BASE=id=>`assets/heroes/cutout-v21/${id}.webp`;
  const LEGACY_CLASSES=[
    'wfgg-live-card','wfgg-v10-live','wfgg-v12-live','wfgg-v13-live','wfgg-v14-live','wfgg-v15-live',
    'wfgg-native-gif-active-v17b','wfgg-native-gif-active-v17c','wfgg-v22-native-active','wfgg-v223-native-active'
  ];
  const ICON={
    tank:'assets/icons/lastwar/Tank.png', aircraft:'assets/icons/lastwar/Aircraft.png', missile:'assets/icons/lastwar/Missile.png',
    attack:'assets/icons/lastwar/Attack.png', defense:'assets/icons/lastwar/Defense.png', support:'assets/icons/lastwar/Support.png'
  };
  const LABEL={
    fr:{tank:'Tank',aircraft:'Avion',missile:'Véhicule Missile',attack:'Attaque',defense:'Défense',support:'Soutien'},
    en:{tank:'Tank',aircraft:'Aircraft',missile:'Missile',attack:'Attack',defense:'Defense',support:'Support'},
    it:{tank:'Tank',aircraft:'Aereo',missile:'Veicolo Missile',attack:'Attacco',defense:'Difesa',support:'Supporto'},
    es:{tank:'Tank',aircraft:'Avión',missile:'Vehículo de misiles',attack:'Ataque',defense:'Defensa',support:'Apoyo'}
  };

  /* Kimberly-master framing. One profile per hero, deliberately static. */
  const FRAME={
    williams:{x:0,y:4,z:.84}, murphy:{x:0,y:4,z:.88}, kimberly:{x:0,y:1,z:.96}, marshall:{x:0,y:-7,z:.90},
    stetmann:{x:0,y:-7,z:.89}, dva:{x:0,y:2,z:.89}, carlie:{x:0,y:1,z:.91}, lucius:{x:0,y:-8,z:.87},
    schuyler:{x:0,y:-9,z:.87}, morrison:{x:0,y:4,z:.82}, tesla:{x:0,y:3,z:.89}, swift:{x:0,y:-3,z:.87},
    fiona:{x:0,y:2,z:.89}, adam:{x:0,y:5,z:.83}, mcgregor:{x:0,y:3,z:.89}, monica:{x:0,y:1,z:.93},
    mason:{x:0,y:5,z:.79}, violet:{x:0,y:4,z:.83}, scarlett:{x:0,y:3,z:.87}, richard:{x:0,y:1,z:.89},
    farhad:{x:0,y:-8,z:.88}, sarah:{x:0,y:-6,z:.89}, maxwell:{x:0,y:-8,z:.87}, cage:{x:0,y:-6,z:.87},
    venom:{x:0,y:2,z:.89}, braz:{x:0,y:-7,z:.89}, elsa:{x:0,y:1,z:.90}, gump:{x:0,y:2,z:.89},
    loki:{x:0,y:5,z:.72}, ambolt:{x:0,y:4,z:.80}, kane:{x:0,y:1,z:.90}
  };

  let catalog=[];
  let queued=false;
  const norm=v=>String(v||'').trim().toLowerCase();
  const currentLang=()=>document.documentElement.lang||'fr';
  const label=k=>(LABEL[currentLang()]||LABEL.fr)[k]||k;
  const heroStep=()=>document.getElementById('step-heroes');
  const cards=()=>[...document.querySelectorAll('#gameHeroGrid .game-hero-card[data-hero-id]')];
  const byId=id=>catalog.find(h=>h.id===id)||null;

  window.WfGgHeroMotionOwner='static-v24';
  window.WfGgHeroStaticV24={version:VERSION,frame:FRAME};
  document.documentElement.dataset.wfggHeroAnimation='off';
  document.documentElement.dataset.wfggHeroPortraitOwner='static-v24';

  function iconMarkup(kind){
    const src=ICON[kind];
    if(!src)return '';
    const text=label(kind);
    return `<span class="wfgg-v15-semantic-icon" title="${text}" aria-label="${text}"><img src="${src}" alt="" aria-hidden="true"><span class="wfgg-v15-sr-only">${text}</span></span>`;
  }

  function neutralize(card){
    LEGACY_CLASSES.forEach(c=>card.classList.remove(c));
    card.classList.remove('wfgg-v223-owned');
    card.classList.add('wfgg-static-v24-owned');
    card.dataset.wfggPortraitOwner='static-v24';
  }

  function staticStage(card){
    const host=card.querySelector('.hero-card-portrait');
    if(!host)return null;
    host.querySelectorAll(':scope > .wfgg-v223-stage,:scope > .wfgg-v22-stage,:scope > .wfgg-v15-motion-layer').forEach(n=>n.remove());
    let stage=host.querySelector(':scope > .wfgg-static-v24-stage');
    if(!stage){
      stage=document.createElement('span');
      stage.className='wfgg-static-v24-stage';
      stage.setAttribute('aria-hidden','true');
      const img=document.createElement('img');
      img.className='wfgg-static-v24-img';
      img.alt='';
      img.decoding='async';
      img.loading='lazy';
      stage.appendChild(img);
      host.appendChild(stage);
    }
    return stage;
  }

  function decorateCardSemantics(card,cat){
    if(!cat)return;
    let layer=card.querySelector(':scope > .wfgg-v15-card-semantics');
    if(!layer){
      layer=document.createElement('div');
      layer.className='wfgg-v15-card-semantics';
      card.appendChild(layer);
    }
    const signature=`${cat.troopType}|${cat.role}|${currentLang()}`;
    if(layer.dataset.signature!==signature){
      layer.innerHTML=`${iconMarkup(cat.troopType)}${iconMarkup(cat.role)}`;
      layer.setAttribute('aria-label',`${label(cat.troopType)}, ${label(cat.role)}`);
      layer.dataset.signature=signature;
    }
  }

  function applyCard(card){
    const id=norm(card?.dataset?.heroId);
    if(!id)return;
    neutralize(card);
    const f=FRAME[id]||{x:0,y:2,z:.89};
    card.style.setProperty('--wfgg-static-x',`${f.x}%`);
    card.style.setProperty('--wfgg-static-y',`${f.y}%`);
    card.style.setProperty('--wfgg-static-zoom',String(f.z));
    card.dataset.wfggStaticFrame=`${f.x},${f.y},${f.z}`;
    const stage=staticStage(card);
    const img=stage?.querySelector('.wfgg-static-v24-img');
    if(img){
      const wanted=BASE(id);
      if(!img.getAttribute('src')?.includes(`/cutout-v21/${id}.webp`))img.src=wanted;
    }
    decorateCardSemantics(card,byId(id));
  }

  function idFromSheet(){
    const sheet=document.getElementById('heroGameSheet');
    if(!sheet?.classList.contains('open'))return null;
    const name=norm(sheet.querySelector('.hero-sheet-title h3')?.textContent);
    if(!name)return null;
    if(name==='skyler')return 'schuyler';
    return catalog.find(h=>norm(h.name)===name)?.id||null;
  }

  function decorateSheetSemantics(sheet,cat){
    const title=sheet.querySelector('.hero-sheet-title');
    if(!title||!cat)return;
    let layer=title.querySelector(':scope > .wfgg-v15-sheet-semantics');
    if(!layer){
      layer=document.createElement('div');
      layer.className='wfgg-v15-sheet-semantics';
      title.appendChild(layer);
    }
    const signature=`${cat.troopType}|${cat.role}|${currentLang()}`;
    if(layer.dataset.signature!==signature){
      layer.innerHTML=`${iconMarkup(cat.troopType)}${iconMarkup(cat.role)}`;
      layer.dataset.signature=signature;
    }
  }

  function applySheet(){
    const sheet=document.getElementById('heroGameSheet');
    const id=idFromSheet();
    if(!sheet||!id)return;
    const src=BASE(id);
    sheet.querySelectorAll('.lw4-unit-portrait,.lw4-skill-hero img,.lw4-tier-portrait img').forEach(img=>{
      if(!(img instanceof HTMLImageElement))return;
      if(!img.getAttribute('src')?.includes(`/cutout-v21/${id}.webp`))img.src=src;
      img.decoding='async';
      img.loading='eager';
      img.dataset.wfggStaticSource='v24';
    });
    decorateSheetSemantics(sheet,byId(id));
    sheet.dataset.wfggStaticHero=id;
  }

  function apply(){
    cards().forEach(applyCard);
    applySheet();
    document.documentElement.dataset.wfggHeroAnimation='off';
    document.documentElement.dataset.wfggHeroPortraitOwner='static-v24';
    document.documentElement.dataset.wfggStaticCount=String(cards().length);
  }

  function schedule(){
    if(queued)return;
    queued=true;
    requestAnimationFrame(()=>{queued=false;apply()});
  }

  async function init(){
    try{
      const r=await fetch(CATALOG_URL,{cache:'force-cache'});
      if(r.ok)catalog=(await r.json()).heroes||[];
    }catch(_){catalog=[]}
    apply();
    const root=heroStep()||document.body;
    new MutationObserver(schedule).observe(root,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
    document.addEventListener('click',schedule,true);
    document.addEventListener('wfgg:languagechange',schedule);
    window.addEventListener('pageshow',schedule);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
