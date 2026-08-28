(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const fmt = (v) => v === null || v === undefined || v === '' ? '—' : (typeof v === 'number' ? new Intl.NumberFormat('fr-FR').format(v) : String(v));
  const kit = window.WFGG_LASTWAR_GRAPHICS_KIT || null;
  const heroMap = window.WFGG_LASTWAR_HERO_AUTHORITATIVE_MAP || null;
  const assetStatus = $('assetStatus');
  const kitMetrics = $('kitMetrics');

  function mappedHero(id) { return heroMap?.heroes?.find(x => Number(x.heroId) === Number(id)) || null; }
  function heroName(id) { return mappedHero(id)?.name || null; }
  function initials(name) { return String(name || '?').split(/\s+/).map(x => x[0]).join('').slice(0,2).toUpperCase(); }
  function heroRecord(id, data) { return (data?.heroes || []).find(x => Number(x.heroId) === Number(id)) || null; }
  function norm(s) { return String(s || '').trim().toLowerCase(); }

  function iconCandidatesFor(id) {
    if (!kit) return [];
    const m = mappedHero(id);
    if (!m) return [];
    const refs = [m.queueIcon,m.halfIcon].filter(Boolean).map(norm);
    const rows = (kit.extractedAssets || []).filter(x => refs.includes(norm(x?.name)));
    return rows.sort((a,b) => {
      const sa = (a.width===158 && a.height===201 ? 500 : 0) + (a.width===140 && a.height===140 ? 200 : 0) + (a.height||0);
      const sb = (b.width===158 && b.height===201 ? 500 : 0) + (b.width===140 && b.height===140 ? 200 : 0) + (b.height||0);
      return sb-sa;
    });
  }

  function directHeroAsset(id) {
    return iconCandidatesFor(id)[0]?.localPath || null;
  }

  function renderKitStatus() {
    kitMetrics.innerHTML = '';
    const decoded = kit?.stats?.decodedRasterAssets ?? kit?.extractedAssets?.length ?? 0;
    const total = heroMap?.heroes?.length ?? 0;
    const icons = heroMap ? heroMap.heroes.filter(h => Boolean(directHeroAsset(h.heroId))).length : 0;
    assetStatus.textContent = heroMap
      ? `31 noms résolus · ${icons}/${total} icônes officielles déjà présentes localement`
      : 'Mapping héros autoritatif absent.';
    assetStatus.className = heroMap ? 'asset-status ok' : 'asset-status warn';
    [
      ['Images Unity', decoded],
      ['Noms héros', heroMap ? `${total}/${total}` : '—'],
      ['Icônes exactes', heroMap ? `${icons}/${total}` : '—'],
      ['Assets Drone', kit?.droneAssets?.length ?? 0]
    ].forEach(([label,value]) => {
      const x = document.createElement('div'); x.className = 'kit-metric';
      const a = document.createElement('span'); a.textContent = label;
      const b = document.createElement('b'); b.textContent = fmt(value);
      x.append(a,b); kitMetrics.appendChild(x);
    });
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
    const mapped = mappedHero(id);
    const name = mapped?.name || null;
    const rec = heroRecord(id,data);
    const el = document.createElement('div');
    el.className = `hero-tile${mapped ? '' : ' unresolved'}`;

    const order = document.createElement('span');
    order.className = 'hero-order'; order.textContent = String(index+1); el.appendChild(order);

    const level = document.createElement('span');
    level.className = 'hero-level'; level.textContent = rec?.level ? `Lv.${rec.level}` : 'Lv.—'; el.appendChild(level);

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
      const fb = document.createElement('div'); fb.className='hero-fallback'; fb.textContent = mapped ? initials(name) : '?'; el.appendChild(fb);
    }

    const cap = document.createElement('div'); cap.className='hero-caption';
    const b = document.createElement('b'); b.textContent = mapped ? name : `ID ${id}`;
    const s = document.createElement('span');
    s.textContent = mapped ? (asset ? mapped.queueIcon : `${mapped.queueIcon} · PNG à extraire`) : 'mapping absent';
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
      'drone','Drone global',
      [`Niv. ${fmt(drone.level)} · ${fmt(drone.totalSquadEquipPower)} puissance`,`Preset ${f.chipEquipGroup||'—'} · 4 puces`],
      '◇',droneMainAsset(),chipStrip(group)
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
    const resolved=ids.filter(id=>Boolean(mappedHero(id))).length;
    const portraits=ids.filter(id=>Boolean(directHeroAsset(id))).length;
    $('replicaStatus').textContent=`${(data.armyFormations||[]).length} escouades · ${resolved}/${ids.length} noms résolus · ${portraits}/${ids.length} icônes exactes`;
  }

  $('squadDataFile').addEventListener('change',async(e)=>{
    const file=e.target.files?.[0]; if(!file)return;
    try { const data=validate(JSON.parse(await file.text())); render(data); }
    catch(err){ $('replicaStatus').textContent=`Erreur : ${err.message||err}`; }
  });

  renderKitStatus();
})();
