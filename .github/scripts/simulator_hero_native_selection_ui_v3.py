from pathlib import Path

JS=Path('simulator/hero-roster-v2.js')
CSS=Path('simulator/hero-roster-v2.css')
s=JS.read_text(encoding='utf-8')

s=s.replace("  let selectionMode=true;\n  let enhancing=false;", "  let selectionMode=false;\n  let bulkBusy=false;\n  let enhancing=false;", 1)

translations={
  "details:'Ouvrir la fiche'":"details:'Ouvrir la fiche',selectAll:'Sélectionner tout',clearAll:'Tout désélectionner',done:'Terminer'",
  "details:'Open details'":"details:'Open details',selectAll:'Select all',clearAll:'Clear all',done:'Done'",
  "details:'Apri scheda'":"details:'Apri scheda',selectAll:'Seleziona tutto',clearAll:'Deseleziona tutto',done:'Fine'",
  "details:'Abrir ficha'":"details:'Abrir ficha',selectAll:'Seleccionar todo',clearAll:'Deseleccionar todo',done:'Listo'"
}
for old,new in translations.items():
  if old not in s: raise SystemExit(f'translation marker missing: {old}')
  s=s.replace(old,new,1)

old_role="  function roleIcon(role){return role==='defense'?'🛡':role==='support'?'✚':'⚔'}"
new_role="""  function roleIcon(role){
    if(role==='defense')return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2 27 6v8c0 8.1-4.7 13.1-11 16C9.7 27.1 5 22.1 5 14V6l11-4zm0 5-6 2.2v5c0 4.7 2.3 8 6 10.2 3.7-2.2 6-5.5 6-10.2v-5L16 7z"/></svg>';
    if(role==='support')return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M12 3h8v9h9v8h-9v9h-8v-9H3v-8h9V3z"/></svg>';
    return '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="m25.8 3.4 2.8 2.8-8.1 8.1 2.5 2.5-3.2 3.2-2.5-2.5-6.7 6.7 2.7 2.7-2.7 2.7-8.1-8.1 2.7-2.7 2.7 2.7 6.7-6.7-2.5-2.5 3.2-3.2 2.5 2.5 8.1-8.1z"/></svg>';
  }"""
if old_role not in s: raise SystemExit('role icon marker missing')
s=s.replace(old_role,new_role,1)

marker="  function portrait(cat){"
if marker not in s: raise SystemExit('portrait marker missing')
icon_helpers="""  function uiIcon(kind){
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

"""
s=s.replace(marker,icon_helpers+marker,1)

a=s.index("  function cardHtml(cat){")
b=s.index("  async function toggleOwned(cat){")
new_card="""  function cardHtml(cat){
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

"""
s=s[:a]+new_card+s[b:]

a=s.index("  async function toggleOwned(cat){")
b=s.index("  function ensureSheet(){")
new_interaction="""  async function toggleOwned(cat){
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

"""
s=s[:a]+new_interaction+s[b:]

a=s.index("  function tabFields(cat,d,owned){")
b=s.index("  function renderSheet(){")
new_fields="""  function tabFields(cat,d,owned){
    const number=(field,label,min=0,max='',step='1')=>`<label class="hero-game-field field-${field}"><span class="hero-field-label"><i class="hero-field-icon">${fieldIcon(field)}</i>${esc(label)}</span><input data-edit-field="${field}" type="number" min="${min}" ${max!==''?`max="${max}"`:''} step="${step}" value="${esc(d[field]??'')}" ${owned?'':'disabled'}></label>`;
    const checkbox=(field,label)=>`<label class="hero-game-field wide field-${field}"><span class="hero-field-label"><i class="hero-field-icon">${uiIcon('grade')}</i>${esc(label)}</span><input data-edit-field="${field}" type="checkbox" ${d[field]?'checked':''} ${owned?'':'disabled'}></label>`;
    if(selectedTab==='grade')return `<div class="hero-tab-panel hero-tab-grade"><div class="hero-game-stats"><label class="hero-game-field field-rarity"><span class="hero-field-label"><i class="hero-field-icon">${uiIcon('rarity')}</i>${esc(t('rarity'))}</span><select data-edit-field="rarity" ${owned?'':'disabled'}>${['UR','SSR','SR','R'].map(x=>`<option value="${x}" ${(d.rarity||cat.rarity)===x?'selected':''}>${x}</option>`).join('')}</select></label>${number('level',t('level'),1,175)}${number('stars',t('stars'),0,5,'0.2')}${cat.promotableTo?`<div class="hero-game-field hero-promotion-tile"><span class="hero-field-label"><i class="hero-field-icon">${uiIcon('grade')}</i>${esc(t('promotion'))}</span><strong>${esc(cat.rarity)} → ${esc(cat.promotableTo)} · S${esc(cat.promotionSeason)}</strong></div>`:''}${cat.awakening?checkbox('awakeningUnlocked',t('awaken')):''}${cat.awakening?number('awakeningStars',t('awakenStars'),0,5):''}${cat.awakening?number('awakeningTier',t('awakenTier'),0,99):''}</div></div>`;
    if(selectedTab==='weapon')return `<div class="hero-tab-panel hero-tab-weapon"><div class="hero-tab-art">${uiIcon('weapon')}</div><div class="hero-game-stats">${number('exclusiveWeaponLevel',t('weaponLevel'),0,40)}${cat.awakening?number('awakeningSkillLevel',t('awakenSkill'),0,40):''}${cat.awakening?checkbox('awakeningUnlocked',t('awaken')):''}</div></div><div class="hero-sheet-note">${esc(t('saved'))}</div>`;
    if(selectedTab==='wall')return `<div class="hero-tab-panel hero-tab-wall"><div class="hero-tab-art">${uiIcon('wall')}</div><div class="hero-game-stats">${number('wallOfHonorLevel',t('wallLevel'),0,999)}${number('monsterDamagePct',t('monster'),0,'','0.01')}${number('pveDamagePct',t('pve'),0,'','0.01')}</div></div><div class="hero-sheet-note">Le niveau du Mur d’honneur est enregistré par héros. Les bonus de type vérifiés restent gérés séparément par le moteur afin d’éviter un double comptage.</div>`;
    return `<div class="hero-tab-panel hero-tab-attributes"><div class="hero-game-stats">${number('displayedPower',t('power'))}${number('displayedAttack',t('attack'))}${number('displayedDefense',t('defense'))}${number('displayedHp',t('hp'))}${number('level',t('level'),1,175)}${number('stars',t('stars'),0,5,'0.2')}</div></div>`;
  }

"""
s=s[:a]+new_fields+s[b:]

a=s.index("  function renderSheet(){")
b=s.index("  function openSheet(id){")
new_sheet="""  function renderSheet(){
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
"""
s=s[:a]+new_sheet+s[b:]

old_add="""  async function addHero(cat,openAfter=true){
    if(ownedHero(cat)){if(openAfter)renderSheet();return}
    const before=(profile().heroes||[]).length;const add=document.querySelector('#step-heroes #addHero');if(!add)return;add.click();
    const index=before;await setStructural(index,'heroId',cat.name);await setStructural(index,'troopType',cat.troopType);await setStructural(index,'role',cat.role);
    let el=await waitField(index,'rarity');if(el)pushInput(el,cat.rarity,false,false);
    el=await waitField(index,'level');if(el)pushInput(el,150,false,false);
    el=await waitField(index,'stars');if(el)pushInput(el,5,false,false);
    await delay(120);enhance(true);
    if(openAfter){selectedId=cat.id;renderSheet()}
  }
  function removeHero(cat,closeAfter=true){const own=ownedHero(cat);if(!own)return;const card=document.querySelector(`.hero-card[data-index="${own.index}"]`);const btn=card?.querySelector('[data-action="remove-hero"]');if(closeAfter)closeSheet();if(btn)btn.click();setTimeout(()=>enhance(true),80)}"""
new_add="""  async function addHero(cat,openAfter=true,refreshAfter=true){
    if(ownedHero(cat)){if(openAfter)renderSheet();return true}
    const before=(profile().heroes||[]).length;const add=document.querySelector('#step-heroes #addHero');if(!add)return false;add.click();
    const index=before;await setStructural(index,'heroId',cat.name);await setStructural(index,'troopType',cat.troopType);await setStructural(index,'role',cat.role);
    let el=await waitField(index,'rarity');if(el)pushInput(el,cat.rarity,false,false);
    el=await waitField(index,'level');if(el)pushInput(el,150,false,false);
    el=await waitField(index,'stars');if(el)pushInput(el,5,false,false);
    await delay(120);if(refreshAfter)enhance(true);
    if(openAfter){selectedId=cat.id;renderSheet()}return true
  }
  function removeHero(cat,closeAfter=true,refreshAfter=true){const own=ownedHero(cat);if(!own)return false;const card=document.querySelector(`.hero-card[data-index="${own.index}"]`);const btn=card?.querySelector('[data-action="remove-hero"]');if(closeAfter)closeSheet();if(btn)btn.click();if(refreshAfter)setTimeout(()=>enhance(true),80);return !!btn}"""
if old_add not in s: raise SystemExit('add/remove hero block missing')
s=s.replace(old_add,new_add,1)
s=s.replace("window.WfGgHeroRosterV2=Object.freeze({version:'2.2.0'", "window.WfGgHeroRosterV2=Object.freeze({version:'3.0.0'",1)

for token in ['hero-card-info','data-hero-info','hero-owned-toggle','data-hero-toggle','heroSelectionMode','game-roster-mode','game-selection-toggle']:
  if token in s: raise SystemExit(f'legacy card selection control still present: {token}')
if '480' not in s or 'heroSelectAll' not in s: raise SystemExit('long-press/select-all patch missing')
JS.write_text(s,encoding='utf-8')

CSS.write_text(r'''.hero-roster-enhanced .step-heading .primary-button{display:none}
.hero-roster-enhanced>.toolbar{display:none}
.hero-roster-enhanced>.entry-list{display:none}
.game-roster-v2{display:grid;gap:13px;user-select:none;-webkit-user-select:none}
.game-roster-head{display:flex;gap:9px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.game-roster-search{flex:1;min-width:180px;position:relative}
.game-roster-search input{width:100%;border:1px solid #53647c;background:linear-gradient(180deg,#202c40,#141d2d);color:#fff;border-radius:8px;padding:11px 13px 11px 38px;font:inherit;box-sizing:border-box;box-shadow:inset 0 1px 2px #0a0f18,0 1px rgba(255,255,255,.07)}
.game-roster-search:before{content:'⌕';position:absolute;left:13px;top:7px;font-size:22px;color:#c5d4e7}
.game-roster-head-actions{display:flex;align-items:center;gap:7px}
.game-roster-count{padding:8px 10px;border-radius:7px;background:linear-gradient(180deg,#33435c,#202c40);border:1px solid #62748c;font-size:11px;font-weight:900;color:#edf4ff;box-shadow:inset 0 1px rgba(255,255,255,.1)}
.hero-select-all{min-height:35px;border:1px solid #b06412;border-radius:7px;background:linear-gradient(180deg,#ffb33b,#e77709);color:#fff;padding:7px 10px;font-weight:1000;font-size:11px;box-shadow:0 2px 0 #8b3e00;cursor:pointer}
.hero-selection-done{width:36px;height:36px;border:1px solid #55da9a;border-radius:50%;background:linear-gradient(180deg,#35d98a,#16995d);color:#fff;font-weight:1000;font-size:18px;box-shadow:0 2px 0 #096239;cursor:pointer}
.hero-select-all:disabled{opacity:.5}
.game-type-tabs{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;background:linear-gradient(180deg,#29374d,#192335);border-radius:9px;padding:5px;border:1px solid #53627a;box-shadow:inset 0 1px rgba(255,255,255,.08),0 2px 5px rgba(0,0,0,.25)}
.game-type-tab{border:1px solid #465770;border-radius:6px;background:linear-gradient(180deg,#394a64,#26354b);color:#e4ebf5;min-height:45px;display:flex;align-items:center;justify-content:center;gap:6px;font-weight:1000;cursor:pointer;transition:transform .14s ease,filter .14s ease,box-shadow .14s ease;text-shadow:0 1px #0b1018}
.game-type-tab:active{transform:scale(.96)}
.game-type-tab.active{background:linear-gradient(180deg,#ffae32,#e87308);border-color:#ffc35d;color:white;box-shadow:inset 0 1px #ffe0a1,0 3px 0 #914000,0 6px 14px rgba(238,109,0,.2)}
.game-type-tab svg{width:24px;height:24px;fill:currentColor}
.game-hero-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;padding:8px;background:linear-gradient(180deg,#c9cdd1,#aeb4bb);border-radius:7px;border:1px solid #7f858d;box-shadow:inset 0 1px 0 #f8fafb,inset 0 0 0 2px rgba(255,255,255,.22),0 3px 8px rgba(0,0,0,.18)}
.game-hero-card{position:relative;aspect-ratio:.78;overflow:hidden;border:3px solid #d49a3c;background:linear-gradient(155deg,#925615,#e6a64d 42%,#82450d);box-shadow:0 2px 0 #5a3311,0 5px 10px rgba(0,0,0,.26);cursor:pointer;padding:0;transition:transform .14s ease,filter .16s ease,box-shadow .16s ease;color:#fff;outline:none;touch-action:pan-y;clip-path:polygon(7px 0,calc(100% - 7px) 0,100% 7px,100% calc(100% - 7px),calc(100% - 7px) 100%,7px 100%,0 calc(100% - 7px),0 7px)}
.game-hero-card.rarity-SSR{border-color:#a276e8;background:linear-gradient(155deg,#5b397f,#9f6fe0 45%,#43245e)}
.game-hero-card.rarity-SR{border-color:#43a9de;background:linear-gradient(155deg,#215c84,#4fb4e9 45%,#173e5c)}
.game-hero-card:active{transform:scale(.96)}
.game-hero-card:focus-visible{box-shadow:0 0 0 3px #72b8ff,0 0 20px rgba(74,158,255,.45)}
.game-hero-card.selected{box-shadow:0 0 0 3px #ffdf66,0 0 22px rgba(255,205,62,.55)}
.hero-card-portrait{position:absolute;inset:0 0 35px;background:radial-gradient(circle at 50% 32%,rgba(255,255,255,.23),transparent 38%),linear-gradient(160deg,#52647d,#1d263b);display:grid;place-items:center;overflow:hidden;transition:filter .18s ease}
.hero-card-portrait img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .22s ease}
.game-hero-card:hover .hero-card-portrait img{transform:scale(1.035)}
.game-hero-grid.is-selecting .game-hero-card .hero-card-portrait{filter:grayscale(.92) saturate(.35) brightness(.72)}
.game-hero-grid.is-selecting .game-hero-card.owned .hero-card-portrait{filter:grayscale(.38) saturate(.85) brightness(.85)}
.game-hero-card.selection-mode.owned{box-shadow:0 0 0 3px #35d583,0 4px 10px rgba(0,0,0,.3),0 0 16px rgba(53,213,131,.35)}
.hero-select-dot{position:absolute;left:5px;top:5px;z-index:12;width:24px;height:24px;border-radius:50%;display:grid;place-items:center;border:2px solid rgba(255,255,255,.92);background:rgba(30,39,53,.72);color:white;font-size:15px;font-weight:1000;box-shadow:0 2px 6px rgba(0,0,0,.4)}
.hero-select-dot.on{background:#25cb76;border-color:#b8ffdc;color:#052718}
.hero-fallback{font-size:30px;font-weight:1000;text-shadow:0 2px 8px rgba(0,0,0,.45);letter-spacing:-1px}
.hero-role-badge{position:absolute;left:5px;top:5px;z-index:6;width:24px;height:24px;border-radius:5px;background:rgba(26,39,58,.88);display:grid;place-items:center;border:1px solid rgba(255,255,255,.62)}
.game-hero-card.selection-mode .hero-role-badge{top:34px}
.hero-role-badge svg{width:16px;height:16px;fill:#fff}
.hero-rarity-badge{position:absolute;right:5px;bottom:38px;z-index:6;font-size:9px;font-weight:1000;padding:2px 5px;border-radius:4px;background:rgba(0,0,0,.58);border:1px solid rgba(255,255,255,.35)}
.hero-type-mini{position:absolute;left:5px;bottom:38px;z-index:6;width:20px;height:20px;display:grid;place-items:center;border-radius:4px;background:rgba(17,24,38,.82)}
.hero-type-mini svg{width:16px;height:16px;fill:#fff}
.hero-card-footer{position:absolute;left:0;right:0;bottom:0;height:38px;background:linear-gradient(180deg,rgba(15,20,31,.2),#0d1523);padding:3px 5px 4px;display:flex;flex-direction:column;justify-content:flex-end;border-top:1px solid rgba(255,255,255,.16)}
.hero-card-name{font-size:10px;font-weight:1000;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-shadow:0 1px 2px #000}
.hero-card-meta{display:flex;align-items:center;justify-content:space-between;font-size:9px;color:#ffd447;font-weight:900}
.hero-card-stars{letter-spacing:-1px;white-space:nowrap}
.hero-promote-mark{position:absolute;right:4px;top:5px;z-index:6;background:linear-gradient(180deg,#41e495,#18ad65);color:#052a18;border-radius:4px;padding:2px 4px;font-size:8px;font-weight:1000;border:1px solid #82ffc0}
.game-roster-empty{grid-column:1/-1;color:#3a4354;text-align:center;padding:30px 10px;font-weight:800}
.hero-game-sheet-backdrop{position:fixed;inset:0;background:rgba(2,5,14,.78);backdrop-filter:blur(6px);z-index:1200;opacity:0;pointer-events:none;transition:opacity .2s ease}
.hero-game-sheet-backdrop.open{opacity:1;pointer-events:auto}
.hero-game-sheet{position:fixed;z-index:1201;left:50%;bottom:0;width:min(720px,100%);max-height:94vh;overflow:auto;transform:translate(-50%,104%);transition:transform .26s cubic-bezier(.22,.9,.24,1);background:linear-gradient(180deg,#28364b,#172235 31%,#111a29);border-radius:14px 14px 0 0;border:1px solid #65758c;box-shadow:0 -18px 50px rgba(0,0,0,.58);color:#fff}
.hero-game-sheet.open{transform:translate(-50%,0)}
.hero-sheet-hero{position:relative;display:grid;grid-template-columns:136px 1fr;gap:14px;align-items:end;padding:18px 16px 14px;overflow:hidden;background:radial-gradient(circle at 18% 20%,rgba(91,174,255,.28),transparent 34%),linear-gradient(135deg,#3a4b64,#243249 62%,#1d293d);border-bottom:2px solid #697c97}
.hero-sheet-tech{position:absolute;inset:0;pointer-events:none;opacity:.28;background:linear-gradient(120deg,transparent 0 48%,rgba(113,185,255,.22) 48% 49%,transparent 49% 100%),repeating-linear-gradient(90deg,transparent 0 34px,rgba(255,255,255,.04) 35px 36px)}
.hero-sheet-portrait{position:relative;height:164px;overflow:hidden;border:3px solid #e2a64b;background:linear-gradient(135deg,#516180,#232c42);display:grid;place-items:center;font-size:40px;font-weight:1000;clip-path:polygon(10px 0,100% 0,100% calc(100% - 10px),calc(100% - 10px) 100%,0 100%,0 10px);box-shadow:0 5px 14px rgba(0,0,0,.4)}
.hero-sheet-portrait.rarity-SSR{border-color:#b789f3}.hero-sheet-portrait.rarity-SR{border-color:#55c3f2}
.hero-sheet-portrait img{width:100%;height:100%;object-fit:cover}
.hero-sheet-title{position:relative;z-index:2;padding-bottom:38px}
.hero-sheet-title small{display:block;color:#8ed3ff;font-weight:1000;font-size:12px;margin-bottom:2px;text-transform:uppercase;letter-spacing:.5px}
.hero-sheet-title h3{margin:0 0 9px;font-size:29px;line-height:1;text-shadow:0 2px 4px #000}
.hero-sheet-tags{display:flex;gap:5px;flex-wrap:wrap}
.hero-sheet-tag{display:inline-flex;align-items:center;gap:5px;padding:5px 7px;border-radius:5px;background:linear-gradient(180deg,rgba(25,39,58,.92),rgba(12,20,32,.92));border:1px solid #596c85;font-size:10px;font-weight:900;box-shadow:inset 0 1px rgba(255,255,255,.08)}
.hero-sheet-tag svg{width:17px;height:17px;fill:currentColor}
.hero-sheet-tag.rarity-tag{color:#ffd366}.hero-sheet-tag.awakening-tag{color:#8ce4ff}
.hero-sheet-close{position:absolute;right:10px;top:9px;width:34px;height:34px;border-radius:6px;border:1px solid #687a91;background:linear-gradient(180deg,#34445c,#1a2638);color:white;font-size:22px;cursor:pointer;z-index:5;box-shadow:0 2px 0 #0c121d}
.hero-owned-action{position:absolute;right:14px;bottom:14px;border:1px solid #71f0b0;border-radius:6px;padding:9px 12px;background:linear-gradient(180deg,#35d98a,#16995d);color:#fff;font-weight:1000;box-shadow:0 3px 0 #096239;cursor:pointer;z-index:5}
.hero-owned-action.remove{background:linear-gradient(180deg,#ef6175,#c52f48);border-color:#ff93a3;box-shadow:0 3px 0 #7e1729}
.hero-sheet-tabs{display:grid;grid-template-columns:repeat(4,1fr);gap:3px;padding:5px;background:#131d2b;position:sticky;top:0;z-index:4;border-bottom:1px solid #4e5d72}
.hero-sheet-tab{border:1px solid #465873;border-radius:5px;background:linear-gradient(180deg,#33445e,#233149);color:#d4dfed;padding:7px 3px 6px;font-weight:1000;font-size:10px;cursor:pointer;display:grid;justify-items:center;gap:2px;text-shadow:0 1px #070b11}
.hero-sheet-tab i{width:24px;height:24px;display:grid;place-items:center}
.hero-sheet-tab svg{width:22px;height:22px;fill:currentColor}
.hero-sheet-tab.active{background:linear-gradient(180deg,#ffad32,#e67008);border-color:#ffc96f;color:#fff;box-shadow:inset 0 1px #ffe2a5,0 2px 0 #8f3f00}
.hero-sheet-body{padding:12px 14px 25px;background:linear-gradient(180deg,#1b2739,#121b2b)}
.hero-stat-banner{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin-bottom:9px}
.hero-stat-chip{min-width:0;background:linear-gradient(180deg,#33435c,#202d43);padding:7px 5px;display:flex;align-items:center;gap:6px;border:1px solid #536781;box-shadow:inset 0 1px rgba(255,255,255,.09),0 2px 4px rgba(0,0,0,.2);clip-path:polygon(5px 0,100% 0,100% calc(100% - 5px),calc(100% - 5px) 100%,0 100%,0 5px)}
.hero-stat-chip i{width:25px;height:25px;flex:0 0 25px;display:grid;place-items:center;border-radius:50%;background:#172237;border:1px solid #607795;color:#87caff}
.hero-stat-chip svg{width:16px;height:16px;fill:currentColor}
.hero-stat-chip span{min-width:0}.hero-stat-chip strong{display:block;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.hero-stat-chip small{display:block;font-size:8px;color:#b9c7da;text-transform:uppercase}
.hero-stat-chip.stat-attack i{color:#ff9d62}.hero-stat-chip.stat-defense i{color:#77bdff}.hero-stat-chip.stat-hp i{color:#ff7185}.hero-stat-chip.stat-power i{color:#ffd65e}
.hero-star-row{display:flex;gap:8px;align-items:center;justify-content:center;padding:7px 0 10px;color:#ffd435;font-size:21px;text-shadow:0 1px 3px #000}
.hero-star-row strong{letter-spacing:-1px}.hero-star-wing{height:1px;width:48px;background:linear-gradient(90deg,transparent,#d39a37)}.hero-star-wing:last-child{transform:scaleX(-1)}
.hero-tab-panel{position:relative;padding:9px;background:linear-gradient(180deg,rgba(48,62,84,.92),rgba(27,38,56,.94));border:1px solid #52657e;box-shadow:inset 0 1px rgba(255,255,255,.08),0 3px 8px rgba(0,0,0,.24);overflow:hidden}
.hero-tab-panel:before{content:'';position:absolute;right:-18px;top:-25px;width:90px;height:90px;border:1px solid rgba(111,190,255,.14);transform:rotate(45deg)}
.hero-tab-art{position:absolute;right:10px;top:8px;width:56px;height:56px;opacity:.12;pointer-events:none}.hero-tab-art svg{width:100%;height:100%;fill:#b9ddff}
.hero-game-stats{position:relative;display:grid;grid-template-columns:repeat(2,1fr);gap:7px;z-index:1}
.hero-game-field{display:grid;gap:5px;background:linear-gradient(180deg,#26364d,#1a2639);border:1px solid #4c607b;padding:8px;clip-path:polygon(5px 0,100% 0,100% calc(100% - 5px),calc(100% - 5px) 100%,0 100%,0 5px)}
.hero-field-label{display:flex!important;align-items:center;gap:6px;font-size:10px!important;color:#dce8f6!important;font-weight:900!important;text-transform:uppercase}
.hero-field-icon{width:19px;height:19px;flex:0 0 19px;display:grid;place-items:center;color:#72c8ff}.hero-field-icon svg{width:16px;height:16px;fill:currentColor}
.hero-game-field input,.hero-game-field select{width:100%;box-sizing:border-box;border:1px solid #52677f;border-radius:4px;background:linear-gradient(180deg,#121d2d,#0d1624);color:#fff;padding:9px;font:inherit;font-weight:900;box-shadow:inset 0 1px 2px #060a11}
.hero-game-field input:focus,.hero-game-field select:focus{outline:1px solid #65c2ff;border-color:#65c2ff}
.hero-game-field.wide{grid-column:1/-1}.hero-promotion-tile strong{font-size:16px;color:#ffd268;padding:7px 2px}
.hero-sheet-note{padding:9px 11px;border-left:3px solid #57b9ff;background:rgba(74,144,214,.1);color:#cfe7ff;font-size:10px;line-height:1.45;margin-top:9px}
.hero-advanced-jump{width:100%;border:1px solid #526782;border-radius:5px;background:linear-gradient(180deg,#31425c,#213049);color:#e9f1fb;padding:10px;font-weight:900;cursor:pointer;margin-top:9px;box-shadow:0 2px 0 #111a28}
.legacy-hero-editor{margin-top:12px;border:1px solid rgba(255,255,255,.09);border-radius:8px;background:rgba(18,22,34,.5)}
.legacy-hero-editor>summary{cursor:pointer;padding:12px 14px;font-weight:900;color:#c9d1e3}
.legacy-hero-editor>.toolbar,.legacy-hero-editor>.entry-list{padding:0 12px 12px}
@media(max-width:520px){.game-roster-head{align-items:stretch}.game-roster-head-actions{width:100%;justify-content:flex-end}.game-roster-head.selecting .game-roster-search{flex-basis:100%}.hero-select-all{flex:1}.game-roster-count{margin-left:auto}.game-hero-grid{gap:5px;padding:6px}.hero-card-name{font-size:9px}.hero-card-meta{font-size:8px}.hero-game-sheet{max-height:97vh;border-radius:10px 10px 0 0}.hero-sheet-hero{grid-template-columns:112px 1fr;padding:14px 11px 11px}.hero-sheet-portrait{height:142px}.hero-sheet-title{padding-bottom:40px}.hero-sheet-title h3{font-size:24px}.hero-sheet-tag{font-size:9px;padding:4px 5px}.hero-owned-action{right:10px;bottom:10px;font-size:10px;padding:8px}.hero-sheet-tab{font-size:9px;padding:6px 1px}.hero-sheet-tab i{width:22px;height:22px}.hero-stat-banner{grid-template-columns:1fr 1fr}.hero-stat-chip{padding:7px}.hero-game-stats{grid-template-columns:1fr 1fr}.hero-sheet-body{padding:10px 10px 22px}}
''',encoding='utf-8')

print('hero UI patch applied')
