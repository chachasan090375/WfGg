(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const cards = ['privacyCard','overviewCard','powerCard','heroesCard','formationsCard','equipmentCard','weaponCard','buildingsCard','scienceCard'];
  let currentData = null;
  let heroFilter = 'all';

  const HERO_NAMES = new Map([
    [30002,'Loki'],[30003,'Kane'],[30004,'Ambolt'],[30005,'Gump'],
    [40007,'Elsa'],[40008,'Farhad'],[40009,'Richard'],[40013,'Braz'],[40015,'Cage'],[40016,'Maxwell'],[40020,'Monica'],
    [50006,'Murphy'],[50007,'Williams'],[50008,'Marshall'],[50009,'Kimberly'],[50010,'Stetmann'],
    [50013,'McGregor'],[50014,'Fiona'],[50015,'Swift'],[50018,'Schuyler'],[50019,'Carlie'],[50020,'Morrison'],[50021,'Lucius'],[50022,'Adam']
  ]);

  const heroLabel = (id) => HERO_NAMES.get(Number(id)) || `Héros ${id}`;
  const fmt = (value) => {
    if (value === null || value === undefined || value === '') return '—';
    if (typeof value === 'number') return new Intl.NumberFormat('fr-FR').format(value);
    return String(value);
  };
  const version = (data) => String(data.format || '').split('_').pop() || '?';

  function setStatus(text, kind = 'neutral') {
    const el = $('loadStatus');
    el.textContent = text;
    el.className = `status ${kind}`;
  }

  function metric(label, value, note = '') {
    const el = document.createElement('div');
    el.className = 'metric';
    const s = document.createElement('span'); s.textContent = label;
    const b = document.createElement('strong'); b.textContent = fmt(value);
    el.append(s,b);
    if (note) { const n = document.createElement('small'); n.textContent = note; n.className='muted'; el.appendChild(n); }
    return el;
  }

  function listRow(title, subtitle, right = '') {
    const row=document.createElement('div');row.className='list-row';
    const l=document.createElement('div');l.className='left';
    const a=document.createElement('strong');a.textContent=title;
    const s=document.createElement('span');s.textContent=subtitle;
    l.append(a,s);
    const r=document.createElement('div');r.className='right';r.textContent=right;
    row.append(l,r);return row;
  }

  function clearHost(id) { const el=$(id); if (!el) return null; el.innerHTML=''; return el; }
  function showCards(show) { cards.forEach(id => $(id)?.classList.toggle('hidden', !show)); }

  function validate(data) {
    const formats=['WFGG_LASTWAR_MODULE_DATA_V1','WFGG_LASTWAR_MODULE_DATA_V2','WFGG_LASTWAR_MODULE_DATA_V3'];
    if (!data || !formats.includes(data.format)) throw new Error('FORMAT_NORMALISE_INVALIDE');
    if (!data.privacy || data.privacy.networkUsed !== false) throw new Error('CONTRAT_CONFIDENTIALITE_INVALIDE');
    return data;
  }

  function renderPrivacy(data) {
    const host = clearHost('privacyGrid');
    const checks = [
      ['Réseau utilisé pendant l’export', data.privacy.networkUsed === false],
      ['Identifiants de session exportés', data.privacy.rawCredentialsExported === false],
      ['UUID privés exportés', data.privacy.rawInstanceUUIDsExported === false],
      ['Noms exportés', data.privacy.namesExported === false],
      ['Soldes de ressources exportés', data.privacy.resourceBalancesExported === false]
    ];
    if ('rawFormationRefsExported' in data.privacy) checks.push(['Références privées de formation exportées', data.privacy.rawFormationRefsExported === false]);
    if ('rawDominatorRefsExported' in data.privacy) checks.push(['Références privées Overlord exportées', data.privacy.rawDominatorRefsExported === false]);
    checks.forEach(([label, safe]) => {
      const row=document.createElement('div'); row.className='privacy-item';
      const span=document.createElement('span'); span.textContent=label;
      const b=document.createElement('b'); b.textContent=safe?'NON':'OUI'; b.className=safe?'ok':'warn';
      row.append(span,b); host.appendChild(row);
    });
  }

  function renderOverview(data) {
    const c=data.counts||{}; const host=clearHost('overviewGrid');
    const rows=[['Héros',c.heroes],['Formations actives',c.armyFormations],['Modèles',c.formationTemplates],['Équipements héros',c.heroEquipment],['Bâtiments',c.buildings],['Recherches',c.science]];
    if (data.format.endsWith('_V3')) rows.splice(4,0,['Overlords',c.overlords||0],['Composants Drone',c.droneComponents||0],['Puces Drone',c.droneChipEntries||0]);
    else rows.splice(4,0,['Équipements généraux',c.generalEquipment],['Système spécial',c.weapons]);
    rows.forEach(([a,b])=>host.appendChild(metric(a,b)));
    $('sourceBadge').textContent=`${data.initTopLevelFields||0} champs init · ${version(data)}`;
  }

  function renderPower(data) {
    const p=data.playerProgress||{}; const host=clearHost('powerGrid');
    [['Puissance max','playerMaxPower'],['Héros','heroPower'],['Armée','armyPower'],['Bâtiments','buildingPower'],['Recherche','sciencePower'],['Équipement escouade','squadEquipPower'],['Cartes de bataille','battleCardPower'],['Overlord','dominatorPower'],['Décoration','decoPower'],['Kills armée','armyKill'],['Niveau PvE','pveLevel'],['Endurance','stamina']].forEach(([label,key])=>host.appendChild(metric(label,p[key])));
  }

  function equipmentByHero(data) {
    const map=new Map();
    (data.heroEquipment||[]).forEach(e=>{ if (!e.heroId) return; if (!map.has(e.heroId)) map.set(e.heroId,[]); map.get(e.heroId).push(e); });
    return map;
  }

  function renderHeroFilters(data) {
    const host=clearHost('heroFilters');
    [['all','Tous'],['weapon','Avec arme'],['equipped','Équipés'],['rank26','Rang 26']].forEach(([key,label])=>{
      const b=document.createElement('button'); b.type='button'; b.className=`filter-chip${heroFilter===key?' active':''}`; b.textContent=label;
      b.addEventListener('click',()=>{heroFilter=key; renderHeroes(data); renderHeroFilters(data);}); host.appendChild(b);
    });
  }

  function renderHeroes(data) {
    const host=clearHost('heroesGrid'); const eq=equipmentByHero(data); let heroes=[...(data.heroes||[])];
    if(heroFilter==='weapon') heroes=heroes.filter(h=>h.hasWeaponInfo);
    if(heroFilter==='equipped') heroes=heroes.filter(h=>eq.has(h.heroId));
    if(heroFilter==='rank26') heroes=heroes.filter(h=>h.rankLv===26);
    heroes.forEach(h=>{
      const row=document.createElement('article'); row.className='hero-row';
      const strong=document.createElement('strong'); strong.textContent=heroLabel(h.heroId);
      const id=document.createElement('div'); id.className='hero-id'; id.textContent=`ID catalogue ${h.heroId}`;
      const meta=document.createElement('div'); meta.className='hero-meta';
      [['Niveau',h.level],['Rang',h.rankLv],['Compétences',h.skillCount],['Équipements',eq.get(h.heroId)?.length||0]].forEach(([k,v])=>{const x=document.createElement('span');x.innerHTML=`${k}<br><b>${fmt(v)}</b>`;meta.appendChild(x);});
      const flags=document.createElement('div'); flags.className='hero-flags';
      if(h.hasWeaponInfo){const f=document.createElement('span');f.className='hero-flag weapon';f.textContent='arme';flags.appendChild(f);}
      if(h.state!==undefined){const f=document.createElement('span');f.className='hero-flag';f.textContent=`état ${h.state}`;flags.appendChild(f);}
      row.append(strong,id,meta,flags); host.appendChild(row);
    });
    $('heroesCount').textContent=`${heroes.length}/${(data.heroes||[]).length}`;
  }

  function formationState(f) {
    const slots=Number(f.slots||0);
    const resolved=(f.heroIds||[]).length+(f.tmpHeroIds||[]).length;
    const unresolved=Number(f.unresolvedRefs ?? f.unresolvedHeroRefs ?? 0);
    const missing=f.missingHeroSlots!==undefined?Number(f.missingHeroSlots):Math.max(0,slots-resolved);
    return {slots,resolved,unresolved,missing};
  }

  function formationNode(f,title,data) {
    const row=document.createElement('div'); row.className='formation-row';
    const head=document.createElement('div'); head.className='formation-head';
    const left=document.createElement('div');
    const strong=document.createElement('strong'); strong.textContent=title;
    const group=f.chipEquipGroup||'—';
    const meta=document.createElement('span'); meta.textContent=`${f.slots||0} emplacements héros · preset Drone ${group}${f.defencePriority?` · priorité défense ${f.defencePriority}`:''}`;
    left.append(strong,meta); head.appendChild(left);
    if(f.squadNo){const badge=document.createElement('b');badge.className='mini-badge';badge.textContent=`Escouade ${f.squadNo}`;head.appendChild(badge);}
    row.appendChild(head);

    const ids=[...(f.heroIds||[]),...(f.tmpHeroIds||[])]; const heroes=document.createElement('div'); heroes.className='formation-heroes';
    if(ids.length){ids.forEach((id,i)=>{const p=document.createElement('span');p.className='formation-hero';p.textContent=`${i+1}. ${heroLabel(id)}`;p.title=`heroId ${id}`;heroes.appendChild(p);});}
    else {const p=document.createElement('span');p.className='muted small';p.textContent='Aucun héros renseigné dans ce modèle';heroes.appendChild(p);}
    row.appendChild(heroes);

    if (data.format.endsWith('_V3')) {
      const companions=document.createElement('div'); companions.className='formation-companions';
      if (f.chipEquipGroup>0) {
        const d=document.createElement('span'); d.className='formation-drone'; d.textContent=`Drone · 4 puces preset ${f.chipEquipGroup}`; companions.appendChild(d);
      }
      (f.overlordOrdinals||[]).forEach(ord=>{
        const o=(data.overlords||[]).find(x=>Number(x.ordinal)===Number(ord));
        const p=document.createElement('span');p.className='formation-overlord';p.textContent=`Overlord #${ord}${o?.power?` · ${fmt(o.power)} puissance`:''}`;companions.appendChild(p);
      });
      if (companions.childNodes.length) row.appendChild(companions);
    }

    const st=formationState(f);
    if(st.missing>0){
      const note=document.createElement('div');note.className='muted small';
      note.textContent=st.resolved===0?`Modèle vide · ${st.missing} emplacement(s) héros non renseigné(s)`:`${st.missing} emplacement(s) héros non renseigné(s)`;
      if(st.unresolved) note.textContent+=` · ${st.unresolved} référence(s) encore non classée(s)`;
      row.appendChild(note);
    } else if(st.unresolved>0){
      const note=document.createElement('div');note.className='muted small';note.textContent=`Formation complète · ${st.unresolved} référence(s) non classée(s)`;row.appendChild(note);
    }
    return row;
  }

  function renderFormations(data) {
    const armies=data.armyFormations||[]; const templates=data.formationTemplates||[];
    const a=clearHost('armyFormations'); armies.forEach(f=>a.appendChild(formationNode(f,`Armée ${f.index}`,data)));
    const t=clearHost('formationTemplates'); templates.forEach(f=>t.appendChild(formationNode(f,`Modèle ${f.index}`,data)));
    const totalSlots=armies.reduce((n,f)=>n+Number(f.slots||0),0);
    const resolved=armies.reduce((n,f)=>n+(f.heroIds||[]).length+(f.tmpHeroIds||[]).length,0);
    const complete=armies.filter(f=>formationState(f).missing===0).length;
    if(data.format.endsWith('_V3')) {
      const r=data.formationResolution||{};
      $('formationsStatus').textContent=`Armées actives : ${resolved}/${totalSlots} héros · ${r.armyOverlordRefs||0} Overlord lié · Drone global avec preset de puces par escouade · ${r.unresolvedRefs||0} référence non classée.`;
    } else if(data.formationResolution){
      $('formationsStatus').textContent=`Armées actives : ${resolved}/${totalSlots} héros résolus · ${complete}/${armies.length} formations complètes.`;
    } else {$('formationsStatus').textContent='Phase 7 : relations héros non résolues. Charge Phase 8 ou Phase 19.';}
  }

  function renderEquipment(data) {
    const map=equipmentByHero(data); const host=clearHost('equipmentSummary');
    [...map.entries()].sort((a,b)=>a[0]-b[0]).forEach(([heroId,items])=>{
      const maxLevel=Math.max(...items.map(x=>Number(x.level||0))); const maxPromote=Math.max(...items.map(x=>Number(x.promote||0))); const configs=[...new Set(items.map(x=>x.cfgId))].join(', ');
      host.appendChild(listRow(heroLabel(heroId),`${items.length} pièces · cfg ${configs}`,`niv. max ${maxLevel||'—'} · promo ${maxPromote||'—'}`));
    });
    $('equipmentCount').textContent=`${map.size} héros liés / ${(data.heroEquipment||[]).length} entrées`;
  }

  function renderCompanions(data) {
    const host=clearHost('weaponGrid');
    const compHost=clearHost('droneComponents');
    const chipHost=clearHost('droneChipGroups');
    const overHost=clearHost('overlordSummary');
    if(data.drone){
      const d=data.drone;
      [['Niveau Drone',d.level],['Puissance totale escouade',d.totalSquadEquipPower],['Puissance Drone hors puces',d.basePower],['Puissance puces',d.chipPower],['Puissance composants',d.componentPower],['Niveau puces',d.chipLevel],['EXP puces',d.chipExp],['Compétence',d.skillId],['Niveau compétence',d.skillLevel]].forEach(([k,v])=>host.appendChild(metric(k,v)));
      const proof=document.createElement('div'); proof.className=`identity-proof ${d.totalIdentityExact?'good':'warn-text'}`; proof.textContent=d.totalIdentityExact?'Identité de puissance confirmée : Drone + puces = puissance équipement escouade.':'Identité de puissance non confirmée.'; host.appendChild(proof);
      (d.components||[]).forEach(c=>compHost.appendChild(listRow(`Composant slot ${c.slot}`,`cfg ${c.cfgId} · EXP ${fmt(c.exp)}`,`${fmt(c.power)} puissance`)));
      (data.droneChipGroups||[]).forEach(g=>{
        const stars=(g.chips||[]).filter(c=>c.slot>0).map(c=>c.star??0).join('/');
        const used=(g.usedByArmies||[]).length?`Armée(s) ${g.usedByArmies.join(', ')}`:(Number(g.equipGroup)===0?'Inventaire non affecté':'Preset non actif');
        chipHost.appendChild(listRow(`Preset ${g.equipGroup}`,`${(g.chips||[]).length} puce(s) · étoiles ${stars||'—'}`,used));
      });
      (data.overlords||[]).forEach(o=>overHost.appendChild(listRow(`Overlord #${o.ordinal}`,`ID catalogue ${o.dominatorId||'—'} · rang ${o.rank||'—'} · ${o.skillCount||0} compétences`,`${fmt(o.power)} puissance`)));
      if (!(data.overlords||[]).length) overHost.appendChild(listRow('Overlord','Aucun Overlord détecté'));
      return;
    }

    const w=(data.weapons||[])[0];
    if(!w){host.appendChild(metric('Système spécial','Aucun'));return;}
    [['Niveau',w.level],['Puissance',w.power],['EXP',w.exp],['Niveau puce',w.chipLv],['EXP puce',w.chipExp],['Compétence',w.skill],['Niveau compétence',w.skillLevel]].forEach(([k,v])=>host.appendChild(metric(k,v)));
  }

  function renderBuildings(data) {
    const groups=new Map(); (data.buildings||[]).forEach(b=>{if(!groups.has(b.bId)) groups.set(b.bId,[]); groups.get(b.bId).push(b);});
    const rows=[...groups.entries()].map(([id,items])=>({id,count:items.length,maxLevel:Math.max(...items.map(x=>Number(x.level||0))),active:items.filter(x=>x.prodStatus!==undefined).length})).sort((a,b)=>b.maxLevel-a.maxLevel||a.id-b.id);
    const host=clearHost('buildingsTable'); const table=document.createElement('table'); table.innerHTML='<thead><tr><th>ID bâtiment</th><th>Instances</th><th>Niveau max</th><th>État production présent</th></tr></thead>';
    const body=document.createElement('tbody'); rows.forEach(r=>{const tr=document.createElement('tr');[r.id,r.count,r.maxLevel||'—',r.active].forEach(v=>{const td=document.createElement('td');td.textContent=fmt(v);tr.appendChild(td)});body.appendChild(tr)}); table.appendChild(body); host.appendChild(table);
    $('buildingsCount').textContent=`${(data.buildings||[]).length} instances · ${groups.size} types`;
  }

  function renderScience(data) {
    const rows=[...(data.science||[])]; const host=clearHost('scienceSummary'); const levels=rows.map(x=>Number(x.level||0));
    host.append(metric('Recherches',rows.length)); host.append(metric('Niveau moyen',levels.length?(levels.reduce((a,b)=>a+b,0)/levels.length).toFixed(2):0)); host.append(metric('Niveau max',levels.length?Math.max(...levels):0)); host.append(metric('Niveau 5',levels.filter(x=>x===5).length));
    const tableHost=clearHost('scienceTable'); const table=document.createElement('table'); table.innerHTML='<thead><tr><th>ID recherche</th><th>Niveau</th></tr></thead>';
    const body=document.createElement('tbody'); rows.sort((a,b)=>a.scienceId-b.scienceId).forEach(r=>{const tr=document.createElement('tr');const a=document.createElement('td');a.textContent=r.scienceId;const b=document.createElement('td');b.textContent=fmt(r.level);tr.append(a,b);body.appendChild(tr)});table.appendChild(body);tableHost.appendChild(table); $('scienceCount').textContent=`${rows.length} entrées`;
  }

  function render(data) {
    currentData=data; showCards(true); $('resetButton').disabled=false;
    renderPrivacy(data); renderOverview(data); renderPower(data); renderHeroFilters(data); renderHeroes(data); renderFormations(data); renderEquipment(data); renderCompanions(data); renderBuildings(data); renderScience(data);
    setStatus(`Fichier ${version(data)} chargé · ${(data.heroes||[]).length} héros · ${(data.armyFormations||[]).length} armées · ${(data.overlords||[]).length} Overlord`, 'success');
  }

  async function loadFile(file) {
    try { if(!file) return; if(file.size > 5*1024*1024) throw new Error('FICHIER_TROP_VOLUMINEUX'); const text=await file.text(); render(validate(JSON.parse(text))); }
    catch(error) { currentData=null; showCards(false); $('resetButton').disabled=true; setStatus(`Fichier refusé : ${error.message}`, 'error'); }
  }

  $('dataFile').addEventListener('change',(e)=>loadFile(e.target.files?.[0]));
  $('resetButton').addEventListener('click',()=>{ currentData=null; heroFilter='all'; $('dataFile').value=''; showCards(false); $('resetButton').disabled=true; setStatus('Données effacées de la mémoire de la page.','neutral'); });
  showCards(false);
})();
