(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const fmt = (v) => v === null || v === undefined || v === '' ? '—' : (typeof v === 'number' ? new Intl.NumberFormat('fr-FR').format(v) : String(v));
  const HERO_NAMES = new Map([
    [30002,'Loki'],[30003,'Kane'],[30004,'Ambolt'],[30005,'Gump'],[40007,'Elsa'],[40008,'Farhad'],[40009,'Richard'],[40013,'Braz'],[40015,'Cage'],[40016,'Maxwell'],[40020,'Monica'],
    [50006,'Murphy'],[50007,'Williams'],[50008,'Marshall'],[50009,'Kimberly'],[50010,'Stetmann'],[50013,'McGregor'],[50014,'Fiona'],[50015,'Swift'],[50018,'Schuyler'],[50019,'Carlie'],[50020,'Morrison'],[50021,'Lucius'],[50022,'Adam']
  ]);

  const kit = window.WFGG_LASTWAR_GRAPHICS_KIT || null;
  const assetStatus = $('assetStatus');
  const kitMetrics = $('kitMetrics');

  function renderKitStatus() {
    kitMetrics.innerHTML='';
    if (!kit || kit.format !== 'WFGG_LASTWAR_GRAPHICS_KIT_V1') {
      assetStatus.textContent='Kit graphique absent · lance la Phase 29.';
      assetStatus.className='asset-status warn';
      return;
    }
    const s=kit.stats||{};
    assetStatus.textContent=`Kit graphique V1 détecté · Last War ${kit.gameVersion||'?'}`;
    assetStatus.className='asset-status ok';
    [['Portraits candidats',s.heroPortraitPathCandidates],['Drone',s.dronePathCandidates],['Équipement',s.equipmentPathCandidates],['Images directes',s.directRasterAssets]].forEach(([label,value])=>{
      const x=document.createElement('div');x.className='kit-metric';
      const a=document.createElement('span');a.textContent=label;
      const b=document.createElement('b');b.textContent=fmt(value);
      x.append(a,b);kitMetrics.appendChild(x);
    });
  }

  function heroName(id){ return HERO_NAMES.get(Number(id)) || `Héros ${id}`; }
  function initials(name){ return String(name).split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase(); }

  function directHeroAsset(id) {
    if (!kit) return null;
    const name=heroName(id);
    const node=kit.heroCandidates?.[name];
    if (!node || !Array.isArray(node.directAssets) || !node.directAssets.length) return null;
    return node.directAssets[0];
  }

  function heroTile(id,index) {
    const name=heroName(id);
    const el=document.createElement('div');el.className='hero-tile';
    const order=document.createElement('span');order.className='hero-order';order.textContent=String(index+1);el.appendChild(order);
    const asset=directHeroAsset(id);
    if (asset) {
      const img=document.createElement('img');img.className='hero-image';img.src=asset;img.alt=name;
      img.addEventListener('error',()=>{img.remove();const fb=document.createElement('div');fb.className='hero-fallback';fb.textContent=initials(name);el.insertBefore(fb,el.querySelector('.hero-caption'));},{once:true});
      el.appendChild(img);
    } else {
      const fb=document.createElement('div');fb.className='hero-fallback';fb.textContent=initials(name);el.appendChild(fb);
    }
    const cap=document.createElement('div');cap.className='hero-caption';
    const b=document.createElement('b');b.textContent=name;
    const s=document.createElement('span');s.textContent=`ID ${id}`;
    cap.append(b,s);el.appendChild(cap);
    return el;
  }

  function companionBox(kind,title,subtitle,icon) {
    const el=document.createElement('div');el.className=`companion-box${kind==='overlord'?' overlord':''}`;
    const ic=document.createElement('div');ic.className='companion-icon';ic.textContent=icon;
    const cp=document.createElement('div');cp.className='companion-copy';
    const b=document.createElement('b');b.textContent=title;
    const s=document.createElement('span');s.textContent=subtitle;
    cp.append(b,s);el.append(ic,cp);return el;
  }

  function squadCard(f,data) {
    const card=document.createElement('article');card.className='squad-card';
    const head=document.createElement('div');head.className='squad-card-head';
    const left=document.createElement('div');
    const strong=document.createElement('strong');strong.textContent=`Escouade ${f.index ?? f.squadNo ?? '?'}`;
    const sub=document.createElement('div');sub.className='squad-sub';sub.textContent=`Preset Drone ${f.chipEquipGroup||'—'}${f.defencePriority?` · défense ${f.defencePriority}`:''}`;
    left.append(strong,sub);
    const badge=document.createElement('span');badge.className='stage-kicker';badge.textContent='5 HÉROS';
    head.append(left,badge);card.appendChild(head);

    const grid=document.createElement('div');grid.className='hero-row-grid';
    const ids=[...(f.heroIds||[]),...(f.tmpHeroIds||[])].slice(0,5);
    ids.forEach((id,i)=>grid.appendChild(heroTile(id,i)));
    while(grid.children.length<5){
      const tile=document.createElement('div');tile.className='hero-tile';
      const fb=document.createElement('div');fb.className='hero-fallback';fb.textContent='?';tile.appendChild(fb);grid.appendChild(tile);
    }
    card.appendChild(grid);

    const strip=document.createElement('div');strip.className='companion-strip';
    const group=(data.droneChipGroups||[]).find(g=>Number(g.equipGroup)===Number(f.chipEquipGroup));
    const stars=(group?.chips||[]).filter(x=>Number(x.slot)>0).map(x=>x.star??0).join('/');
    strip.appendChild(companionBox('drone','Drone global',`Preset ${f.chipEquipGroup||'—'} · 4 puces${stars?` · ★ ${stars}`:''}`,'◈'));
    const ord=(f.overlordOrdinals||[])[0];
    if(ord!==undefined){
      const o=(data.overlords||[]).find(x=>Number(x.ordinal)===Number(ord));
      strip.appendChild(companionBox('overlord',`Overlord #${ord}`,`${fmt(o?.power)} puissance · rang ${fmt(o?.rank)}`,'◆'));
    } else {
      strip.appendChild(companionBox('overlord','Overlord','Non affecté à cette escouade','—'));
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
    const host=$('squadGrid');host.innerHTML='';
    (data.armyFormations||[]).forEach(f=>host.appendChild(squadCard(f,data)));
    $('squadEquipPower').textContent=fmt(data.playerProgress?.squadEquipPower ?? data.drone?.totalSquadEquipPower);
    $('replicaStatus').textContent=`${(data.armyFormations||[]).length} escouades chargées · ${(data.heroes||[]).length} héros disponibles.`;
  }

  $('squadDataFile').addEventListener('change',async(e)=>{
    const file=e.target.files?.[0];if(!file)return;
    try{const data=validate(JSON.parse(await file.text()));render(data);}catch(err){$('replicaStatus').textContent=`Erreur : ${err.message||err}`;}
  });

  renderKitStatus();
})();
