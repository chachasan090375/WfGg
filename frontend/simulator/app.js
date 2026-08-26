(() => {
  'use strict';

  const STORAGE_KEY = 'wfgg-simulator-profile-v1';
  const STEPS = ['account','heroes','gear','research','season','summary'];
  const UI = {
    fr:{topTitle:'Simulateur',introEyebrow:'Module autonome',introTitle:'Construisez votre compte',introText:'Renseignez uniquement les éléments qui peuvent changer le classement relatif de vos équipes. Vos données restent enregistrées localement sur cet appareil.',termTitle:'Terminologie Last War contrôlée',termText:'Les libellés non confirmés dans le client du jeu restent signalés comme provisoires. Le moteur stocke des IDs sémantiques indépendants des traductions.',previous:'Précédent',next:'Suivant',pending:'à confirmer',steps:['Compte','Héros','Équipements','Recherches','Saison / Buffs','Résumé'],addHero:'Ajouter un héros',addGear:'Ajouter un équipement',saved:'Sauvegardé',heroName:'Nom du héros',heroType:'Type',heroRole:'Rôle',heroLevel:'Niveau',heroStars:'Étoiles',heroEw:'Arme exclusive · niveau',heroWall:'Wall of Honor · niveau',heroAwakening:'Awakening débloqué',gearEyebrow:'Équipement',gearId:'Identifiant / nom',gearSlot:'Emplacement',rarity:'Rareté',level:'Niveau',stars:'Étoiles',promotion:'Promotion',assignedHero:'Héros équipé'},
    en:{topTitle:'Simulator',introEyebrow:'Standalone module',introTitle:'Build your account',introText:'Enter only elements that can change the relative ranking of your squads. Your data stays stored locally on this device.',termTitle:'Controlled Last War terminology',termText:'Labels not confirmed in the game client remain marked as provisional. The engine stores semantic IDs independently from translations.',previous:'Previous',next:'Next',pending:'pending',steps:['Account','Heroes','Gear','Research','Season / Buffs','Summary'],addHero:'Add hero',addGear:'Add gear',saved:'Saved',heroName:'Hero name',heroType:'Type',heroRole:'Role',heroLevel:'Level',heroStars:'Stars',heroEw:'Exclusive Weapon · level',heroWall:'Wall of Honor · level',heroAwakening:'Awakening unlocked',gearEyebrow:'Gear',gearId:'Identifier / name',gearSlot:'Slot',rarity:'Rarity',level:'Level',stars:'Stars',promotion:'Promotion',assignedHero:'Equipped hero'},
    it:{topTitle:'Simulatore',introEyebrow:'Modulo autonomo',introTitle:'Configura il tuo account',introText:'Inserisci solo gli elementi che possono cambiare la classifica relativa delle squadre. I dati restano salvati localmente su questo dispositivo.',termTitle:'Terminologia Last War controllata',termText:'Le etichette non confermate nel client del gioco restano indicate come provvisorie. Il motore usa ID semantici indipendenti dalle traduzioni.',previous:'Indietro',next:'Avanti',pending:'da confermare',steps:['Account','Eroi','Equipaggiamento','Ricerche','Stagione / Buff','Riepilogo'],addHero:'Aggiungi eroe',addGear:'Aggiungi equipaggiamento',saved:'Salvato',heroName:'Nome eroe',heroType:'Tipo',heroRole:'Ruolo',heroLevel:'Livello',heroStars:'Stelle',heroEw:'Arma esclusiva · livello',heroWall:'Wall of Honor · livello',heroAwakening:'Awakening sbloccato',gearEyebrow:'Equipaggiamento',gearId:'Identificatore / nome',gearSlot:'Slot',rarity:'Rarità',level:'Livello',stars:'Stelle',promotion:'Promozione',assignedHero:'Eroe equipaggiato'},
    es:{topTitle:'Simulador',introEyebrow:'Módulo autónomo',introTitle:'Configura tu cuenta',introText:'Introduce solo los elementos que pueden cambiar la clasificación relativa de tus escuadras. Los datos se guardan localmente en este dispositivo.',termTitle:'Terminología Last War controlada',termText:'Las etiquetas no confirmadas en el cliente del juego siguen marcadas como provisionales. El motor usa IDs semánticos independientes de las traducciones.',previous:'Anterior',next:'Siguiente',pending:'por confirmar',steps:['Cuenta','Héroes','Equipamiento','Investigación','Temporada / Buffs','Resumen'],addHero:'Añadir héroe',addGear:'Añadir equipamiento',saved:'Guardado',heroName:'Nombre del héroe',heroType:'Tipo',heroRole:'Rol',heroLevel:'Nivel',heroStars:'Estrellas',heroEw:'Arma exclusiva · nivel',heroWall:'Wall of Honor · nivel',heroAwakening:'Awakening desbloqueado',gearEyebrow:'Equipamiento',gearId:'Identificador / nombre',gearSlot:'Ranura',rarity:'Rareza',level:'Nivel',stars:'Estrellas',promotion:'Promoción',assignedHero:'Héroe equipado'}
  };

  const DEFAULT_STATE = {
    locale:'fr',step:0,
    account:{hqLevel:30,activeSquads:3,superMonthlyPass:false,troopTier:'T10',troopCenters:{tankLevel:30,aircraftLevel:30,missileLevel:30},marchSizeAdditional:{survivorShirleyBonus:0,decorationsBonus:0}},
    heroes:[],gear:[],research:{},
    season6:{totemLevels:{bearTank:0,eagleAircraft:0,jaguarMissile:0},tacticsCards:{dimensionalCrit:0,frontalSuppression:0,aftermathBurst:0}},
    metadata:{schema:'wfgg-simulator-profile-v1',updatedAt:null}
  };

  let schemas = {};
  let state = loadState();
  let researchTab = 'hero';

  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const esc = value => String(value ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const clone = obj => JSON.parse(JSON.stringify(obj));
  const ui = key => (UI[state.locale] || UI.fr)[key] ?? UI.fr[key] ?? key;

  function loadState(){
    try{
      const raw = JSON.parse(localStorage.getItem(STORAGE_KEY));
      return raw && raw.metadata?.schema === DEFAULT_STATE.metadata.schema ? deepMerge(clone(DEFAULT_STATE), raw) : clone(DEFAULT_STATE);
    }catch(_){return clone(DEFAULT_STATE);}
  }
  function deepMerge(base, extra){
    Object.entries(extra || {}).forEach(([k,v]) => {
      if(v && typeof v === 'object' && !Array.isArray(v) && base[k] && typeof base[k] === 'object' && !Array.isArray(base[k])) deepMerge(base[k],v); else base[k]=v;
    });
    return base;
  }
  function saveState(){
    state.metadata.updatedAt = new Date().toISOString();
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    const el=$('#saveState'); if(el){el.textContent=ui('saved'); el.style.opacity='1'; setTimeout(()=>el.style.opacity='.7',650);}
  }
  async function loadSchemas(){
    const files = {
      account:'data/account-inputs.v1.json', research:'data/research-inputs.v1.json', season:'data/season6-context.v1.json', terminology:'i18n/official-terminology.v1.json', researchTerms:'i18n/research-terminology-audit.v1.json'
    };
    const pairs = await Promise.all(Object.entries(files).map(async ([k,url]) => [k, await fetch(url).then(r => {if(!r.ok) throw new Error(url); return r.json();})]));
    schemas = Object.fromEntries(pairs);
  }

  function setLocale(locale){
    if(!UI[locale]) return;
    state.locale=locale; document.documentElement.lang=locale; saveState(); renderAll();
  }
  function renderStaticI18n(){
    $$('[data-ui]').forEach(el => {const v=ui(el.dataset.ui); if(typeof v==='string') el.textContent=v;});
    $('#topTitle').textContent=ui('topTitle');
    $$('#languageStrip button').forEach(b=>b.classList.toggle('active',b.dataset.lang===state.locale));
  }
  function renderStepNav(){
    $('#stepNav').innerHTML = ui('steps').map((name,i)=>`<button class="step-button ${i===state.step?'active':''}" data-step="${i}" type="button"><span class="step-index">${i+1}</span>${esc(name)}</button>`).join('');
    $$('#stepNav [data-step]').forEach(b=>b.onclick=()=>{state.step=Number(b.dataset.step);saveState();renderAll();scrollToWorkspace();});
  }
  function showStep(){
    STEPS.forEach((s,i)=>$('#step-'+s).classList.toggle('hidden',i!==state.step));
    $('#prevBtn').disabled=state.step===0;
    $('#nextBtn').disabled=state.step===STEPS.length-1;
  }
  function heading(title,text,action=''){return `<div class="step-heading"><div><p class="eyebrow">WfGg</p><h2>${esc(title)}</h2><p class="muted">${esc(text)}</p></div>${action}</div>`;}

  function gameTerm(id){
    const row=schemas.terminology?.terms?.[id]?.[state.locale];
    if(!row) return {label:id,pending:true};
    const pending = row.status==='pending' || row.finalInGame==='pending' || row.display==null;
    return {label:row.display || id,pending};
  }
  function optionTerm(id,value){const t=gameTerm(id);return `<option value="${value}">${esc(t.label)}${t.pending?' · '+ui('pending'):''}</option>`;}
  function pendingCount(){
    const terms=schemas.terminology?.terms || {}; let n=0;
    Object.values(terms).forEach(row=>{const x=row[state.locale]; if(!x || x.status==='pending' || x.finalInGame==='pending' || x.display==null)n++;});
    return n;
  }
  function renderTerminologyNotice(){const n=pendingCount();$('#termPendingCount').textContent=`${n} ${ui('pending')}`;}

  function renderAccount(){
    const a=state.account;
    const labels = state.locale==='fr'?{title:'Mon compte',text:'Base commune nécessaire pour les plafonds de héros, la taille de marche et les bonus de centres.',hq:'Niveau HQ',squads:'Escouades simultanées',pass:'Super Monthly Pass actif',tier:'Niveau de troupes',centers:'Centres de troupes',tank:'Centre Tank',air:'Centre Aircraft',missile:'Centre Missile',march:'Taille de marche additionnelle',shirley:'Bonus Shirley affiché',decor:'Bonus décorations affiché'}:
      state.locale==='it'?{title:'Il mio account',text:'Base comune necessaria per limiti eroi, dimensione marcia e bonus dei centri.',hq:'Livello HQ',squads:'Squadre simultanee',pass:'Super Monthly Pass attivo',tier:'Livello truppe',centers:'Centri truppe',tank:'Centro Tank',air:'Centro Aircraft',missile:'Centro Missile',march:'Dimensione marcia aggiuntiva',shirley:'Bonus Shirley mostrato',decor:'Bonus decorazioni mostrato'}:
      state.locale==='es'?{title:'Mi cuenta',text:'Base común necesaria para límites de héroes, tamaño de marcha y bonificaciones de centros.',hq:'Nivel HQ',squads:'Escuadras simultáneas',pass:'Super Monthly Pass activo',tier:'Nivel de tropas',centers:'Centros de tropas',tank:'Centro Tank',air:'Centro Aircraft',missile:'Centro Missile',march:'Tamaño de marcha adicional',shirley:'Bonificación Shirley mostrada',decor:'Bonificación decoraciones mostrada'}:
      {title:'My account',text:'Common base needed for hero caps, march size and troop-center bonuses.',hq:'HQ level',squads:'Simultaneous squads',pass:'Super Monthly Pass active',tier:'Troop tier',centers:'Troop centers',tank:'Tank Center',air:'Aircraft Center',missile:'Missile Center',march:'Additional march size',shirley:'Displayed Shirley bonus',decor:'Displayed decorations bonus'};
    $('#step-account').innerHTML = heading(labels.title,labels.text)+`
      <div class="section-card"><div class="form-grid">
        <label>${labels.hq}<input data-account="hqLevel" type="number" min="1" max="35" value="${a.hqLevel}"></label>
        <label>${labels.tier}<select data-account="troopTier">${['T7','T8','T9','T10','T11'].map(x=>`<option ${x===a.troopTier?'selected':''}>${x}</option>`).join('')}</select></label>
        <label>${labels.squads}<select data-account="activeSquads"><option value="3" ${a.activeSquads===3?'selected':''}>3</option><option value="4" ${a.activeSquads===4?'selected':''}>4</option></select></label>
        <label class="toggle-field">${labels.pass}<input data-account="superMonthlyPass" type="checkbox" ${a.superMonthlyPass?'checked':''}></label>
      </div></div>
      <div class="section-card"><h3>${labels.centers}</h3><div class="form-grid three">
        <label>${labels.tank}<input data-center="tankLevel" type="number" min="1" max="35" value="${a.troopCenters.tankLevel}"></label>
        <label>${labels.air}<input data-center="aircraftLevel" type="number" min="1" max="35" value="${a.troopCenters.aircraftLevel}"></label>
        <label>${labels.missile}<input data-center="missileLevel" type="number" min="1" max="35" value="${a.troopCenters.missileLevel}"></label>
      </div></div>
      <div class="section-card"><h3>${labels.march}</h3><div class="form-grid">
        <label>${labels.shirley}<input data-march="survivorShirleyBonus" type="number" min="0" step="1" value="${a.marchSizeAdditional.survivorShirleyBonus}"></label>
        <label>${labels.decor}<input data-march="decorationsBonus" type="number" min="0" step="1" value="${a.marchSizeAdditional.decorationsBonus}"></label>
      </div></div>`;
    $$('[data-account]').forEach(el=>el.onchange=()=>{const k=el.dataset.account; a[k]=el.type==='checkbox'?el.checked:(el.type==='number'||k==='activeSquads'?Number(el.value):el.value); if(k==='activeSquads'&&a[k]===4){a.superMonthlyPass=true;} saveState();renderAccount();});
    $$('[data-center]').forEach(el=>el.onchange=()=>{a.troopCenters[el.dataset.center]=Number(el.value);saveState();});
    $$('[data-march]').forEach(el=>el.onchange=()=>{a.marchSizeAdditional[el.dataset.march]=Number(el.value);saveState();});
  }

  function troopOptions(value){return ['tank','aircraft','missile'].map(x=>optionTerm('troop.'+x,x).replace('value="'+x+'"','value="'+x+'" '+(x===value?'selected':''))).join('');}
  function roleOptions(value){return ['attack','defense','support'].map(x=>optionTerm('role.'+x,x).replace('value="'+x+'"','value="'+x+'" '+(x===value?'selected':''))).join('');}
  function renderHeroes(){
    const titles = state.locale==='fr'?['Mes héros','Ajoutez les héros que vous possédez. Un héros ne pourra jamais être utilisé dans deux escouades simultanées.']:state.locale==='it'?['I miei eroi','Aggiungi gli eroi posseduti. Un eroe non potrà essere usato in due squadre simultaneamente.']:state.locale==='es'?['Mis héroes','Añade los héroes que posees. Un héroe no podrá usarse en dos escuadras simultáneamente.']:['My heroes','Add the heroes you own. A hero can never be used in two simultaneous squads.'];
    $('#step-heroes').innerHTML = heading(titles[0],titles[1],`<button id="addHero" class="primary-button" type="button">＋ ${ui('addHero')}</button>`)+`<div class="toolbar"><span class="count-pill">${state.heroes.length} ${ui('steps')[1].toLowerCase()}</span></div><div id="heroList" class="entry-list"></div>`;
    $('#addHero').onclick=()=>{state.heroes.push({heroId:'',owned:true,troopType:'tank',role:'attack',level:150,stars:5,exclusiveWeaponLevel:0,awakeningUnlocked:false,wallOfHonorLevel:0});saveState();renderHeroes();};
    const list=$('#heroList');
    if(!state.heroes.length){list.innerHTML='<div class="empty-state">＋ '+esc(ui('addHero'))+'</div>';list.firstChild.onclick=()=>$('#addHero').click();return;}
    state.heroes.forEach((hero,i)=>{
      const node=$('#heroTemplate').content.cloneNode(true); const card=node.querySelector('.hero-card'); card.dataset.index=i;
      card.querySelector('.entry-title').textContent=hero.heroId || `${ui('steps')[1]} ${i+1}`;
      card.querySelector('[data-field="troopType"]').innerHTML=troopOptions(hero.troopType);
      card.querySelector('[data-field="role"]').innerHTML=roleOptions(hero.role);
      card.querySelectorAll('[data-field]').forEach(el=>{const k=el.dataset.field;if(!['troopType','role'].includes(k)){if(el.type==='checkbox')el.checked=!!hero[k];else el.value=hero[k]??'';}el.onchange=()=>{hero[k]=el.type==='checkbox'?el.checked:(el.type==='number'?Number(el.value):el.value);saveState();renderHeroes();};});
      card.querySelector('[data-action="remove-hero"]').onclick=()=>{state.heroes.splice(i,1);state.gear.forEach(g=>{if(!state.heroes.some(h=>h.heroId===g.currentlyAssignedHero))g.currentlyAssignedHero='';});saveState();renderHeroes();};
      list.appendChild(node);
    });
    renderStaticI18n();
  }

  function gearSlotOptions(value){return ['gun','chip','armor','radar'].map(x=>optionTerm('gear.'+x,x).replace('value="'+x+'"','value="'+x+'" '+(x===value?'selected':''))).join('');}
  function heroAssignmentOptions(value){return `<option value="">—</option>`+state.heroes.filter(h=>h.heroId).map(h=>`<option value="${esc(h.heroId)}" ${h.heroId===value?'selected':''}>${esc(h.heroId)}</option>`).join('');}
  function renderGear(){
    const titles=state.locale==='fr'?['Mes équipements','Chaque pièce est unique et ne pourra être attribuée qu’à un héros à la fois dans l’optimisation multi-escouades.']:state.locale==='it'?['Il mio equipaggiamento','Ogni pezzo è unico e potrà essere assegnato a un solo eroe alla volta nell’ottimizzazione multi-squadra.']:state.locale==='es'?['Mi equipamiento','Cada pieza es única y solo podrá asignarse a un héroe a la vez en la optimización multi-escuadra.']:['My gear','Each item is unique and can only be assigned to one hero at a time during multi-squad optimization.'];
    $('#step-gear').innerHTML=heading(titles[0],titles[1],`<button id="addGear" class="primary-button" type="button">＋ ${ui('addGear')}</button>`)+`<div class="toolbar"><span class="count-pill">${state.gear.length} ${ui('steps')[2].toLowerCase()}</span></div><div id="gearList" class="entry-list"></div>`;
    $('#addGear').onclick=()=>{state.gear.push({itemId:'',slot:'gun',rarity:'UR',level:40,stars:0,promotion:0,currentlyAssignedHero:''});saveState();renderGear();};
    const list=$('#gearList');if(!state.gear.length){list.innerHTML='<div class="empty-state">＋ '+esc(ui('addGear'))+'</div>';list.firstChild.onclick=()=>$('#addGear').click();return;}
    state.gear.forEach((gear,i)=>{const node=$('#gearTemplate').content.cloneNode(true);const card=node.querySelector('.gear-card');card.querySelector('.entry-title').textContent=gear.itemId||`${ui('steps')[2]} ${i+1}`;card.querySelector('[data-field="slot"]').innerHTML=gearSlotOptions(gear.slot);card.querySelector('[data-field="currentlyAssignedHero"]').innerHTML=heroAssignmentOptions(gear.currentlyAssignedHero);card.querySelectorAll('[data-field]').forEach(el=>{const k=el.dataset.field;if(!['slot','currentlyAssignedHero'].includes(k)){el.value=gear[k]??'';}el.onchange=()=>{gear[k]=el.type==='number'?Number(el.value):el.value;saveState();renderGear();};});card.querySelector('[data-action="remove-gear"]').onclick=()=>{state.gear.splice(i,1);saveState();renderGear();};list.appendChild(node);});renderStaticI18n();
  }

  function researchLabel(item, fallback){
    const local=item[state.locale];
    if(local) return {label:local,pending:false};
    return {label:fallback || item.en || item.baseEn || item.id,pending:true};
  }
  function researchInputRow(id,label,maxLevel,pending,meta=''){
    const current=state.research[id]||{level:0,displayedBonusPct:''};
    return `<div class="research-row"><div><span class="research-name">${esc(label)}${pending?`<span class="pending-tag">${ui('pending')}</span>`:''}</span>${meta?`<span class="research-meta">${esc(meta)}</span>`:''}</div><label>${ui('level')}<input data-research-level="${esc(id)}" type="number" min="0" max="${maxLevel}" value="${Number(current.level)||0}"></label><label>Bonus %<input data-research-bonus="${esc(id)}" type="number" step="0.01" placeholder="optionnel" value="${esc(current.displayedBonusPct)}"></label></div>`;
  }
  function bindResearchInputs(){
    $$('[data-research-level]').forEach(el=>el.onchange=()=>{const id=el.dataset.researchLevel;state.research[id]=state.research[id]||{};state.research[id].level=Number(el.value);saveState();});
    $$('[data-research-bonus]').forEach(el=>el.onchange=()=>{const id=el.dataset.researchBonus;state.research[id]=state.research[id]||{};state.research[id].displayedBonusPct=el.value===''?'':Number(el.value);saveState();});
  }
  function renderResearchHero(){
    const items=schemas.researchTerms.heroTree||[];return ['tank','aircraft','missile'].map(type=>{const rows=items.filter(x=>x.type===type).map(item=>{const l=researchLabel(item,item.en);return researchInputRow(item.id,l.label,item.maxLevel,l.pending,'source: game-data mirror');}).join('');return `<section class="research-group"><h3>${esc(gameTerm('troop.'+type).label)}</h3>${rows}</section>`;}).join('');
  }
  function renderResearchMastery(){
    const adv=schemas.researchTerms.advancedTypeMastery||{};return ['tank','aircraft','missile'].map(type=>{const cfg=adv[type];let rows='';(cfg?.nodes||[]).forEach(node=>['I','II'].forEach(tier=>{const id=`${node.id}.${tier}`;const label=node.en?.[tier]||id;rows+=researchInputRow(id,label,node.maxLevel,true,'EN mirror · label local non confirmé');}));return `<section class="research-group"><h3>${esc(cfg?.treeTitleEn||type)}</h3>${rows}</section>`;}).join('');
  }
  function renderResearchSquad(){
    const s=schemas.researchTerms.squadSlotResearch||{};const active=state.account.activeSquads;return Object.entries(s.slots||{}).filter(([slot])=>Number(slot)<=active).map(([slot,cfg])=>{const rows=(s.familiesNeededBySimulator||[]).map(f=>researchInputRow(`squad.${slot}.${f.id}`,`${f.baseEn} ${cfg.roman}`,f.maxLevel,true,f.context)).join('');return `<section class="research-group"><h3>${esc(cfg.treeEn)}</h3>${rows}</section>`;}).join('');
  }
  function renderResearch(){
    const titles=state.locale==='fr'?['Mes recherches','Seules les recherches pouvant modifier la comparaison entre types ou slots d’escouade sont demandées.']:state.locale==='it'?['Le mie ricerche','Sono richieste solo le ricerche che possono modificare il confronto tra tipi o slot di squadra.']:state.locale==='es'?['Mi investigación','Solo se piden investigaciones que puedan modificar la comparación entre tipos o posiciones de escuadra.']:['My research','Only research that can change the comparison between troop types or squad slots is requested.'];
    $('#step-research').innerHTML=heading(titles[0],titles[1])+`<div class="research-warning">${state.locale==='fr'?'Les noms de recherches FR/IT/ES ne sont pas traduits artificiellement : tant qu’une capture du client n’existe pas, le libellé anglais audité est affiché avec le statut « à confirmer ».':state.locale==='en'?'Research names come from the audited game-data mirror and still require an in-game capture before linguistic finalization.':'Unconfirmed local research names are not invented. The audited English label is shown until an in-game capture confirms the local label.'}</div><div id="researchTabs" class="research-tabs"><button data-r-tab="hero">Hero</button><button data-r-tab="mastery">Mastery</button><button data-r-tab="squad">Squad 1–${state.account.activeSquads}</button></div><div id="researchGroups" class="research-groups"></div>`;
    $$('#researchTabs button').forEach(b=>{b.classList.toggle('active',b.dataset.rTab===researchTab);b.onclick=()=>{researchTab=b.dataset.rTab;renderResearch();};});
    $('#researchGroups').innerHTML=researchTab==='hero'?renderResearchHero():researchTab==='mastery'?renderResearchMastery():renderResearchSquad();bindResearchInputs();
  }

  function renderSeason(){
    const s=state.season6; const labels=state.locale==='fr'?['Saison 6 & buffs différentiels','Les totems et cartes sont enregistrés séparément afin de pouvoir les activer ou les exclure selon l’objectif de simulation.','Totems véhicule','Cartes tactiques PvP']:state.locale==='it'?['Stagione 6 & buff differenziali','Totem e carte sono salvati separatamente per poterli attivare o escludere secondo l’obiettivo di simulazione.','Totem veicolo','Carte tattiche PvP']:state.locale==='es'?['Temporada 6 y buffs diferenciales','Los tótems y cartas se guardan por separado para poder activarlos o excluirlos según el objetivo de simulación.','Tótems de vehículo','Cartas tácticas PvP']:['Season 6 & differential buffs','Totems and cards are stored separately so they can be enabled or excluded depending on the simulation objective.','Vehicle Totems','PvP Tactics Cards'];
    const totems=[['bearTank','Bear Totem','tank'],['eagleAircraft','Eagle Totem','aircraft'],['jaguarMissile','Jaguar Totem','missile']];
    const cards=[['dimensionalCrit','Dimensional Crit'],['frontalSuppression','Frontal Suppression'],['aftermathBurst','Aftermath Burst']];
    $('#step-season').innerHTML=heading(labels[0],labels[1])+`<div class="section-card"><h3>${labels[2]}</h3><div class="form-grid three">${totems.map(([id,name,type])=>`<label>${name}<input data-totem="${id}" type="number" min="0" max="30" value="${s.totemLevels[id]}"><span class="totem-value">${esc(gameTerm('troop.'+type).label)} · +${(Number(s.totemLevels[id])*.5).toFixed(1)}%</span></label>`).join('')}</div></div><div class="section-card"><h3>${labels[3]}</h3><div class="form-grid three">${cards.map(([id,name])=>`<label>${name}<input data-card="${id}" type="number" min="0" max="99" value="${s.tacticsCards[id]||0}"></label>`).join('')}</div><p class="fine-print">Crystal Boss: ces cartes restent désactivables par contexte, conformément au modèle de données.</p></div>`;
    $$('[data-totem]').forEach(el=>el.onchange=()=>{s.totemLevels[el.dataset.totem]=Number(el.value);saveState();renderSeason();});$$('[data-card]').forEach(el=>el.onchange=()=>{s.tacticsCards[el.dataset.card]=Number(el.value);saveState();});
  }

  function renderSummary(){
    const researchFilled=Object.values(state.research).filter(x=>Number(x.level)>0 || x.displayedBonusPct!=='').length;
    const title=state.locale==='fr'?'Résumé du profil':state.locale==='it'?'Riepilogo profilo':state.locale==='es'?'Resumen del perfil':'Profile summary';
    const text=state.locale==='fr'?'Cette première interface de saisie est prête pour le futur moteur de scoring relatif. Aucun calcul de classement n’est encore appliqué ici.':state.locale==='en'?'This first input interface is ready for the future relative-scoring engine. No squad ranking calculation is applied here yet.':'This input interface is ready for the future relative-scoring engine. No ranking calculation is applied yet.';
    $('#step-summary').innerHTML=heading(title,text)+`<div class="summary-grid"><div class="summary-tile"><strong>${state.heroes.length}</strong><small>${ui('steps')[1]}</small></div><div class="summary-tile"><strong>${state.gear.length}</strong><small>${ui('steps')[2]}</small></div><div class="summary-tile"><strong>${researchFilled}</strong><small>${ui('steps')[3]}</small></div></div><div class="section-card" style="margin-top:12px"><h3>Profil JSON local</h3><textarea id="jsonPreview" class="json-box" readonly>${esc(JSON.stringify(state,null,2))}</textarea><div class="toolbar" style="margin-top:10px;margin-bottom:0"><button id="copyJson" class="secondary-button" type="button">Copier JSON</button><button id="resetProfile" class="ghost-button" type="button">Réinitialiser</button></div></div><p class="fine-print">Le profil ne contient aucun code d’authentification WfGg et n’est envoyé à aucun serveur par cette interface.</p>`;
    $('#copyJson').onclick=async()=>{try{await navigator.clipboard.writeText(JSON.stringify(state,null,2));$('#copyJson').textContent='✓';setTimeout(()=>renderSummary(),800);}catch(_){$('#jsonPreview').select();document.execCommand('copy');}};
    $('#resetProfile').onclick=()=>{if(confirm('Réinitialiser le profil local ?')){state=clone(DEFAULT_STATE);saveState();renderAll();}};
  }

  function renderAll(){
    renderStaticI18n();renderTerminologyNotice();renderStepNav();renderAccount();renderHeroes();renderGear();renderResearch();renderSeason();renderSummary();showStep();
  }
  function scrollToWorkspace(){document.querySelector('.workspace').scrollIntoView({behavior:'smooth',block:'start'});}
  function bindGlobal(){
    $('#languageStrip').onclick=e=>{const b=e.target.closest('[data-lang]');if(b)setLocale(b.dataset.lang);};
    $('#prevBtn').onclick=()=>{if(state.step>0){state.step--;saveState();renderAll();scrollToWorkspace();}};
    $('#nextBtn').onclick=()=>{if(state.step<STEPS.length-1){state.step++;saveState();renderAll();scrollToWorkspace();}};
  }
  async function init(){
    bindGlobal();
    try{await loadSchemas();renderAll();}catch(err){console.error(err);document.querySelector('.workspace').innerHTML='<div class="empty-state">Impossible de charger les schémas du simulateur.</div>';}
  }
  init();
})();
