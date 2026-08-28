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
    const decoded=s.decodedRasterAssets ?? kit.extractedAssets?.length ?? 0;
    assetStatus.textContent=`Kit graphique V1 détecté · ${fmt(decoded)} images Unity décodées`;
    assetStatus.className='asset-status ok';
    [['Portraits candidats',s.heroPortraitPathCandidates],['Drone',s.dronePathCandidates],['Images Unity',decoded],['Sprites',s.phase30bDecodedSprites]].forEach(([label,value])=>{
      const x=document.createElement('div');x.className='kit-metric';
      const a=document.createElement('span');a.textContent=label;
      const b=document.createElement('b');b.textContent=fmt(value);
      x.append(a,b);kitMetrics.appendChild(x);
    });
  }

  function heroName(id){ return HERO_NAMES.get(Number(id)) || `Héros ${id}`; }
  function initials(name){ return String(name).split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase(); }

  function heroAssetScore(path) {
    const p=String(path||'').toLowerCase();
    let score=0;
    if (p.includes('hero_icon_')) score+=1000;
    if (p.includes('halfbody') || p.includes('herohead') || p.includes('headicon')) score+=500;
    if (p.includes('_zw') || p.includes('zhuanwu') || p.includes('lrb_') || p.includes('ljq_icon')) score-=700;
    if (p.includes('eff_') || p.includes('effect') || p.includes('smoke') || p.includes('noise') || p.includes('crack')) score-=1200;
    if (/hero_icon_[^/]+\.png$/.test(p)) score+=180;
    if (/_2\.png$/.test(p) || /_3\.png$/.test(p)) score-=20;
    return score;
  }

  function directHeroAsset(id) {
    if (!kit) return null;
    const name=heroName(id);
    const node=kit.heroCandidates?.[name];
    if (!node || !Array.isArray(node.directAssets) || !node.directAssets.length) return null;
    const ranked=node.directAssets.map(path=>({path,score:heroAssetScore(path)})).sort((a,b)=>b.score-a.score);
    return ranked[0]?.score >= 700 ? ranked[0].path : null;
  }

  function categoryAsset(list,kind) {
    if (!Array.isArray(list) || !list.length) return null;
    const score=(path)=>{
      const p=String(path||'').toLowerCase();
      let s=0;
      if (kind==='drone') {
        if (p.includes('hero_icon_drone')) s+=1200;
        if (p.includes('item_uav_equip_')) s+=900;
        if (p.includes('tacticalchip') || p.includes('skillchip')) s+=600;
        if (p.includes('drone') || p.includes('uav')) s+=350;
      } else if (kind==='overlord') {
        if (p.includes('dominator')) s+=1000;
        if (p.includes('gorilla') || p.includes('cockatrice') || p.includes('hawk')) s+=800;
      }
      if (p.includes('eff_') || p.includes('effect') || p.includes('noise') || p.includes('smoke')) s-=900;
      return s;
    };
    const ranked=list.map(path=>({path,score:score(path)})).sort((a,b)=>b.score-a.score);
    return ranked[0]?.score > 0 ? ranked[0].path : null;
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

  function companionBox(kind,title,subtitle,icon,asset) {
    const el=document.createElement('div');el.className=`companion-box${kind==='overlord'?' overlord':''}`;
    const ic=document.createElement('div');ic.className='companion-icon';
    if (asset) {
      const img=document.createElement('img');img.className='companion-image';img.src=asset;img.alt=title;
      img.addEventListener('error',()=>{img.remove();ic.textContent=icon;},{once:true});
      ic.appendChild(img);
    } else ic.textContent=icon;
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
    const droneAsset=categoryAsset(kit?.droneAssets,'drone');
    strip.appendChild(companionBox('drone','Drone global',`Preset ${f.chipEquipGroup||'—'} · 4 puces${stars?` · ★ ${stars}`:''}`,'◈',droneAsset));
    const ord=(f.overlordOrdinals||[])[0];
    if(ord!==undefined){
      const o=(data.overlords||[]).find(x=>Number(x.ordinal)===Number(ord));
      strip.appendChild(companionBox('overlord',`Overlord #${ord}`,`${fmt(o?.power)} puissance · rang ${fmt(o?.rank)}`,'◆',categoryAsset(kit?.dominatorAssets,'overlord')));
    } else {
      strip.appendChild(companionBox('overlord','Overlord','Non affecté à cette escouade','—',null));
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
