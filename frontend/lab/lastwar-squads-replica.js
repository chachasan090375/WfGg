(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const fmt = (v) => v === null || v === undefined || v === '' ? '—' : (typeof v === 'number' ? new Intl.NumberFormat('fr-FR').format(v) : String(v));
  const HERO_NAMES = new Map([
    [30002,'Loki'],[30003,'Kane'],[30004,'Ambolt'],[30005,'Gump'],[40007,'Elsa'],[40008,'Farhad'],[40009,'Richard'],[40013,'Braz'],[40015,'Cage'],[40016,'Maxwell'],[40020,'Monica'],
    [50006,'Murphy'],[50007,'Williams'],[50008,'Marshall'],[50009,'Kimberly'],[50010,'Stetmann'],[50013,'McGregor'],[50014,'Fiona'],[50015,'Swift'],[50018,'Schuyler'],[50019,'Carlie'],[50020,'Morrison'],[50021,'Lucius'],[50022,'Adam']
  ]);

  const kit = window.WFGG_LASTWAR_GRAPHICS_KIT || null;
  const heroCatalog = window.WFGG_LASTWAR_HERO_CATALOG || null;
  const assetStatus = $('assetStatus');
  const kitMetrics = $('kitMetrics');

  function catalogHero(id) { return heroCatalog?.heroes?.find(x => Number(x.heroId) === Number(id)) || null; }
  function catalogProofValid(x) { return Boolean(x?.authoritativeRowFound && x?.name && x?.nameBasis); }
  function catalogIconValid(x) { return Boolean(catalogProofValid(x) && x?.localIconPath); }
  function heroName(id) { const x=catalogHero(id); return (catalogProofValid(x) ? x.name : null) || HERO_NAMES.get(Number(id)) || null; }
  function initials(name) { return String(name || '?').split(/\s+/).map(x => x[0]).join('').slice(0,2).toUpperCase(); }
  function heroRecord(id, data) { return (data?.heroes || []).find(x => Number(x.heroId) === Number(id)) || null; }

  function renderKitStatus() {
    kitMetrics.innerHTML = '';
    if (!kit || kit.format !== 'WFGG_LASTWAR_GRAPHICS_KIT_V1') {
      assetStatus.textContent = 'Kit graphique absent · extraction locale requise.';
      assetStatus.className = 'asset-status warn';
      return;
    }
    const s = kit.stats || {};
    const decoded = s.decodedRasterAssets ?? kit.extractedAssets?.length ?? 0;
    const provenNames = heroCatalog?.heroes?.filter(catalogProofValid).length ?? 0;
    const provenIcons = heroCatalog?.heroes?.filter(catalogIconValid).length ?? 0;
    const total = heroCatalog?.heroCount ?? 31;
    assetStatus.textContent = heroCatalog
      ? `Catalogue héros prouvé · ${provenNames}/${total} noms · ${provenIcons}/${total} icônes`
      : `Kit local · ${fmt(decoded)} images Unity décodées · catalogue héros à générer`;
    assetStatus.className = heroCatalog && provenNames === total && provenIcons === total ? 'asset-status ok' : 'asset-status warn';
    [
      ['Images Unity', decoded],
      ['Noms prouvés', heroCatalog ? `${provenNames}/${total}` : '—'],
      ['Icônes prouvées', heroCatalog ? `${provenIcons}/${total}` : '—'],
      ['Assets Drone', kit.droneAssets?.length ?? 0]
    ].forEach(([label,value]) => {
      const x = document.createElement('div'); x.className = 'kit-metric';
      const a = document.createElement('span'); a.textContent = label;
      const b = document.createElement('b'); b.textContent = fmt(value);
      x.append(a,b); kitMetrics.appendChild(x);
    });
  }

  function heroAssetScore(asset) {
    const p = `${asset?.name || ''} ${asset?.localPath || asset || ''}`.toLowerCase();
    let score = 0;
    if (p.includes('hero_icon_')) score += 1400;
    if (p.includes('halfbody') || p.includes('herohead') || p.includes('headicon') || p.includes('portrait')) score += 700;
    if (asset?.width && asset?.height) {
      const ratio = asset.width / asset.height;
      if (ratio > .68 && ratio < .9 && asset.height >= 180) score += 350;
      if (asset.width === 158 && asset.height === 201) score += 500;
      if (asset.width === 140 && asset.height === 140) score += 120;
    }
    if (p.includes('_zw') || p.includes('zhuanwu') || p.includes('lrb_') || p.includes('ljq_icon') || p.includes('weapon')) score -= 1100;
    if (p.includes('eff_') || p.includes('effect') || p.includes('smoke') || p.includes('noise') || p.includes('crack') || p.includes('particle')) score -= 1800;
    return score;
  }

  function directHeroAsset(id) {
    const cat = catalogHero(id);
    if (catalogIconValid(cat)) return cat.localIconPath;
    if (!kit) return null;
    const name = heroName(id);
    if (!name) return null;

    const rich = (kit.extractedAssets || [])
      .filter(x => x && x.category === 'heroes' && x.heroName === name && x.mappingBasis === 'object_name')
      .map(x => ({...x, score: heroAssetScore(x)}))
      .sort((a,b) => b.score - a.score);
    if (rich[0]?.score >= 900) return rich[0].localPath;

    const node = kit.heroCandidates?.[name];
    const ranked = (node?.directAssets || [])
      .map(path => ({path,score:heroAssetScore(path)}))
      .sort((a,b) => b.score-a.score);
    return ranked[0]?.score >= 900 ? ranked[0].path : null;
  }

  function droneMainAsset() {
    if (!kit) return null;
    const rows = (kit.extractedAssets || []).filter(x => x?.category === 'drone');
    const score = (x) => {
      const p = `${x.name || ''} ${x.localPath || ''}`.toLowerCase();
      let s = 0;
      if (/hero_icon_.*drone|drone.*hero_icon_/.test(p)) s += 1800;
      if (/drone_(?:head|portrait|avatar|icon)|(?:head|portrait|avatar|icon)_drone/.test(p)) s += 1400;
      if (/uav_(?:head|portrait|avatar|icon)|(?:head|portrait|avatar|icon)_uav/.test(p)) s += 1200;
      if (p.includes('item_uav_equip_') || p.includes('tacticalchip') || p.includes('skillchip')) s -= 1600;
      if (p.includes('eff_') || p.includes('effect') || p.includes('noise') || p.includes('smoke')) s -= 1600;
      return s;
    };
    const ranked = rows.map(x => ({...x,score:score(x)})).sort((a,b)=>b.score-a.score);
    return ranked[0]?.score >= 1000 ? ranked[0].localPath : null;
  }

  function heroTile(id,index,data) {
    const name = heroName(id);
    const rec = heroRecord(id,data);
    const resolved = Boolean(name);
    const cat = catalogHero(id);
    const el = document.createElement('div');
    el.className = `hero-tile${resolved ? '' : ' unresolved'}`;

    const order = document.createElement('span');
    order.className = 'hero-order'; order.textContent = String(index+1); el.appendChild(order);

    const level = document.createElement('span');
    level.className = 'hero-level';
    level.textContent = rec?.level ? `Lv.${rec.level}` : 'Lv.—';
    el.appendChild(level);

    const asset = directHeroAsset(id);
    if (asset) {
      const img = document.createElement('img');
      img.className = 'hero-image'; img.src = asset; img.alt = name;
      img.addEventListener('error',() => {
        img.remove();
        const fb = document.createElement('div'); fb.className='hero-fallback'; fb.textContent=initials(name);
        el.insertBefore(fb,el.querySelector('.hero-caption'));
      },{once:true});
      el.appendChild(img);
    } else {
      const fb = document.createElement('div');
      fb.className = 'hero-fallback'; fb.textContent = resolved ? initials(name) : '?'; el.appendChild(fb);
    }

    const cap = document.createElement('div'); cap.className='hero-caption';
    const b = document.createElement('b'); b.textContent = resolved ? name : 'Héros non résolu';
    const s = document.createElement('span');
    if (!resolved) s.textContent = `ID ${id} · table à décoder`;
    else if (catalogProofValid(cat)) s.textContent = asset ? 'table + icône officielle' : 'table résolue · icône à extraire';
    else s.textContent = asset ? 'portrait officiel' : 'portrait à retrouver';
    cap.append(b,s); el.appendChild(cap);
    return el;
  }

  function chipStrip(group) {
    const row = document.createElement('div'); row.className='chip-strip';
    const chips = (group?.chips || []).filter(x => Number(x.slot) > 0).sort((a,b)=>Number(a.slot)-Number(b.slot));
    chips.forEach((chip,i) => {
      const x = document.createElement('span'); x.className='chip-token';
      const slot = document.createElement('small'); slot.textContent = `P${chip.slot ?? i+1}`;
      const star = document.createElement('b'); star.textContent = `★${chip.star ?? 0}`;
      x.append(slot,star); row.appendChild(x);
    });
    return row;
  }

  function companionBox(kind,title,lines,icon,asset,extra) {
    const el = document.createElement('div'); el.className=`companion-box ${kind}`;
    const ic = document.createElement('div'); ic.className='companion-icon';
    if (asset) {
      const img = document.createElement('img'); img.className='companion-image'; img.src=asset; img.alt=title;
      img.addEventListener('error',()=>{img.remove();ic.textContent=icon;},{once:true});
      ic.appendChild(img);
    } else ic.textContent=icon;
    const cp = document.createElement('div'); cp.className='companion-copy';
    const b = document.createElement('b'); b.textContent=title; cp.appendChild(b);
    for (const line of lines.filter(Boolean)) { const s=document.createElement('span'); s.textContent=line; cp.appendChild(s); }
    if (extra) cp.appendChild(extra);
    el.append(ic,cp); return el;
  }

  function squadCard(f,data) {
    const card=document.createElement('article'); card.className='squad-card';
    const head=document.createElement('div'); head.className='squad-card-head';
    const left=document.createElement('div');
    const strong=document.createElement('strong'); strong.textContent=`Escouade ${f.index ?? f.squadNo ?? '?'}`;
    const sub=document.createElement('div'); sub.className='squad-sub'; sub.textContent=`Priorité défense ${f.defencePriority ?? '—'}`;
    left.append(strong,sub);
    const badge=document.createElement('span'); badge.className='stage-kicker'; badge.textContent='5 HÉROS';
    head.append(left,badge); card.appendChild(head);

    const grid=document.createElement('div'); grid.className='hero-row-grid';
    const ids=[...(f.heroIds||[]),...(f.tmpHeroIds||[])].slice(0,5);
    ids.forEach((id,i)=>grid.appendChild(heroTile(id,i,data)));
    while(grid.children.length<5){
      const tile=document.createElement('div'); tile.className='hero-tile unresolved';
      const fb=document.createElement('div'); fb.className='hero-fallback'; fb.textContent='?'; tile.appendChild(fb); grid.appendChild(tile);
    }
    card.appendChild(grid);

    const strip=document.createElement('div'); strip.className='companion-strip';
    const group=(data.droneChipGroups||[]).find(g=>Number(g.equipGroup)===Number(f.chipEquipGroup));
    const drone=data.drone||{};
    strip.appendChild(companionBox(
      'drone',
      'Drone global',
      [`Niv. ${fmt(drone.level)} · ${fmt(drone.totalSquadEquipPower)} puissance`,`Preset ${f.chipEquipGroup||'—'} · 4 puces`],
      '◇',
      droneMainAsset(),
      chipStrip(group)
    ));

    const ord=(f.overlordOrdinals||[])[0];
    if(ord!==undefined){
      const o=(data.overlords||[]).find(x=>Number(x.ordinal)===Number(ord));
      strip.appendChild(companionBox('overlord','Overlord',[`Rang ${fmt(o?.rank)} · ${fmt(o?.power)} puissance`,`${fmt(o?.skillCount)} compétences`],'◆',null,null));
    } else {
      strip.appendChild(companionBox('overlord','Overlord',['Non affecté à cette escouade'],'—',null,null));
    }
    card.appendChild(strip);
    return card;
  }

  function validate(data){
    if (!data || data.format !== 'WFGG_LASTWAR_MODULE_DATA_V3') throw new Error('Le fichier doit être le JSON Phase 19 / V3.');
    if (!data.privacy || data.privacy.networkUsed !== false) throw new Error('Contrat de confidentialité invalide.');
    return data;
  }

  function render(data){
    const host=$('squadGrid'); host.innerHTML='';
    (data.armyFormations||[]).forEach(f=>host.appendChild(squadCard(f,data)));
    $('squadEquipPower').textContent=fmt(data.playerProgress?.squadEquipPower ?? data.drone?.totalSquadEquipPower);

    const ids=(data.armyFormations||[]).flatMap(x=>x.heroIds||[]);
    const resolved=ids.filter(id=>Boolean(heroName(id))).length;
    const portraits=ids.filter(id=>Boolean(directHeroAsset(id))).length;
    $('replicaStatus').textContent=`${(data.armyFormations||[]).length} escouades · ${resolved}/${ids.length} libellés héros · ${portraits}/${ids.length} icônes officielles`;
  }

  $('squadDataFile').addEventListener('change',async(e)=>{
    const file=e.target.files?.[0]; if(!file)return;
    try { const data=validate(JSON.parse(await file.text())); render(data); }
    catch(err){ $('replicaStatus').textContent=`Erreur : ${err.message||err}`; }
  });

  renderKitStatus();
})();
