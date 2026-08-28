(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const fmt = (v) => v === null || v === undefined || v === '' ? '—' : (typeof v === 'number' ? new Intl.NumberFormat('fr-FR').format(v) : String(v));
  const kit = window.WFGG_LASTWAR_GRAPHICS_KIT || null;
  const heroMap = window.WFGG_LASTWAR_HERO_AUTHORITATIVE_MAP || null;
  const companionMap = window.WFGG_LASTWAR_COMPANION_AUTHORITATIVE_MAP || null;
  const assetStatus = $('assetStatus');
  const kitMetrics = $('kitMetrics');

  function mappedHero(id) { return heroMap?.heroes?.find(x => Number(x.heroId) === Number(id)) || null; }
  function initials(name) { return String(name || '?').split(/\s+/).map(x => x[0]).join('').slice(0,2).toUpperCase(); }
  function heroRecord(id, data) { return (data?.heroes || []).find(x => Number(x.heroId) === Number(id)) || null; }
  function norm(s) { return String(s || '').trim().toLowerCase(); }
  function assetStem(s) { return norm(String(s || '').split('/').pop()).replace(/\.(png|jpg|jpeg|tga|webp)$/i,''); }
  function rarityFor(id) {
    const n = Number(id) || 0;
    if (n >= 50000) return { key:'ur', label:'UR' };
    if (n >= 40000) return { key:'ssr', label:'SSR' };
    return { key:'sr', label:'SR' };
  }
  function formationProfile(f) {
    const n = Number(f?.squadNo ?? f?.index) || 0;
    if (n === 1) return { key:'tank', label:'BLINDÉS', mark:'T' };
    if (n === 2) return { key:'aircraft', label:'AÉRIEN', mark:'A' };
    if (n === 3) return { key:'missile', label:'MISSILES', mark:'M' };
    return { key:'mixed', label:'FORMATION', mark:'+' };
  }

  function exactAssetRows(name) {
    if (!kit || !name) return [];
    const wanted = assetStem(name);
    return (kit.extractedAssets || []).filter(x => assetStem(x?.name) === wanted);
  }

  function exactAsset(name, preferSquare = true) {
    const rows = exactAssetRows(name);
    return rows.sort((a,b) => {
      const score = (x) => {
        const square = Number(x.width) === Number(x.height);
        const sprite = x.objectType === 'Sprite';
        return (sprite ? 400 : 0) + (preferSquare && square ? 300 : 0) + Math.min(Number(x.width)||0, Number(x.height)||0);
      };
      return score(b)-score(a);
    })[0] || null;
  }

  function iconCandidatesFor(id) {
    if (!kit) return [];
    const m = mappedHero(id);
    if (!m) return [];
    const refs = [m.queueIcon,m.halfIcon].filter(Boolean).map(assetStem);
    const rows = (kit.extractedAssets || []).filter(x => refs.includes(assetStem(x?.name)));
    const murphy = Number(id) === 50006;
    return rows.sort((a,b) => {
      const score = (x) => {
        if (murphy) {
          return (x.width===140 && x.height===140 ? 5000 : 0)
            + (x.width===154 && x.height===154 ? 2500 : 0)
            + (x.objectType==='Texture2D' ? 600 : 0)
            - (x.width===158 && x.height===201 ? 1500 : 0)
            + (x.height||0);
        }
        return (x.width===158 && x.height===201 ? 1000 : 0)
          + (x.width===140 && x.height===140 ? 500 : 0)
          + (x.objectType==='Sprite' ? 200 : 0)
          + (x.height||0);
      };
      return score(b)-score(a);
    });
  }

  function directHeroAsset(id) { return iconCandidatesFor(id)[0]?.localPath || null; }
  function resolvedDrone(level) { return companionMap?.drone?.resolve ? companionMap.drone.resolve(level) : null; }
  function resolvedGorilla(rank) { return companionMap?.dominator?.resolve ? companionMap.dominator.resolve(rank) : null; }
  function droneMainAsset(level) {
    const r = resolvedDrone(level);
    return r ? exactAsset(r.icon, false)?.localPath || null : null;
  }
  function gorillaMainAsset(rank) {
    const r = resolvedGorilla(rank);
    return r ? exactAsset(r.icon, true)?.localPath || null : null;
  }

  function renderKitStatus() {
    kitMetrics.innerHTML = '';
    const decoded = kit?.stats?.decodedRasterAssets ?? kit?.extractedAssets?.length ?? 0;
    const total = heroMap?.heroes?.length ?? 0;
    const icons = heroMap ? heroMap.heroes.filter(h => Boolean(directHeroAsset(h.heroId))).length : 0;
    const drone162 = Boolean(droneMainAsset(162));
    const gorilla47 = Boolean(gorillaMainAsset(47));
    assetStatus.textContent = heroMap
      ? `31 noms résolus · ${icons}/${total} icônes héros · Drone 162 ${drone162?'✓':'…'} · Gorilla rang 47 ${gorilla47?'✓':'…'}`
      : 'Mapping héros autoritatif absent.';
    assetStatus.className = heroMap && drone162 && gorilla47 ? 'asset-status ok' : 'asset-status warn';
    [
      ['Images Unity', decoded],
      ['Icônes héros', heroMap ? `${icons}/${total}` : '—'],
      ['Drone niv.162', drone162 ? 'profil 1217 ✓' : 'à extraire'],
      ['Gorilla rang 47', gorilla47 ? 'profil 1000005 ✓' : 'à extraire']
    ].forEach(([label,value]) => {
      const x = document.createElement('div'); x.className = 'kit-metric';
      const a = document.createElement('span'); a.textContent = label;
      const b = document.createElement('b'); b.textContent = fmt(value);
      x.append(a,b); kitMetrics.appendChild(x);
    });
  }

  function starStrip(rankLv) {
    const rank = Math.max(0, Number(rankLv) || 0);
    const progress = Math.max(0, rank - 1);
    const full = Math.min(5, Math.floor(progress / 5));
    const partial = full < 5 && progress % 5 > 0;
    const row = document.createElement('div');
    row.className = 'star-strip';
    row.title = rank ? `Rang héros ${rank}` : 'Rang inconnu';
    for (let i=0; i<5; i++) {
      const s = document.createElement('span');
      s.className = `hero-star${i < full ? ' on' : (i === full && partial ? ' partial' : '')}`;
      s.textContent = '★';
      row.appendChild(s);
    }
    return row;
  }

  function gearRail(rec) {
    const row = document.createElement('div'); row.className='gear-rail';
    row.title = rec?.hasWeaponInfo ? 'Équipement détecté' : 'Équipement non résolu';
    for (let i=0;i<4;i++) {
      const slot=document.createElement('span');
      slot.className=`gear-slot${rec?.hasWeaponInfo ? ' on' : ''}`;
      row.appendChild(slot);
    }
    return row;
  }

  function heroTile(id,index,data,profile) {
    const mapped = mappedHero(id);
    const name = mapped?.name || null;
    const rec = heroRecord(id,data);
    const rarity = rarityFor(id);
    const el = document.createElement('div');
    el.className = `hero-tile rarity-${rarity.key}${mapped ? '' : ' unresolved'}${Number(id)===50006 ? ' hero-murphy' : ''}`;

    const order = document.createElement('span'); order.className = 'hero-order'; order.textContent = String(index+1); el.appendChild(order);
    const cls = document.createElement('span'); cls.className='hero-class-dot'; cls.textContent=profile.mark; cls.title=profile.label; el.appendChild(cls);
    const level = document.createElement('span'); level.className = 'hero-level'; level.textContent = rec?.level ? `Lv.${rec.level}` : 'Lv.—'; el.appendChild(level);

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

    const rarityBadge=document.createElement('span'); rarityBadge.className='rarity-badge'; rarityBadge.textContent=rarity.label; el.appendChild(rarityBadge);
    el.appendChild(starStrip(rec?.rankLv));
    el.appendChild(gearRail(rec));

    const cap = document.createElement('div'); cap.className='hero-caption';
    const b = document.createElement('b'); b.textContent = mapped ? name : `ID ${id}`;
    const s = document.createElement('span');
    s.textContent = mapped ? `${rarity.label} · ${rec?.skillCount ?? '—'} compétences` : 'mapping absent';
    cap.append(b,s); el.appendChild(cap);
    return el;
  }

  function chipStrip(group) {
    const row = document.createElement('div'); row.className='chip-strip';
    const chips = (group?.chips || []).filter(x => Number(x.slot) > 0).sort((a,b)=>Number(a.slot)-Number(b.slot));
    chips.forEach((chip,i) => {
      const x = document.createElement('span'); x.className='chip-token'; x.title=`Puce ${chip.slot ?? i+1} · ${chip.star ?? 0} étoile(s)`;
      const gem=document.createElement('i'); gem.className='chip-gem';
      const slot = document.createElement('small'); slot.textContent = `P${chip.slot ?? i+1}`;
      const star = document.createElement('b'); star.textContent = `★${chip.star ?? 0}`;
      x.append(gem,slot,star); row.appendChild(x);
    });
    return row;
  }

  function companionBox(kind,title,lines,icon,asset,extra,inactive=false) {
    const el = document.createElement('div'); el.className=`companion-box ${kind}${inactive?' inactive':''}`;
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
    const profile=formationProfile(f);
    const squadNo=f.squadNo ?? f.index ?? '?';
    const card=document.createElement('article'); card.className='squad-card';
    const head=document.createElement('div'); head.className='squad-card-head';
    const left=document.createElement('div'); left.className='squad-head-copy';
    const number=document.createElement('span'); number.className='squad-number'; number.textContent=String(squadNo);
    const copy=document.createElement('div');
    const strong=document.createElement('strong'); strong.textContent=`Escouade ${squadNo}`;
    const sub=document.createElement('div'); sub.className='squad-sub'; sub.textContent=`Priorité défense ${f.defencePriority ?? '—'}`;
    copy.append(strong,sub); left.append(number,copy);
    const right=document.createElement('div'); right.className='squad-head-meta';
    const type=document.createElement('span'); type.className=`formation-type ${profile.key}`; type.textContent=profile.label;
    const badge=document.createElement('span'); badge.className='stage-kicker'; badge.textContent='5 HÉROS';
    right.append(type,badge); head.append(left,right); card.appendChild(head);

    const grid=document.createElement('div'); grid.className='hero-row-grid';
    const ids=[...(f.heroIds||[]),...(f.tmpHeroIds||[])].slice(0,5);
    ids.forEach((id,i)=>grid.appendChild(heroTile(id,i,data,profile)));
    while(grid.children.length<5){
      const tile=document.createElement('div'); tile.className='hero-tile unresolved';
      const fb=document.createElement('div'); fb.className='hero-fallback'; fb.textContent='?'; tile.appendChild(fb); grid.appendChild(tile);
    }
    card.appendChild(grid);

    const strip=document.createElement('div'); strip.className='companion-strip';
    const group=(data.droneChipGroups||[]).find(g=>Number(g.equipGroup)===Number(f.chipEquipGroup));
    const drone=data.drone||{};
    const droneVisual=resolvedDrone(drone.level);
    strip.appendChild(companionBox(
      'drone','Drone global',
      [
        `Niv. ${fmt(drone.level)} · ${fmt(drone.totalSquadEquipPower)} puissance`,
        `Apparence ${droneVisual?.currentAppearance ?? droneVisual?.appearance ?? '—'} · preset ${f.chipEquipGroup||'—'}`
      ],
      '◇',droneMainAsset(drone.level),chipStrip(group)
    ));

    const ord=(f.overlordOrdinals||[])[0];
    if(ord!==undefined){
      const o=(data.overlords||[]).find(x=>Number(x.ordinal)===Number(ord));
      const gorilla=resolvedGorilla(o?.rank);
      strip.appendChild(companionBox(
        'overlord','Overlord · Gorilla',
        [
          `Rang ${fmt(o?.rank)} · ${fmt(o?.power)} puissance`,
          `Apparence ${gorilla?.appearance || '—'} · ${fmt(o?.skillCount)} compétences`
        ],
        '◆',gorillaMainAsset(o?.rank),null
      ));
    } else {
      strip.appendChild(companionBox('overlord','Overlord',['Non affecté à cette escouade'],'—',null,null,true));
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
