(() => {
  'use strict';
  const PROFILE_KEY='wfgg-simulator-profile-v1';
  const CATALOG_URL='data/hero-catalog.v2.json';
  const norm=v=>String(v||'').trim().toLowerCase();
  const esc=v=>String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
  const delay=ms=>new Promise(r=>setTimeout(r,ms));
  let catalog=[];
  let filter='all';
  let query='';
  let selectedId=null;
  let selectedTab='attributes';
  let selectionMode=false;
  let bulkBusy=false;
  let enhancing=false;

  const L={
    fr:{search:'Rechercher un héros…',all:'Tous',tank:'Tank',aircraft:'Avion',missile:'Véhicule Missile',owned:'possédés',level:'Niv.',attack:'Attaque',defense:'Défense',support:'Soutien',attributes:'Attributs',grade:'Grade',weapon:'Arme exclusive',wall:'Mur d’honneur',add:'Ajouter à mon profil',remove:'Retirer du profil',power:'Puissance',hp:'PV',stars:'Étoiles',rarity:'Rareté / variante',awaken:'Éveil débloqué',awakenStars:'Étoiles d’éveil',awakenTier:'Palier d’éveil',awakenSkill:'Compétence d’éveil',weaponLevel:'Niveau de l’arme exclusive',wallLevel:'Niveau au Mur d’honneur',monster:'Bonus dégâts monstres %',pve:'Bonus dégâts PvE %',advanced:'Ouvrir les réglages avancés',advancedTitle:'Réglages avancés / compétences',notOwned:'Ce héros n’est pas encore dans votre profil. Touchez « Ajouter » puis renseignez ses valeurs réelles.',saved:'Chaque changement est sauvegardé automatiquement.',promotion:'Promotion saison',awakening:'Awakening',multi:'Sélection multiple',multiHint:'Touchez les cartes pour ajouter ou retirer plusieurs héros. ⓘ ouvre la fiche.',detailsMode:'Mode fiches',details:'Ouvrir la fiche',selectAll:'Sélectionner tout',clearAll:'Tout désélectionner',done:'Terminer'},
    en:{search:'Search hero…',all:'All',tank:'Tank',aircraft:'Aircraft',missile:'Missile Vehicle',owned:'owned',level:'Lv.',attack:'Attack',defense:'Defense',support:'Support',attributes:'Attributes',grade:'Grade',weapon:'Exclusive Weapon',wall:'Wall of Honor',add:'Add to my profile',remove:'Remove from profile',power:'Power',hp:'HP',stars:'Stars',rarity:'Rarity / variant',awaken:'Awakening unlocked',awakenStars:'Awakening stars',awakenTier:'Awakening tier',awakenSkill:'Awakening skill',weaponLevel:'Exclusive Weapon level',wallLevel:'Wall of Honor level',monster:'Monster damage bonus %',pve:'PvE damage bonus %',advanced:'Open advanced settings',advancedTitle:'Advanced settings / skills',notOwned:'This hero is not in your profile yet. Tap Add, then enter the real values shown in game.',saved:'Every change is saved automatically.',promotion:'Season promotion',awakening:'Awakening',multi:'Multi-select',multiHint:'Tap cards to add or remove several heroes. ⓘ opens details.',detailsMode:'Details mode',details:'Open details',selectAll:'Select all',clearAll:'Clear all',done:'Done'},
    it:{search:'Cerca eroe…',all:'Tutti',tank:'Tank',aircraft:'Aereo',missile:'Veicolo Missile',owned:'posseduti',level:'Liv.',attack:'Attacco',defense:'Difesa',support:'Supporto',attributes:'Attributi',grade:'Grado',weapon:'Arma esclusiva',wall:'Wall of Honor',add:'Aggiungi al profilo',remove:'Rimuovi dal profilo',power:'Potenza',hp:'PV',stars:'Stelle',rarity:'Rarità / variante',awaken:'Awakening sbloccato',awakenStars:'Stelle Awakening',awakenTier:'Tier Awakening',awakenSkill:'Abilità Awakening',weaponLevel:'Livello arma esclusiva',wallLevel:'Livello Wall of Honor',monster:'Bonus danni mostri %',pve:'Bonus danni PvE %',advanced:'Apri impostazioni avanzate',advancedTitle:'Impostazioni avanzate / abilità',notOwned:'Questo eroe non è ancora nel profilo. Tocca Aggiungi e inserisci i valori reali mostrati nel gioco.',saved:'Ogni modifica viene salvata automaticamente.',promotion:'Promozione stagione',awakening:'Awakening',multi:'Selezione multipla',multiHint:'Tocca le carte per aggiungere o rimuovere più eroi. ⓘ apre la scheda.',detailsMode:'Modalità schede',details:'Apri scheda',selectAll:'Seleziona tutto',clearAll:'Deseleziona tutto',done:'Fine'},
    es:{search:'Buscar héroe…',all:'Todos',tank:'Tank',aircraft:'Avión',missile:'Vehículo de misiles',owned:'guardados',level:'Nv.',attack:'Ataque',defense:'Defensa',support:'Apoyo',attributes:'Atributos',grade:'Grado',weapon:'Arma exclusiva',wall:'Wall of Honor',add:'Añadir a mi perfil',remove:'Quitar del perfil',power:'Potencia',hp:'PV',stars:'Estrellas',rarity:'Rareza / variante',awaken:'Awakening desbloqueado',awakenStars:'Estrellas Awakening',awakenTier:'Nivel Awakening',awakenSkill:'Habilidad Awakening',weaponLevel:'Nivel del arma exclusiva',wallLevel:'Nivel Wall of Honor',monster:'Bonus daño monstruos %',pve:'Bonus daño PvE %',advanced:'Abrir ajustes avanzados',advancedTitle:'Ajustes avanzados / habilidades',notOwned:'Este héroe aún no está en tu perfil. Toca Añadir y escribe los valores reales mostrados en el juego.',saved:'Cada cambio se guarda automáticamente.',promotion:'Promoción de temporada',awakening:'Awakening',multi:'Selección múltiple',multiHint:'Toca las cartas para añadir o quitar varios héroes. ⓘ abre la ficha.',detailsMode:'Modo fichas',details:'Abrir ficha',selectAll:'Seleccionar todo',clearAll:'Deseleccionar todo',done:'Listo'}
  };

  function locale(){return document.documentElement.lang||'fr'}
  function t(k){return (L[locale()]||L.fr)[k]||L.fr[k]||k}
  function profile(){
    try{return window.WfGgProfilePersistence?.profile?.()||JSON.parse(localStorage.getItem(PROFILE_KEY)||'{}')||{};}catch(_){return {}}
  }
  function heroIndex(name){return (profile().heroes||[]).findIndex(h=>norm(h.heroId)===norm(name))}
  function ownedHero(cat){const i=heroIndex(cat.name);return i<0?null:{index:i,data:(profile().heroes||[])[i]}}
  function roleIcon(role){
    if(role==='defense')return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2 27 6v8c0 8.1-4.7 13.1-11 16C9.7 27.1 5 22.1 5 14V6l11-4zm0 5-6 2.2v5c0 4.7 2.3 8 6 10.2 3.7-2.2 6-5.5 6-10.2v-5L16 7z"/></svg>';
    if(role==='support')return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M12 3h8v9h9v8h-9v9h-8v-9H3v-8h9V3z"/></svg>';
    return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="m25.8 3.4 2.8 2.8-8.1 8.1 2.5 2.5-3.2 3.2-2.5-2.5-6.7 6.7 2.7 2.7-2.7 2.7-8.1-8.1 2.7-2.7 2.7 2.7 6.7-6.7-2.5-2.5 3.2-3.2 2.5 2.5 8.1-8.1z"/></svg>';
  }
  function roleLabel(role){return t(role)}
  function initials(name){return name.split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase()}
  function stars(n){const v=Math.max(0,Math.min(5,Math.floor(Number(n)||0)));return '★'.repeat(v)+'☆'.repeat(5-v)}
  function fmt(v){const n=Number(v);return Number.isFinite(n)&&n>0?n.toLocaleString(locale()==='fr'?'fr-FR':undefined):'—'}

  function troopSvg(type){
    if(type==='aircraft')return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M28 15.2 18.8 11l-3.6-8H12l1.4 8.5-6.7 2.1-3.2-2.2H1.2l2 4.6-2 4.6h2.3l3.2-2.2 6.7 2.1L12 29h3.2l3.6-8 9.2-4.2z"/></svg>';
    if(type==='missile')return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M4 20h17l6-5-6-5H4l4 5-4 5zm0 3h18v4H4zm2-18h16v3H6z"/></svg>';
    return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M6 10h17l4 5v8H5v-9l1-4zm4-5h9l2 4H9l1-4zM8 24a3 3 0 1 0 0 6 3 3 0 0 0 0-6zm15 0a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"/></svg>';
  }
  function uiIcon(kind){
    const icons={
      attributes:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M5 25h4V14H5v11zm9 0h4V7h-4v18zm9 0h4V11h-4v14z"/><path d="M3 27h26v2H3z"/></svg>',
      grade:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="m16 2 4.1 8.4 9.2 1.3-6.6 6.5 1.5 9.2L16 23l-8.2 4.4 1.5-9.2-6.6-6.5 9.2-1.3L16 2z"/></svg>',
      weapon:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M4 18h15l4-4 5 5-4 4-4-1-4 6h-5l3-7H4v-3zm2-6h12v4H6v-4z"/></svg>',
      wall:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M4 5h7v5h10V5h7v22H4V5zm4 10v8h5v-8H8zm11 0v8h5v-8h-5z"/></svg>',
      power:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M18 2 7 18h8l-1 12 11-17h-8l1-11z"/></svg>',
      attack:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 3a13 13 0 1 0 13 13A13 13 0 0 0 16 3zm0 5a8 8 0 1 1-8 8 8 8 0 0 1 8-8zm0 4a4 4 0 1 0 4 4 4 4 0 0 0-4-4z"/></svg>',
      defense:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2 27 6v8c0 8.1-4.7 13.1-11 16C9.7 27.1 5 22.1 5 14V6l11-4z"/></svg>',
      hp:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 28 5.2 17.5C-1 11.2 3 3 9.8 4.1 12.6 4.5 14.4 6 16 8c1.6-2 3.4-3.5 6.2-3.9C29 3 33 11.2 26.8 17.5L16 28z"/></svg>',
      level:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="m16 3 9 8h-6v9h-6v-9H7l9-8zm-9 21h18v5H7z"/></svg>',
      stars:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="m16 3 3.6 7.4 8.2 1.2-5.9 5.8 1.4 8.2L16 21.7l-7.3 3.9 1.4-8.2-5.9-5.8 8.2-1.2L16 3z"/></svg>',
      rarity:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2 29 16 16 30 3 16 16 2zm0 7-6.5 7L16 23l6.5-7L16 9z"/></svg>',
      generic:'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M6 7h20v4H6V7zm0 7h20v4H6v-4zm0 7h20v4H6v-4z"/></svg>'
    };
    return icons[kind]||icons.generic;
  }
  function fieldIcon(field){
    if(field==='displayedPower')return uiIcon('power');
    if(field==='displayedAttack')return uiIcon('attack');
    if(field==='displayedDefense')return uiIcon('defense');
    if(field==='displayedHp')return uiIcon('hp');
    if(field==='level'||field==='wallOfHonorLevel'||field==='exclusiveWeaponLevel')return uiIcon('level');
    if(field==='stars'||field==='awakeningStars'||field==='awakeningTier')return uiIcon('stars');
    if(field==='rarity')return uiIcon('rarity');
    return uiIcon('generic');
  }

  function portrait(cat){
    const fallback=`<span class="hero-fallback">${esc(initials(cat.name))}</span>`;
    if(!cat.portrait)return fallback;
    return `<img src="${esc(cat.portrait)}" alt="${esc(cat.name)}" loading="lazy" referrerpolicy="no-referrer">${fallback}`;
  }
  function bindImageFallbacks(root){
    root?.querySelectorAll?.('.hero-card-portrait img,.hero-sheet-portrait img').forEach(img=>{
      if(img.dataset.fallbackBound)return;
      img.dataset.fallbackBound='1';
      img.addEventListener('error',()=>img.remove(),{once:true});
    });
  }

  function filtered(){
    const q=norm(query);
    return catalog.filter(h=>(filter==='all'||h.troopType===filter)&&(!q||norm(h.name).includes(q)||norm(h.title?.[locale()]||h.title?.en).includes(q)));
  }

  function cardHtml(cat){
    const own=ownedHero(cat);const d=own?.data||{};const rarity=d.rarity||cat.rarity;const lvl=d.level||'';const st=d.stars||0;
    return `<article class="game-hero-card rarity-${esc(rarity)} ${own?'owned':''} ${selectedId===cat.id?'selected':''} ${selectionMode?'selection-mode':''}" data-hero-id="${esc(cat.id)}" role="button" tabindex="0" aria-label="${esc(cat.name)}" aria-pressed="${own?'true':'false'}">
      <span class="hero-card-portrait">${portrait(cat)}</span>
      ${selectionMode?`<span class="hero-select-dot ${own?'on':''}" aria-hidden="true">${own?'✓':''}</span>`:''}
      <span class="hero-role-badge" title="${esc(roleLabel(cat.role))}">${roleIcon(cat.role)}</span>
      ${cat.promotableTo?`<span class="hero-promote-mark">${esc(cat.rarity)}→${esc(cat.promotableTo)}</span>`:''}
      <span class="hero-type-mini">${troopSvg(cat.troopType)}</span>
      <span class="hero-rarity-badge">${esc(rarity)}</span>
      <span class="hero-card-footer"><span class="hero-card-name">${esc(cat.name)}</span><span class="hero-card-meta"><span>${lvl?`${esc(t('level'))}${esc(lvl)}`:own?'—':''}</span><span class="hero-card-stars">${own?stars(st):'☆☆☆☆☆'}</span></span></span>
    </article>`;
  }

  async function toggleOwned(cat){
    if(bulkBusy)return;
    if(ownedHero(cat))removeHero(cat,false,false);else await addHero(cat,false,false);
    await delay(90);
    enhance(true);
  }

  async function setVisibleOwned(target){
    if(bulkBusy)return;bulkBusy=true;
    const rows=filtered();
    try{
      for(const cat of rows){
        const own=!!ownedHero(cat);
        if(target&&!own)await addHero(cat,false,false);
        if(!target&&own){removeHero(cat,false,false);await delay(70)}
      }
    }finally{
      bulkBusy=false;enhance(true);
    }
  }

  function bindCardGesture(card,shell){
    const cat=()=>catalog.find(h=>h.id===card.dataset.heroId);
    let timer=null,startX=0,startY=0,longPressed=false;
    const clear=()=>{if(timer){clearTimeout(timer);timer=null}};
    const activate=()=>{
      const h=cat();if(!h)return;
      if(longPressed){longPressed=false;return}
      if(selectionMode)toggleOwned(h);else openSheet(h.id);
    };
    card.addEventListener('pointerdown',e=>{
      if(e.pointerType==='mouse'&&e.button!==0)return;
      startX=e.clientX;startY=e.clientY;longPressed=false;clear();
      timer=setTimeout(()=>{
        timer=null;longPressed=true;const h=cat();if(!h)return;
        selectionMode=true;
        try{if(navigator.vibrate)navigator.vibrate(18)}catch(_){}
        renderRoster(shell);
        toggleOwned(h);
      },480);
    });
    card.addEventListener('pointermove',e=>{if(Math.hypot(e.clientX-startX,e.clientY-startY)>12)clear()});
    card.addEventListener('pointerup',clear);
    card.addEventListener('pointercancel',clear);
    card.addEventListener('pointerleave',e=>{if(e.pointerType==='mouse')clear()});
    card.addEventListener('contextmenu',e=>e.preventDefault());
    card.onclick=activate;
    card.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate()}};
  }

  function renderGrid(shell){
    if(!shell)return;const grid=shell.querySelector('#gameHeroGrid');if(!grid)return;
    const rows=filtered();grid.innerHTML=rows.length?rows.map(cardHtml).join(''):`<div class="game-roster-empty">Aucun héros</div>`;
    bindImageFallbacks(grid);
    const count=shell.querySelector('#gameRosterCount');const owned=(profile().heroes||[]).filter(h=>h.heroId).length;if(count)count.textContent=`${owned}/${catalog.length} ${t('owned')}`;
    grid.querySelectorAll('.game-hero-card[data-hero-id]').forEach(card=>bindCardGesture(card,shell));
  }

  function renderRoster(shell){
    const rows=filtered();
    const allVisibleSelected=rows.length>0&&rows.every(cat=>!!ownedHero(cat));
    shell.innerHTML=`<div class="game-roster-head ${selectionMode?'selecting':''}"><div class="game-roster-search"><input id="gameHeroSearch" value="${esc(query)}" placeholder="${esc(t('search'))}" autocomplete="off"></div><div class="game-roster-head-actions">${selectionMode?`<button id="heroSelectAll" class="hero-select-all" type="button" ${bulkBusy?'disabled':''}>${esc(allVisibleSelected?t('clearAll'):t('selectAll'))}</button><button id="heroSelectionDone" class="hero-selection-done" type="button" aria-label="${esc(t('done'))}">✓</button>`:''}<span id="gameRosterCount" class="game-roster-count"></span></div></div>
      <div class="game-type-tabs">
        <button class="game-type-tab ${filter==='all'?'active':''}" data-filter="all" type="button">${esc(t('all'))}</button>
        <button class="game-type-tab ${filter==='tank'?'active':''}" data-filter="tank" type="button">${troopSvg('tank')}<span>${esc(t('tank'))}</span></button>
        <button class="game-type-tab ${filter==='missile'?'active':''}" data-filter="missile" type="button">${troopSvg('missile')}<span>${esc(t('missile'))}</span></button>
        <button class="game-type-tab ${filter==='aircraft'?'active':''}" data-filter="aircraft" type="button">${troopSvg('aircraft')}<span>${esc(t('aircraft'))}</span></button>
      </div><div id="gameHeroGrid" class="game-hero-grid ${selectionMode?'is-selecting':''}"></div>`;
    shell.querySelector('#gameHeroSearch').oninput=e=>{query=e.target.value;renderRoster(shell)};
    const all=shell.querySelector('#heroSelectAll');if(all)all.onclick=()=>setVisibleOwned(!allVisibleSelected);
    const done=shell.querySelector('#heroSelectionDone');if(done)done.onclick=()=>{selectionMode=false;renderRoster(shell)};
    shell.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;renderRoster(shell)});
    renderGrid(shell);
  }

  function ensureSheet(){
    let backdrop=document.querySelector('#heroGameBackdrop');let sheet=document.querySelector('#heroGameSheet');
    if(!backdrop){backdrop=document.createElement('div');backdrop.id='heroGameBackdrop';backdrop.className='hero-game-sheet-backdrop';document.body.appendChild(backdrop);backdrop.onclick=closeSheet;}
    if(!sheet){sheet=document.createElement('section');sheet.id='heroGameSheet';sheet.className='hero-game-sheet';sheet.setAttribute('aria-modal','true');sheet.setAttribute('role','dialog');document.body.appendChild(sheet);}
    return {backdrop,sheet};
  }
  function closeSheet(){const {backdrop,sheet}=ensureSheet();backdrop.classList.remove('open');sheet.classList.remove('open');selectedId=null;const shell=document.querySelector('#gameHeroRosterV2');if(shell)renderGrid(shell)}

  function tabFields(cat,d,owned){
    const number=(field,label,min=0,max='',step='1')=>`<label class="hero-game-field field-${field}"><span class="hero-field-label"><i class="hero-field-icon">${fieldIcon(field)}</i>${esc(label)}</span><input data-edit-field="${field}" type="number" min="${min}" ${max!==''?`max="${max}"`:''} step="${step}" value="${esc(d[field]??'')}" ${owned?'':'disabled'}></label>`;
    const checkbox=(field,label)=>`<label class="hero-game-field wide field-${field}"><span class="hero-field-label"><i class="hero-field-icon">${uiIcon('grade')}</i>${esc(label)}</span><input data-edit-field="${field}" type="checkbox" ${d[field]?'checked':''} ${owned?'':'disabled'}></label>`;
    if(selectedTab==='grade')return `<div class="hero-tab-panel hero-tab-grade"><div class="hero-game-stats"><label class="hero-game-field field-rarity"><span class="hero-field-label"><i class="hero-field-icon">${uiIcon('rarity')}</i>${esc(t('rarity'))}</span><select data-edit-field="rarity" ${owned?'':'disabled'}>${['UR','SSR','SR','R'].map(x=>`<option value="${x}" ${(d.rarity||cat.rarity)===x?'selected':''}>${x}</option>`).join('')}</select></label>${number('level',t('level'),1,175)}${number('stars',t('stars'),0,5,'0.2')}${cat.promotableTo?`<div class="hero-game-field hero-promotion-tile"><span class="hero-field-label"><i class="hero-field-icon">${uiIcon('grade')}</i>${esc(t('promotion'))}</span><strong>${esc(cat.rarity)} → ${esc(cat.promotableTo)} · S${esc(cat.promotionSeason)}</strong></div>`:''}${cat.awakening?checkbox('awakeningUnlocked',t('awaken')):''}${cat.awakening?number('awakeningStars',t('awakenStars'),0,5):''}${cat.awakening?number('awakeningTier',t('awakenTier'),0,99):''}</div></div>`;
    if(selectedTab==='weapon')return `<div class="hero-tab-panel hero-tab-weapon"><div class="hero-tab-art">${uiIcon('weapon')}</div><div class="hero-game-stats">${number('exclusiveWeaponLevel',t('weaponLevel'),0,40)}${cat.awakening?number('awakeningSkillLevel',t('awakenSkill'),0,40):''}${cat.awakening?checkbox('awakeningUnlocked',t('awaken')):''}</div></div><div class="hero-sheet-note">${esc(t('saved'))}</div>`;
    if(selectedTab==='wall')return `<div class="hero-tab-panel hero-tab-wall"><div class="hero-tab-art">${uiIcon('wall')}</div><div class="hero-game-stats">${number('wallOfHonorLevel',t('wallLevel'),0,999)}${number('monsterDamagePct',t('monster'),0,'','0.01')}${number('pveDamagePct',t('pve'),0,'','0.01')}</div></div><div class="hero-sheet-note">Le niveau du Mur d’honneur est enregistré par héros. Les bonus de type vérifiés restent gérés séparément par le moteur afin d’éviter un double comptage.</div>`;
    return `<div class="hero-tab-panel hero-tab-attributes"><div class="hero-game-stats">${number('displayedPower',t('power'))}${number('displayedAttack',t('attack'))}${number('displayedDefense',t('defense'))}${number('displayedHp',t('hp'))}${number('level',t('level'),1,175)}${number('stars',t('stars'),0,5,'0.2')}</div></div>`;
  }

  function renderSheet(){
    const cat=catalog.find(h=>h.id===selectedId);if(!cat)return;const own=ownedHero(cat);const d=own?.data||{};const {backdrop,sheet}=ensureSheet();
    const rarity=d.rarity||cat.rarity;const title=cat.title?.[locale()]||cat.title?.en||'';
    const tabs=[['attributes',t('attributes')],['grade',t('grade')],['weapon',t('weapon')],['wall',t('wall')]];
    const statChip=(kind,value,label)=>`<div class="hero-stat-chip stat-${kind}"><i>${uiIcon(kind)}</i><span><strong>${fmt(value)}</strong><small>${esc(label)}</small></span></div>`;
    sheet.innerHTML=`<div class="hero-sheet-hero"><div class="hero-sheet-tech"></div><div class="hero-sheet-portrait rarity-${esc(rarity)}">${portrait(cat)}</div><div class="hero-sheet-title">${title?`<small>${esc(title)}</small>`:''}<h3>${esc(cat.name)}</h3><div class="hero-sheet-tags"><span class="hero-sheet-tag">${troopSvg(cat.troopType)} ${esc(t(cat.troopType))}</span><span class="hero-sheet-tag">${roleIcon(cat.role)} ${esc(roleLabel(cat.role))}</span><span class="hero-sheet-tag rarity-tag">${esc(rarity)}</span>${cat.awakening?`<span class="hero-sheet-tag awakening-tag">✦ ${esc(t('awakening'))}</span>`:''}</div></div><button id="heroSheetClose" class="hero-sheet-close" type="button">×</button><button id="heroOwnedAction" class="hero-owned-action ${own?'remove':''}" type="button">${esc(own?t('remove'):t('add'))}</button></div>
      <div class="hero-sheet-tabs">${tabs.map(([id,label])=>`<button class="hero-sheet-tab ${selectedTab===id?'active':''}" data-sheet-tab="${id}" type="button"><i>${uiIcon(id)}</i><span>${esc(label)}</span></button>`).join('')}</div>
      <div class="hero-sheet-body"><div class="hero-stat-banner">${statChip('power',d.displayedPower,t('power'))}${statChip('attack',d.displayedAttack,t('attack'))}${statChip('defense',d.displayedDefense,t('defense'))}${statChip('hp',d.displayedHp,t('hp'))}</div><div class="hero-star-row"><span class="hero-star-wing"></span><strong>${stars(d.stars)}</strong><span class="hero-star-wing"></span></div>${own?tabFields(cat,d,true):`<div class="hero-sheet-note">${esc(t('notOwned'))}</div>`}<button id="heroAdvancedJump" class="hero-advanced-jump" type="button" ${own?'':'disabled'}>${esc(t('advanced'))}</button><div class="hero-sheet-note">${esc(t('saved'))}</div></div>`;
    bindImageFallbacks(sheet);
    sheet.querySelector('#heroSheetClose').onclick=closeSheet;
    sheet.querySelector('#heroOwnedAction').onclick=async()=>{if(own)removeHero(cat,true);else await addHero(cat,true)};
    sheet.querySelectorAll('[data-sheet-tab]').forEach(b=>b.onclick=()=>{selectedTab=b.dataset.sheetTab;renderSheet()});
    sheet.querySelectorAll('[data-edit-field]').forEach(el=>{
      const handler=()=>editOwnedField(cat,el.dataset.editField,el.type==='checkbox'?el.checked:el.value,el.type==='checkbox');
      el.addEventListener(el.tagName==='SELECT'||el.type==='checkbox'?'change':'input',handler);
      if(el.tagName==='SELECT')el.addEventListener('input',handler);
    });
    const adv=sheet.querySelector('#heroAdvancedJump');if(adv)adv.onclick=()=>jumpAdvanced(cat);
    requestAnimationFrame(()=>{backdrop.classList.add('open');sheet.classList.add('open')});
  }
  function openSheet(id){selectedId=id;selectedTab='attributes';renderSheet();const shell=document.querySelector('#gameHeroRosterV2');if(shell)renderGrid(shell)}

  function hiddenField(index,field){return document.querySelector(`.hero-card[data-index="${index}"] [data-field="${field}"]`)}
  function pushInput(el,value,checkbox=false,structural=false){
    if(!el)return false;if(checkbox)el.checked=!!value;else el.value=value==null?'':String(value);el.dispatchEvent(new Event('input',{bubbles:true}));if(structural)el.dispatchEvent(new Event('change',{bubbles:true}));return true;
  }
  function editOwnedField(cat,field,value,checkbox=false){
    const own=ownedHero(cat);if(!own)return;const el=hiddenField(own.index,field);if(!el)return;pushInput(el,value,checkbox,false);
    const shell=document.querySelector('#gameHeroRosterV2');if(shell&&['level','stars','rarity'].includes(field))renderGrid(shell);
  }
  async function waitField(index,field,timeout=1800){const start=Date.now();while(Date.now()-start<timeout){const el=hiddenField(index,field);if(el)return el;await delay(25)}return null}
  async function setStructural(index,field,value){const el=await waitField(index,field);if(!el)return false;pushInput(el,value,false,true);await delay(80);return true}
  async function addHero(cat,openAfter=true,refreshAfter=true){
    if(ownedHero(cat)){if(openAfter)renderSheet();return true}
    const before=(profile().heroes||[]).length;const add=document.querySelector('#step-heroes #addHero');if(!add)return false;add.click();
    const index=before;await setStructural(index,'heroId',cat.name);await setStructural(index,'troopType',cat.troopType);await setStructural(index,'role',cat.role);
    let el=await waitField(index,'rarity');if(el)pushInput(el,cat.rarity,false,false);
    el=await waitField(index,'level');if(el)pushInput(el,150,false,false);
    el=await waitField(index,'stars');if(el)pushInput(el,5,false,false);
    await delay(120);if(refreshAfter)enhance(true);
    if(openAfter){selectedId=cat.id;renderSheet()}return true
  }
  function removeHero(cat,closeAfter=true,refreshAfter=true){const own=ownedHero(cat);if(!own)return false;const card=document.querySelector(`.hero-card[data-index="${own.index}"]`);const btn=card?.querySelector('[data-action="remove-hero"]');if(closeAfter)closeSheet();if(btn)btn.click();if(refreshAfter)setTimeout(()=>enhance(true),80);return !!btn}
  function jumpAdvanced(cat){const own=ownedHero(cat);if(!own)return;closeSheet();const details=document.querySelector('.legacy-hero-editor');if(details)details.open=true;setTimeout(()=>document.querySelector(`.hero-card[data-index="${own.index}"]`)?.scrollIntoView({behavior:'smooth',block:'start'}),120)}

  function enhance(force=false){
    if(enhancing)return;const step=document.querySelector('#step-heroes');if(!step)return;if(!force&&step.querySelector('#gameHeroRosterV2'))return;enhancing=true;
    try{
      step.classList.add('hero-roster-enhanced');
      let legacy=step.querySelector('.legacy-hero-editor');
      if(!legacy){legacy=document.createElement('details');legacy.className='legacy-hero-editor';const summary=document.createElement('summary');summary.textContent=t('advancedTitle');legacy.appendChild(summary);const toolbar=[...step.children].find(x=>x.classList?.contains('toolbar'));const list=step.querySelector(':scope > #heroList');if(toolbar)legacy.appendChild(toolbar);if(list)legacy.appendChild(list);step.appendChild(legacy)}
      let shell=step.querySelector('#gameHeroRosterV2');if(!shell){shell=document.createElement('section');shell.id='gameHeroRosterV2';shell.className='game-roster-v2';const heading=step.querySelector('.step-heading');if(heading)heading.insertAdjacentElement('afterend',shell);else step.prepend(shell)}
      renderRoster(shell);
    }finally{enhancing=false}
  }

  async function init(){
    try{const r=await fetch(CATALOG_URL,{cache:'no-store'});if(!r.ok)throw new Error(CATALOG_URL);catalog=(await r.json()).heroes||[];}catch(e){console.error('WfGg hero roster catalog',e);return}
    const obs=new MutationObserver(()=>queueMicrotask(()=>enhance(false)));obs.observe(document.body,{childList:true,subtree:true});
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>enhance(false),{once:true});else enhance(false);
  }
  init();
  window.WfGgHeroRosterV2=Object.freeze({version:'3.0.0',catalog:()=>catalog.slice(),openHero:id=>openSheet(id),refresh:()=>enhance(true),selectionMode:()=>selectionMode});
})();