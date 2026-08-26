(() => {
  'use strict';

  const PROFILE_KEY='wfgg-simulator-profile-v1';
  const SLOT_ORDER=['gun','armor','chip','radar'];
  const TEXT={
    fr:{choose:'Choisir',none:'Aucun équipement',inventory:'Inventaire global',equipped:'Équipé',transfer:'Transférer depuis',create:'Créer un équipement',close:'Fermer',gun:'Arme',armor:'Armure',chip:'Puce',radar:'Radar',notOwned:'Ajoute d’abord ce héros à ton profil.',empty:'Aucun équipement de ce type dans ton inventaire.',tierLocked:'Non débloquée',tierBase:'Forme initiale',tier10:'Évolution I',tier20:'Évolution II',tier30:'Évolution III'},
    en:{choose:'Choose',none:'No gear',inventory:'Global inventory',equipped:'Equipped',transfer:'Transfer from',create:'Create gear',close:'Close',gun:'Weapon',armor:'Armor',chip:'Chip',radar:'Radar',notOwned:'Add this hero to your profile first.',empty:'No gear of this type in your inventory.',tierLocked:'Locked',tierBase:'Base form',tier10:'Evolution I',tier20:'Evolution II',tier30:'Evolution III'},
    it:{choose:'Scegli',none:'Nessun equipaggiamento',inventory:'Inventario globale',equipped:'Equipaggiato',transfer:'Trasferisci da',create:'Crea equipaggiamento',close:'Chiudi',gun:'Arma',armor:'Armatura',chip:'Chip',radar:'Radar',notOwned:'Aggiungi prima questo eroe al profilo.',empty:'Nessun equipaggiamento di questo tipo nell’inventario.',tierLocked:'Bloccata',tierBase:'Forma iniziale',tier10:'Evoluzione I',tier20:'Evoluzione II',tier30:'Evoluzione III'},
    es:{choose:'Elegir',none:'Sin equipamiento',inventory:'Inventario global',equipped:'Equipado',transfer:'Transferir desde',create:'Crear equipamiento',close:'Cerrar',gun:'Arma',armor:'Armadura',chip:'Chip',radar:'Radar',notOwned:'Añade primero este héroe a tu perfil.',empty:'No hay equipamiento de este tipo en tu inventario.',tierLocked:'Bloqueada',tierBase:'Forma inicial',tier10:'Evolución I',tier20:'Evolución II',tier30:'Evolución III'}
  };
  const GEAR_ICON={
    gun:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M4 13h17l4 4-4 4H11l-3 5H4l2-7H4v-6z"/></svg>',
    armor:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2 27 6v8c0 8-5 13-11 16C10 27 5 22 5 14V6z"/></svg>',
    chip:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M8 8h16v16H8zM3 11h4v3H3zm0 7h4v3H3zm22-7h4v3h-4zm0 7h4v3h-4zM11 3h3v4h-3zm7 0h3v4h-3zm-7 22h3v4h-3zm7 0h3v4h-3z"/></svg>',
    radar:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 4a12 12 0 1 0 12 12h-4a8 8 0 1 1-8-8V4zm1 6v7l6 3 2-3-4-2h7v-4h-7z"/></svg>'
  };

  let motionTimer=null;
  let currentLive=[];
  let lastLiveIds=new Set();
  let picker=null;
  let pickerBackdrop=null;
  let pickerSlot=null;

  const locale=()=>document.documentElement.lang||'fr';
  const t=k=>(TEXT[locale()]||TEXT.fr)[k]||TEXT.fr[k]||k;
  const norm=v=>String(v||'').trim().toLowerCase();
  const esc=v=>String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
  const profile=()=>{try{return window.WfGgProfilePersistence?.profile?.()||JSON.parse(localStorage.getItem(PROFILE_KEY)||'{}')||{}}catch{return {}}};
  const currentHeroName=()=>document.querySelector('#heroGameSheet.open .hero-sheet-title h3')?.textContent?.trim()||'';
  const heroOwned=name=>(profile().heroes||[]).some(h=>norm(h.heroId)===norm(name));
  const slotLabel=slot=>t(slot);

  /* ---------------------------------------------------------------------- */
  /* Selective card animation: 5–6 cards at a time, fresh random batch.     */
  /* ---------------------------------------------------------------------- */
  function clearLive(){
    currentLive.forEach(card=>{if(card?.isConnected){card.classList.remove('wfgg-live-card');card.style.removeProperty('--wfgg-live-delay');card.style.removeProperty('--wfgg-live-duration')}});
    currentLive=[];
  }
  function shuffled(list){
    const a=list.slice();
    for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}
    return a;
  }
  function animateBatch(){
    clearTimeout(motionTimer);clearLive();
    if(document.hidden||matchMedia('(prefers-reduced-motion: reduce)').matches){motionTimer=setTimeout(animateBatch,2400);return}
    const grid=document.querySelector('.game-hero-grid:not(.is-selecting)');
    const cards=grid?[...grid.querySelectorAll('.game-hero-card[data-hero-id]')].filter(c=>c.offsetParent!==null):[];
    if(!cards.length){motionTimer=setTimeout(animateBatch,1200);return}
    const target=Math.min(cards.length,cards.length<5?cards.length:(5+Math.floor(Math.random()*2)));
    let pool=cards.filter(c=>!lastLiveIds.has(c.dataset.heroId));
    if(pool.length<target)pool=cards;
    currentLive=shuffled(pool).slice(0,target);
    lastLiveIds=new Set(currentLive.map(c=>c.dataset.heroId));
    currentLive.forEach((card,i)=>{
      card.style.setProperty('--wfgg-live-delay',`${Math.round(Math.random()*180)}ms`);
      card.style.setProperty('--wfgg-live-duration',`${(1.18+Math.random()*.55).toFixed(2)}s`);
      card.classList.add('wfgg-live-card');
    });
    const activeFor=1850;
    setTimeout(clearLive,activeFor);
    motionTimer=setTimeout(animateBatch,2250+Math.round(Math.random()*500));
  }
  function startMotion(){if(motionTimer)return;motionTimer=setTimeout(animateBatch,900)}

  /* ---------------------------------------------------------------------- */
  /* Gear picker: item remains in global inventory; only assignment changes. */
  /* ---------------------------------------------------------------------- */
  function ensurePicker(){
    if(picker&&picker.isConnected)return;
    pickerBackdrop=document.createElement('div');pickerBackdrop.className='wfgg-gear-picker-backdrop';pickerBackdrop.id='wfggGearPickerBackdrop';
    picker=document.createElement('section');picker.className='wfgg-gear-picker';picker.id='wfggGearPicker';picker.setAttribute('role','dialog');picker.setAttribute('aria-modal','true');
    document.body.append(pickerBackdrop,picker);
    pickerBackdrop.addEventListener('click',closePicker);
    picker.addEventListener('click',onPickerClick);
  }
  function closePicker(){if(!picker)return;picker.classList.remove('open');pickerBackdrop?.classList.remove('open');pickerSlot=null}
  function itemTitle(g,index){return g.itemId?.trim()||`${slotLabel(g.slot)} ${index+1}`}
  function stars(v){const n=Math.max(0,Math.min(5,Number(v)||0));return n?`★ ${n}`:'★ 0'}
  function renderPicker(slot){
    ensurePicker();pickerSlot=slot;
    const hero=currentHeroName();const p=profile();const gear=Array.isArray(p.gear)?p.gear:[];
    if(!heroOwned(hero)){
      picker.innerHTML=`<div class="wfgg-gear-picker-head"><small>${esc(t('inventory'))}</small><h4>${esc(slotLabel(slot))}</h4><button class="wfgg-gear-picker-close" data-picker-close type="button" aria-label="${esc(t('close'))}">×</button></div><div class="wfgg-gear-picker-list"><div class="wfgg-gear-empty">${esc(t('notOwned'))}</div></div><div class="wfgg-gear-picker-foot"><button data-picker-close type="button">${esc(t('close'))}</button></div>`;
      requestAnimationFrame(()=>{pickerBackdrop.classList.add('open');picker.classList.add('open')});return;
    }
    const items=gear.map((g,index)=>({g,index})).filter(x=>x.g.slot===slot);
    const current=items.find(x=>norm(x.g.currentlyAssignedHero)===norm(hero));
    const none=`<button class="wfgg-gear-choice ${current?'':'current'}" type="button" data-gear-none="1"><span class="wfgg-gear-choice-icon">${GEAR_ICON[slot]||''}</span><span class="wfgg-gear-choice-main"><b>${esc(t('none'))}</b><span>${esc(slotLabel(slot))}</span></span><span class="wfgg-gear-choice-side">${current?'':`✓ ${esc(t('equipped'))}`}</span></button>`;
    const rows=items.map(({g,index})=>{
      const isCurrent=norm(g.currentlyAssignedHero)===norm(hero);const other=g.currentlyAssignedHero&&!isCurrent?g.currentlyAssignedHero:'';
      return `<button class="wfgg-gear-choice rarity-${esc(g.rarity||'R')} ${isCurrent?'current':''}" type="button" data-gear-index="${index}"><span class="wfgg-gear-choice-icon">${GEAR_ICON[slot]||''}</span><span class="wfgg-gear-choice-main"><b>${esc(itemTitle(g,index))}</b><span>${esc(g.rarity||'R')} · Lv.${esc(g.level??0)} · ${esc(stars(g.stars))}${Number(g.promotion)?` · +${esc(g.promotion)}`:''}</span></span><span class="wfgg-gear-choice-side">${isCurrent?`✓ ${esc(t('equipped'))}`:other?`${esc(t('transfer'))}<small>${esc(other)}</small>`:''}</span></button>`;
    }).join('');
    picker.innerHTML=`<div class="wfgg-gear-picker-head"><small>${esc(t('inventory'))} · ${esc(hero)}</small><h4>${esc(slotLabel(slot))}</h4><button class="wfgg-gear-picker-close" data-picker-close type="button" aria-label="${esc(t('close'))}">×</button></div><div class="wfgg-gear-picker-list">${none}${rows||`<div class="wfgg-gear-empty">${esc(t('empty'))}</div>`}</div><div class="wfgg-gear-picker-foot"><button data-picker-close type="button">${esc(t('close'))}</button><button class="primary" data-create-gear="${esc(slot)}" type="button">＋ ${esc(t('create'))}</button></div>`;
    requestAnimationFrame(()=>{pickerBackdrop.classList.add('open');picker.classList.add('open')});
  }
  function assignThroughExistingForm(index,hero){
    const cards=[...document.querySelectorAll('#step-gear .gear-card')];
    const sel=cards[index]?.querySelector('[data-field="currentlyAssignedHero"]');
    if(!sel)return false;
    sel.value=hero;
    sel.dispatchEvent(new Event('input',{bubbles:true}));
    sel.dispatchEvent(new Event('change',{bubbles:true}));
    return true;
  }
  function assignGear(index,slot){
    const hero=currentHeroName();if(!hero||!heroOwned(hero))return false;
    const before=profile();const gear=Array.isArray(before.gear)?before.gear:[];
    const clearIndices=[];
    gear.forEach((g,i)=>{if(g.slot===slot&&norm(g.currentlyAssignedHero)===norm(hero)&&i!==index)clearIndices.push(i)});
    clearIndices.forEach(i=>assignThroughExistingForm(i,''));
    if(index!=null)assignThroughExistingForm(index,hero);
    decorateGearSlots();
    renderPicker(slot);
    return true;
  }
  function createGear(slot){
    closePicker();
    document.querySelector('#heroSheetClose')?.click();
    document.querySelector('#stepNav [data-step="2"]')?.click();
    setTimeout(()=>{
      document.querySelector('#addGear')?.click();
      setTimeout(()=>{
        const cards=[...document.querySelectorAll('#step-gear .gear-card')];
        const card=cards.at(-1);const sel=card?.querySelector('[data-field="slot"]');
        if(sel){sel.value=slot;sel.dispatchEvent(new Event('input',{bubbles:true}));sel.dispatchEvent(new Event('change',{bubbles:true}))}
        card?.scrollIntoView({behavior:'smooth',block:'center'});
      },80);
    },120);
  }
  function onPickerClick(e){
    if(e.target.closest('[data-picker-close]')){closePicker();return}
    const create=e.target.closest('[data-create-gear]');if(create){createGear(create.dataset.createGear);return}
    if(e.target.closest('[data-gear-none]')){assignGear(null,pickerSlot);return}
    const choice=e.target.closest('[data-gear-index]');if(choice)assignGear(Number(choice.dataset.gearIndex),pickerSlot);
  }
  function decorateGearSlots(){
    const sheet=document.querySelector('#heroGameSheet.open');if(!sheet)return;
    const hero=currentHeroName();const p=profile();const gear=Array.isArray(p.gear)?p.gear:[];
    const assigned=Object.fromEntries(SLOT_ORDER.map(slot=>[slot,gear.find(g=>g.slot===slot&&norm(g.currentlyAssignedHero)===norm(hero))||null]));
    [...sheet.querySelectorAll('.lw4-gear')].slice(0,4).forEach((box,i)=>{
      const slot=SLOT_ORDER[i];const item=assigned[slot];box.dataset.gearSlot=slot;box.classList.add('wfgg-gear-slot');box.setAttribute('role','button');box.setAttribute('tabindex','0');
      box.classList.remove('wfgg-empty-gear','wfgg-gear-UR','wfgg-gear-SSR','wfgg-gear-SR','wfgg-gear-R');box.classList.add(item?`wfgg-gear-${item.rarity||'R'}`:'wfgg-empty-gear');
      const small=box.querySelector('small');if(small)small.textContent=item?`${item.rarity||'R'} · Lv.${item.level??0}`:t('choose');
      let state=box.querySelector('.wfgg-gear-state');if(!state){state=document.createElement('span');state.className='wfgg-gear-state';box.appendChild(state)}state.textContent=item?(item.itemId||`${stars(item.stars)}`):slotLabel(slot);
      let mark=box.querySelector('.wfgg-gear-pick-mark');if(!mark){mark=document.createElement('span');mark.className='wfgg-gear-pick-mark';mark.textContent='›';box.appendChild(mark)}
      box.setAttribute('aria-label',`${slotLabel(slot)} · ${item?itemTitle(item,gear.indexOf(item)):t('choose')}`);
    });
  }

  /* ---------------------------------------------------------------------- */
  /* Exclusive weapon: visual band follows exact level boundaries.          */
  /* ---------------------------------------------------------------------- */
  function visualBand(level){if(level<=0)return'locked';if(level<10)return'base';if(level<20)return'tier10';if(level<30)return'tier20';return'tier30'}
  function visualLabel(level){const band=visualBand(level);return band==='locked'?t('tierLocked'):band==='base'?t('tierBase'):band==='tier10'?t('tier10'):band==='tier20'?t('tier20'):t('tier30')}
  function ensureWeaponLayer(stage){
    let layer=stage.querySelector('.wfgg-ew-layer');if(!layer){layer=document.createElement('div');layer.className='wfgg-ew-layer';layer.setAttribute('aria-hidden','true');layer.innerHTML='<i class="wfgg-ew-ring r1"></i><i class="wfgg-ew-ring r2"></i><i class="wfgg-ew-core"></i><i class="wfgg-ew-particle p1"></i><i class="wfgg-ew-particle p2"></i><i class="wfgg-ew-particle p3"></i><i class="wfgg-ew-particle p4"></i><i class="wfgg-ew-particle p5"></i>';stage.prepend(layer)}
    let badge=stage.querySelector('.wfgg-ew-evolution');if(!badge){badge=document.createElement('span');badge.className='wfgg-ew-evolution';stage.appendChild(badge)}return badge;
  }
  function decorateWeaponStage(){
    const sheet=document.querySelector('#heroGameSheet.open');if(!sheet)return;
    const stage=sheet.querySelector('.lw4-weapon-stage');if(!stage)return;
    const input=stage.parentElement?.querySelector('[data-lw4-weapon-level]')||sheet.querySelector('[data-lw4-weapon-level]');
    const badgeText=stage.querySelector('.lw4-weapon-level')?.textContent||'';
    const parsed=Number(input?.value??badgeText.replace(/[^0-9.]/g,''));const level=Number.isFinite(parsed)?Math.max(0,parsed):0;
    const band=visualBand(level);stage.dataset.wfggEw=band;const badge=ensureWeaponLayer(stage);badge.textContent=`${visualLabel(level)} · Lv.${Math.round(level)}`;
  }

  function scan(){decorateGearSlots();decorateWeaponStage()}
  const observer=new MutationObserver(()=>requestAnimationFrame(scan));

  document.addEventListener('click',e=>{
    const slot=e.target.closest?.('.lw4-gear.wfgg-gear-slot');if(slot){e.preventDefault();e.stopPropagation();renderPicker(slot.dataset.gearSlot)}
  },true);
  document.addEventListener('keydown',e=>{
    const slot=e.target.closest?.('.lw4-gear.wfgg-gear-slot');if(slot&&(e.key==='Enter'||e.key===' ')){e.preventDefault();renderPicker(slot.dataset.gearSlot)}
  },true);
  document.addEventListener('input',e=>{if(e.target.matches?.('[data-lw4-weapon-level]'))requestAnimationFrame(decorateWeaponStage)},true);
  document.addEventListener('change',e=>{if(e.target.matches?.('[data-lw4-weapon-level]'))setTimeout(decorateWeaponStage,60)},true);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!motionTimer)startMotion()});

  function init(){
    startMotion();scan();
    if(document.body)observer.observe(document.body,{childList:true,subtree:true});
    window.WfGgHeroUxV9=Object.freeze({version:'9.0.0',animateNow:animateBatch,decorateGearSlots,decorateWeaponStage,openGearPicker:renderPicker,profile});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
