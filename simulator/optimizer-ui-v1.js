(() => {
  'use strict';

  const PROFILE_KEY='wfgg-simulator-profile-v1';
  const UI_KEY='wfgg-simulator-optimizer-ui-v1';
  const L={
    fr:{attack:'ATK affichée',power:'Puissance affichée',attackHelp:'Ancre offensive pour les Codes.',powerHelp:'Référence uniquement · poids 0 dans les Codes.',title:'Codes · attaque & placement',text:'Le moteur optimise le placement des 5 héros et ignore DEF, PV et puissance globale pour les Codes. Le score reste un proxy offensif tant que toutes les compétences n’ont pas été calibrées.',objective:'Objectif',team:'Équipe test',slot:'Héros',need5:'Ajoutez au moins 5 héros avec un nom pour tester le placement.',needAttack:'ATK affichée manquante pour :',duplicate:'Chaque emplacement doit contenir un héros différent.',score:'Score offensif relatif',placements:'Placements évalués',positional:'Buffs positionnels appliqués',formation:'Bonus ATK de formation',rule:'Règle Codes',ruleText:'DEF = 0 · PV = 0 · Puissance globale = 0. Seuls les facteurs offensifs vérifiés doivent modifier le classement.',noEffects:'Aucun buff positionnel de héros vérifié n’est encore chargé : le moteur conserve donc l’ordre courant au lieu de prétendre qu’un placement est meilleur.',front:'Ligne avant',back:'Ligne arrière',research:'Mode recherche · pas une prédiction exacte des dégâts 90 s.'},
    en:{attack:'Displayed ATK',power:'Displayed Power',attackHelp:'Offensive anchor for Wanted Codes.',powerHelp:'Reference only · weight 0 for Codes.',title:'Wanted Codes · attack & placement',text:'The engine optimizes the five hero positions and ignores DEF, HP and displayed Power for Wanted Codes. The score remains an offensive proxy until all skills are calibrated.',objective:'Objective',team:'Test squad',slot:'Hero',need5:'Add at least 5 named heroes to test placement.',needAttack:'Missing displayed ATK for:',duplicate:'Each slot must contain a different hero.',score:'Relative offense score',placements:'Placements evaluated',positional:'Positional buffs applied',formation:'Formation ATK bonus',rule:'Code scoring rule',ruleText:'DEF = 0 · HP = 0 · displayed Power = 0. Only verified offensive factors may change the ranking.',noEffects:'No verified hero positional buff is loaded yet, so the engine keeps the current order instead of pretending one placement is better.',front:'Front row',back:'Back row',research:'Research mode · not an exact 90-second damage prediction.'},
    it:{attack:'ATK mostrato',power:'Potenza mostrata',attackHelp:'Base offensiva per i Wanted Code.',powerHelp:'Solo riferimento · peso 0 nei Code.',title:'Wanted Code · attacco e posizione',text:'Il motore ottimizza le cinque posizioni e ignora DIF, PS e Potenza mostrata nei Wanted Code. Il punteggio resta un proxy offensivo finché tutte le abilità non sono calibrate.',objective:'Obiettivo',team:'Squadra test',slot:'Eroe',need5:'Aggiungi almeno 5 eroi con nome per testare il posizionamento.',needAttack:'ATK mostrato mancante per:',duplicate:'Ogni posizione deve contenere un eroe diverso.',score:'Punteggio offensivo relativo',placements:'Posizionamenti valutati',positional:'Buff di posizione applicati',formation:'Bonus ATK formazione',rule:'Regola Code',ruleText:'DIF = 0 · PS = 0 · Potenza = 0. Solo i fattori offensivi verificati devono cambiare la classifica.',noEffects:'Nessun buff posizionale verificato è ancora caricato: il motore mantiene quindi l’ordine corrente.',front:'Prima linea',back:'Seconda linea',research:'Modalità ricerca · non è una previsione esatta dei danni in 90 s.'},
    es:{attack:'ATQ mostrado',power:'Poder mostrado',attackHelp:'Base ofensiva para los Wanted Code.',powerHelp:'Solo referencia · peso 0 en los Code.',title:'Wanted Code · ataque y posición',text:'El motor optimiza las cinco posiciones e ignora DEF, PV y Poder mostrado para los Wanted Code. La puntuación sigue siendo un proxy ofensivo hasta calibrar todas las habilidades.',objective:'Objetivo',team:'Escuadra de prueba',slot:'Héroe',need5:'Añade al menos 5 héroes con nombre para probar el posicionamiento.',needAttack:'Falta ATQ mostrado para:',duplicate:'Cada posición debe contener un héroe diferente.',score:'Puntuación ofensiva relativa',placements:'Posiciones evaluadas',positional:'Buffs posicionales aplicados',formation:'Bonus ATQ de formación',rule:'Regla de los Code',ruleText:'DEF = 0 · PV = 0 · Poder = 0. Solo los factores ofensivos verificados deben cambiar la clasificación.',noEffects:'Todavía no hay ningún buff posicional de héroe verificado cargado; el motor mantiene el orden actual.',front:'Línea delantera',back:'Línea trasera',research:'Modo de investigación · no es una predicción exacta del daño en 90 s.'}
  };

  let formationSchema=null;
  let rendering=false;

  const locale=()=>document.documentElement.lang in L?document.documentElement.lang:'fr';
  const t=k=>L[locale()][k]||L.fr[k]||k;
  const esc=v=>String(v??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  function profile(){try{return JSON.parse(localStorage.getItem(PROFILE_KEY))||{};}catch(_){return {};}}
  function uiState(){try{return Object.assign({objective:'wanted-39',heroes:[]},JSON.parse(localStorage.getItem(UI_KEY))||{});}catch(_){return {objective:'wanted-39',heroes:[]};}}
  function saveUi(s){localStorage.setItem(UI_KEY,JSON.stringify(s));}

  async function loadFormation(){
    if(formationSchema) return formationSchema;
    formationSchema=await fetch('data/formation-positioning.v1.json').then(r=>{if(!r.ok)throw new Error('formation-positioning.v1.json');return r.json();});
    return formationSchema;
  }

  function localizeOptimizerFields(){
    document.querySelectorAll('[data-opt-label="attack"]').forEach(x=>x.textContent=t('attack'));
    document.querySelectorAll('[data-opt-label="power"]').forEach(x=>x.textContent=t('power'));
    document.querySelectorAll('[data-opt-help="attack"]').forEach(x=>x.textContent=t('attackHelp'));
    document.querySelectorAll('[data-opt-help="power"]').forEach(x=>x.textContent=t('powerHelp'));
  }

  function bestGrid(best){
    if(!best?.placement)return '';
    const p=best.placement;
    const card=pos=>`<div class="formation-slot"><small>${esc(pos)}</small><strong>${esc(p[pos]?.heroId||'—')}</strong></div>`;
    return `<div class="formation-caption">${esc(t('front'))}</div><div class="formation-grid front">${card('front-left')}${card('front-right')}</div><div class="formation-caption">${esc(t('back'))}</div><div class="formation-grid back">${card('back-left')}${card('back-center')}${card('back-right')}</div>`;
  }

  function heroSelects(heroes,state){
    const ids=heroes.map(h=>h.heroId).filter(Boolean);
    if(state.heroes.length!==5 || state.heroes.some(id=>!ids.includes(id))) state.heroes=ids.slice(0,5);
    while(state.heroes.length<5) state.heroes.push('');
    const options=value=>`<option value="">—</option>`+ids.map(id=>`<option value="${esc(id)}" ${id===value?'selected':''}>${esc(id)}</option>`).join('');
    return `<div class="optimizer-select-grid">${state.heroes.map((id,i)=>`<label>${esc(t('slot'))} ${i+1}<select data-opt-hero="${i}">${options(id)}</select></label>`).join('')}</div>`;
  }

  async function renderCard(){
    if(rendering) return;
    const host=document.querySelector('#step-summary');
    if(!host || host.querySelector('#codeOptimizerCard')) return;
    rendering=true;
    try{
      const schema=await loadFormation();
      const p=profile();
      const heroes=(p.heroes||[]).filter(h=>h.heroId);
      const s=uiState();
      const card=document.createElement('section');
      card.id='codeOptimizerCard';card.className='section-card optimizer-card';
      let body=`<div class="optimizer-head"><div><p class="eyebrow">WfGg Engine</p><h3>${esc(t('title'))}</h3><p class="muted">${esc(t('text'))}</p></div><span class="status-pill">v1</span></div><div class="optimizer-rule"><strong>${esc(t('rule'))}</strong><span>${esc(t('ruleText'))}</span></div>`;
      if(heroes.length<5){body+=`<div class="optimizer-message">${esc(t('need5'))}</div>`;card.innerHTML=body;host.prepend(card);return;}
      body+=`<div class="optimizer-controls"><label>${esc(t('objective'))}<select id="codeObjective"><option value="wanted-39" ${s.objective==='wanted-39'?'selected':''}>Code 39 · Aircraft +50%</option><option value="wanted-64" ${s.objective==='wanted-64'?'selected':''}>Code 64 · Missile +50%</option><option value="wanted-87" ${s.objective==='wanted-87'?'selected':''}>Code 87 · Tank +50%</option></select></label></div><h4>${esc(t('team'))}</h4>${heroSelects(heroes,s)}<div id="optimizerResult"></div>`;
      card.innerHTML=body;host.prepend(card);saveUi(s);
      card.querySelector('#codeObjective').onchange=e=>{s.objective=e.target.value;saveUi(s);renderResult(card,heroes,s,schema);};
      card.querySelectorAll('[data-opt-hero]').forEach(sel=>sel.onchange=e=>{s.heroes[Number(e.target.dataset.optHero)]=e.target.value;saveUi(s);renderResult(card,heroes,s,schema);});
      renderResult(card,heroes,s,schema);
    }catch(err){console.error(err);}finally{rendering=false;localizeOptimizerFields();}
  }

  function renderResult(card,heroes,s,schema){
    const out=card.querySelector('#optimizerResult');if(!out)return;
    const chosen=s.heroes.map(id=>heroes.find(h=>h.heroId===id)).filter(Boolean);
    if(chosen.length!==5 || new Set(s.heroes).size!==5){out.innerHTML=`<div class="optimizer-message warning">${esc(t('duplicate'))}</div>`;return;}
    const missing=chosen.filter(h=>!Number(h.displayedAttack)>0).map(h=>h.heroId);
    if(missing.length){out.innerHTML=`<div class="optimizer-message warning">${esc(t('needAttack'))} <strong>${esc(missing.join(', '))}</strong></div>`;return;}
    const engine=window.WfGgSimulatorEngine;if(!engine){out.innerHTML='<div class="optimizer-message warning">Engine indisponible.</div>';return;}
    try{
      const result=engine.optimizePlacement(chosen,s.objective,{heroEffects:schema.verifiedHeroEffects||[],geometry:schema.geometry||{},options:{verifiedOnly:true,includeUnverified:false}});
      const score=result.best.score;
      out.innerHTML=`<div class="optimizer-metrics"><div><strong>${score.relativeOffenseScore.toLocaleString()}</strong><small>${esc(t('score'))}</small></div><div><strong>${result.evaluatedPlacements}/${result.fullPermutationSpace}</strong><small>${esc(t('placements'))}</small></div><div><strong>${score.appliedPositionalEffects.length}</strong><small>${esc(t('positional'))}</small></div><div><strong>+${score.formationAttackPct}%</strong><small>${esc(t('formation'))}</small></div></div>${bestGrid(result.best)}${result.positionalOptimizationActive?'':`<div class="optimizer-message info">${esc(t('noEffects'))}</div>`}<p class="fine-print">${esc(t('research'))}</p>`;
    }catch(err){out.innerHTML=`<div class="optimizer-message warning">${esc(err.message)}</div>`;}
  }

  function tick(){localizeOptimizerFields();renderCard();}
  const observer=new MutationObserver(()=>queueMicrotask(tick));
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',()=>{observer.observe(document.body,{childList:true,subtree:true});tick();});
  else {observer.observe(document.body,{childList:true,subtree:true});tick();}
})();
