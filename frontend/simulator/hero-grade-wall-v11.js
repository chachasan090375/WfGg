(() => {
  'use strict';
  const PROFILE_KEY='wfgg-simulator-profile-v1';
  const CATALOG_URL='data/hero-catalog.v2.json';
  let catalog=[];
  let rendering=false;
  let queued=false;
  let wallOpenFor='';

  const norm=v=>String(v||'').trim().toLowerCase();
  const esc=v=>String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
  const fmt=v=>{const n=Number(v);return Number.isFinite(n)&&n>0?n.toLocaleString('fr-FR'):'—'};
  const profile=()=>{try{return window.WfGgProfilePersistence?.profile?.()||JSON.parse(localStorage.getItem(PROFILE_KEY)||'{}')||{}}catch{return {}}};
  const heroName=()=>document.querySelector('#heroGameSheet.open .hero-sheet-title h3')?.textContent?.trim()||'';
  const catByName=name=>catalog.find(h=>norm(h.name)===norm(name))||null;
  const heroByName=name=>(profile().heroes||[]).find(h=>norm(h.heroId)===norm(name))||null;
  const heroIndexByName=(p,name)=>(p.heroes||[]).findIndex(h=>norm(h.heroId)===norm(name));

  function hiddenField(name,field){
    return [...document.querySelectorAll('.hero-card')].find(c=>norm(c.querySelector('[data-field="heroId"]')?.value)===norm(name))?.querySelector(`[data-field="${field}"]`)||null;
  }
  function setHeroField(name,field,value){
    const el=hiddenField(name,field);
    if(el){el.value=String(value);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return true}
    const p=profile(),i=heroIndexByName(p,name);if(i<0)return false;p.heroes[i][field]=value;localStorage.setItem(PROFILE_KEY,JSON.stringify(p));return true;
  }
  function wallData(name){
    const h=heroByName(name)||{};const b=h.wallOfHonorBonuses||{};
    return {level:Math.max(0,Number(h.wallOfHonorLevel)||0),hp:Math.max(0,Number(b.hp)||0),attack:Math.max(0,Number(b.attack)||0),defense:Math.max(0,Number(b.defense)||0)};
  }
  function saveWallData(name,patch){
    const p=profile(),i=heroIndexByName(p,name);if(i<0)return false;
    const h=p.heroes[i]=p.heroes[i]||{};const cur=h.wallOfHonorBonuses||{};
    if(patch.level!=null)h.wallOfHonorLevel=Math.max(0,Math.round(Number(patch.level)||0));
    h.wallOfHonorBonuses={hp:patch.hp!=null?Math.max(0,Number(patch.hp)||0):Math.max(0,Number(cur.hp)||0),attack:patch.attack!=null?Math.max(0,Number(patch.attack)||0):Math.max(0,Number(cur.attack)||0),defense:patch.defense!=null?Math.max(0,Number(patch.defense)||0):Math.max(0,Number(cur.defense)||0)};
    localStorage.setItem(PROFILE_KEY,JSON.stringify(p));
    if(patch.level!=null){const el=hiddenField(name,'wallOfHonorLevel');if(el){el.value=String(h.wallOfHonorLevel);el.dispatchEvent(new Event('input',{bubbles:true}));}}
    return true;
  }
  function stats(cat,h){
    let hp=Number(h?.displayedHp)||0,attack=Number(h?.displayedAttack)||0,defense=Number(h?.displayedDefense)||0;
    try{
      if((!hp||!attack||!defense)&&cat?.nativeId&&window.WfGgNativeStats?.calculateSync){
        const z=window.WfGgNativeStats.calculateSync({nativeId:cat.nativeId,level:Number(h?.level)||175,stars:Number(h?.stars)||0});
        hp=hp||z.stats.hp.nativeLevelPlusGrade;attack=attack||z.stats.attack.nativeLevelPlusGrade;defense=defense||z.stats.defense.nativeLevelPlusGrade;
      }
    }catch(_){}
    return {hp,attack,defense,power:Number(h?.displayedPower)||0};
  }
  function portrait(cat){const src=cat?.localPortrait||cat?.portrait||'';return src?`<img src="${esc(src)}" alt="${esc(cat?.name||'Héros')}">`:''}
  function starColumns(stars){
    const tiers=Math.round(Math.max(0,Math.min(5,Number(stars)||0))*5);
    return [0,1,2,3,4].map(star=>{
      const base=star*5,lit=Math.max(0,Math.min(5,tiers-base));
      return `<div class="v11-grade-star ${lit===5?'full':''}"><button type="button" class="v11-grade-bigstar" data-v11-grade-tier="${base+5}" aria-label="${star+1} étoiles">★</button><div class="v11-grade-pips">${[1,2,3,4,5].map(p=>`<button type="button" data-v11-grade-tier="${base+p}" class="${p<=lit?'on':''}" aria-label="${star}+${p}/5"></button>`).join('')}</div></div>`;
    }).join('');
  }
  function gradePage(cat,h){
    const s=stats(cat,h),stars=Math.max(0,Math.min(5,Number(h?.stars)||0)),five=stars>=5;
    return `<div class="v11-grade-page" data-v11-page="grade" data-v11-hero="${esc(cat.name)}">
      <div class="v11-grade-hero">${portrait(cat)}<div class="v11-grade-power"><span>⚔</span>${fmt(s.power)}</div></div>
      <section class="v11-grade-panel">
        <div class="v11-grade-stars">${starColumns(stars)}</div>
        <div class="v11-grade-label">${stars.toFixed(stars%1?1:0)} étoile${stars>1?'s':''}</div>
        <div class="v11-grade-stats"><div><span>PV Héros</span><b>${fmt(s.hp)}</b></div><div><span>ATQ Héros</span><b>${fmt(s.attack)}</b></div><div><span>Défense Héros</span><b>${fmt(s.defense)}</b></div></div>
        <div class="v11-grade-modules" aria-hidden="true"><i class="m1">◆<small>${five?'MAX':'PV'}</small></i><i class="m2">✦<small>${five?'MAX':'ATQ'}</small></i><i class="m3">➤<small>${five?'MAX':'DEF'}</small></i><i class="m4">★<small>${five?'MAX':'GRADE'}</small></i></div>
      </section>
      <div class="v11-honor-entry ${five?'ready':'locked'}"><div class="v11-honor-message">${five?`Le Héros a été ajouté au Mur d'honneur.`:`Mur d'honneur disponible à 5 étoiles.`}</div><button type="button" data-v11-open-honor ${five?'':'disabled'}><span>Aller</span><b>›</b></button></div>
    </div>`;
  }
  function statIcon(kind){if(kind==='hp')return '♥';if(kind==='attack')return '⚔';return '⬟'}
  function honorPage(cat,h){
    const d=wallData(cat.name);
    return `<div class="v11-honor-page" data-v11-page="honor" data-v11-hero="${esc(cat.name)}">
      <header class="v11-honor-head"><button type="button" data-v11-honor-back aria-label="Retour au Grade">←</button><div>${portrait(cat)}<span><small>Mur d'honneur</small><b>${esc(cat.name)}</b></span></div></header>
      <section class="v11-honor-level"><div class="v11-honor-medal"><span>★</span><small>NIVEAU</small><b data-v11-honor-level-label>${d.level}</b></div><div class="v11-honor-step"><button type="button" data-v11-honor-minus>−</button><input type="number" min="0" max="999" value="${d.level}" data-v11-honor-level inputmode="numeric"><button type="button" data-v11-honor-plus>+</button></div></section>
      <section class="v11-honor-stats">
        ${['hp','attack','defense'].map(k=>`<label class="v11-honor-stat ${k}"><i>${statIcon(k)}</i><span>${k==='hp'?'PV':k==='attack'?'ATQ':'DEF'}</span><input type="number" min="0" step="1" value="${d[k]}" data-v11-honor-bonus="${k}" inputmode="numeric"><small>+</small></label>`).join('')}
      </section>
      <div class="v11-honor-save"><span>Bonus du héros</span><b>Enregistré automatiquement</b></div>
    </div>`;
  }
  function relabelTabs(sheet){
    const labels={attributes:'Attributs',grade:'Compétences',wall:'Grade',weapon:'Armes exclusives'};
    sheet.querySelectorAll('[data-sheet-tab]').forEach(btn=>{const span=btn.querySelector('span'),id=btn.dataset.sheetTab;if(span&&labels[id]&&span.textContent!==labels[id])span.textContent=labels[id];if(labels[id])btn.setAttribute('aria-label',labels[id])});
  }
  function renderCurrent(force=false){
    if(rendering)return;const sheet=document.querySelector('#heroGameSheet.open');if(!sheet)return;
    relabelTabs(sheet);
    const active=sheet.querySelector('.hero-sheet-tab.active')?.dataset.sheetTab;if(active!=='wall'){wallOpenFor='';return}
    const name=heroName(),cat=catByName(name),h=heroByName(name);if(!cat||!h)return;
    const body=sheet.querySelector('.hero-sheet-body');if(!body)return;
    const mode=wallOpenFor===name?'honor':'grade';
    if(!force&&body.dataset.v11Mode===mode&&body.dataset.v11Hero===name)return;
    rendering=true;
    body.dataset.v11Mode=mode;body.dataset.v11Hero=name;
    body.innerHTML=mode==='honor'?honorPage(cat,h):gradePage(cat,h);
    bind(body,cat,h,mode);
    rendering=false;
  }
  function bind(body,cat,h,mode){
    if(mode==='grade'){
      body.querySelectorAll('[data-v11-grade-tier]').forEach(btn=>btn.addEventListener('click',()=>{const tier=Math.max(0,Math.min(25,Number(btn.dataset.v11GradeTier)||0));setHeroField(cat.name,'stars',tier/5);setTimeout(()=>renderCurrent(true),60)}));
      const go=body.querySelector('[data-v11-open-honor]');if(go&&!go.disabled)go.addEventListener('click',()=>{wallOpenFor=cat.name;renderCurrent(true)});
      return;
    }
    body.querySelector('[data-v11-honor-back]')?.addEventListener('click',()=>{wallOpenFor='';renderCurrent(true)});
    const level=body.querySelector('[data-v11-honor-level]'),label=body.querySelector('[data-v11-honor-level-label]');
    const commitLevel=v=>{const n=Math.max(0,Math.min(999,Math.round(Number(v)||0)));if(level)level.value=String(n);if(label)label.textContent=String(n);saveWallData(cat.name,{level:n})};
    level?.addEventListener('change',()=>commitLevel(level.value));
    body.querySelector('[data-v11-honor-minus]')?.addEventListener('click',()=>commitLevel((Number(level?.value)||0)-1));
    body.querySelector('[data-v11-honor-plus]')?.addEventListener('click',()=>commitLevel((Number(level?.value)||0)+1));
    body.querySelectorAll('[data-v11-honor-bonus]').forEach(input=>{input.addEventListener('input',()=>saveWallData(cat.name,{[input.dataset.v11HonorBonus]:input.value}));input.addEventListener('change',()=>saveWallData(cat.name,{[input.dataset.v11HonorBonus]:input.value}))});
  }
  function queue(){if(queued||rendering)return;queued=true;requestAnimationFrame(()=>{queued=false;renderCurrent()})}
  async function init(){
    try{const r=await fetch(CATALOG_URL,{cache:'no-store'});if(r.ok)catalog=(await r.json()).heroes||[]}catch(e){console.error('WfGg grade/wall v11 catalog',e)}
    document.addEventListener('click',e=>{if(e.target.closest('[data-sheet-tab="wall"]')){wallOpenFor='';setTimeout(()=>renderCurrent(true),30)}else if(e.target.closest('[data-sheet-tab]'))wallOpenFor=''},true);
    new MutationObserver(queue).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
    queue();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
  window.WfGgHeroGradeWallV11=Object.freeze({version:'11.0.0',refresh:()=>renderCurrent(true)});
})();
