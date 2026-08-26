(() => {
  'use strict';
  const PROFILE_KEY='wfgg-simulator-profile-v1';
  const OPTIMIZER_KEY='wfgg-simulator-optimizer-ui-v1';
  const OVERLORD_ID='gorilla-overlord';
  const DEFAULT_NAME='Gorilla Overlord';
  const L={
    fr:{name:'Nom affiché',nameHelp:'Nom libre · valeur par défaut conservée dans la langue d’origine.',optionalStats:'Stats affichées du Gorilla (optionnel)',optionalStatsHelp:'Renseignez-les uniquement si le jeu les affiche séparément. Sinon elles restent hors des totaux ATK/DEF/PV.',attack:'ATK affichée',defense:'DEF affichée',hp:'PV affichés',title:'Synthèse théorique de l’équipe',globalPower:'Puissance globale',globalAttack:'ATK globale',globalDefense:'DEF globale',globalHp:'PV globaux',partial:'partiel',sixth:'6e unité',theory:'Données théoriques : ces totaux utilisent les valeurs affichées enregistrées et n’ajoutent pas les buffs communs à toutes les équipes. Le Gorilla est ajouté uniquement pour les valeurs renseignées.',ranking:'La composition et le placement affichés restent l’ordre recommandé par le moteur pour l’objectif sélectionné, dans le périmètre des effets différentiels actuellement modélisés.'},
    en:{name:'Display name',nameHelp:'Free name · the default remains in the original language.',optionalStats:'Displayed Gorilla stats (optional)',optionalStatsHelp:'Enter only if the game displays them separately. Otherwise they stay outside ATK/DEF/HP totals.',attack:'Displayed ATK',defense:'Displayed DEF',hp:'Displayed HP',title:'Theoretical squad summary',globalPower:'Global Power',globalAttack:'Global ATK',globalDefense:'Global DEF',globalHp:'Global HP',partial:'partial',sixth:'6th unit',theory:'Theoretical data: totals use saved displayed values and do not add buffs common to every squad. Gorilla is added only for values that were entered.',ranking:'The displayed composition and placement remain the engine recommendation for the selected objective, within the differential effects currently modeled.'},
    it:{name:'Nome visualizzato',nameHelp:'Nome libero · il valore predefinito resta nella lingua originale.',optionalStats:'Statistiche Gorilla mostrate (opzionale)',optionalStatsHelp:'Inseriscile solo se il gioco le mostra separatamente. Altrimenti restano fuori dai totali ATK/DIF/PS.',attack:'ATK mostrato',defense:'DIF mostrata',hp:'PS mostrati',title:'Riepilogo teorico della squadra',globalPower:'Potenza globale',globalAttack:'ATK globale',globalDefense:'DIF globale',globalHp:'PS globali',partial:'parziale',sixth:'6ª unità',theory:'Dati teorici: i totali usano i valori mostrati salvati e non aggiungono i buff comuni a tutte le squadre. Il Gorilla viene aggiunto solo per i valori inseriti.',ranking:'La composizione e il posizionamento mostrati restano la raccomandazione del motore per l’obiettivo selezionato, nel perimetro degli effetti differenziali attualmente modellati.'},
    es:{name:'Nombre mostrado',nameHelp:'Nombre libre · el valor predeterminado se conserva en el idioma original.',optionalStats:'Estadísticas mostradas del Gorilla (opcional)',optionalStatsHelp:'Introdúcelas solo si el juego las muestra por separado. De lo contrario quedan fuera de los totales ATQ/DEF/PV.',attack:'ATQ mostrado',defense:'DEF mostrada',hp:'PV mostrados',title:'Resumen teórico de la escuadra',globalPower:'Poder global',globalAttack:'ATQ global',globalDefense:'DEF global',globalHp:'PV globales',partial:'parcial',sixth:'6.ª unidad',theory:'Datos teóricos: los totales usan los valores mostrados guardados y no añaden los buffs comunes a todas las escuadras. El Gorilla solo se añade para los valores introducidos.',ranking:'La composición y la colocación mostradas siguen siendo la recomendación del motor para el objetivo seleccionado, dentro de los efectos diferenciales actualmente modelados.'}
  };
  const lang=()=>L[document.documentElement.lang]?document.documentElement.lang:'fr';
  const t=k=>L[lang()][k]||L.fr[k]||k;
  const esc=v=>String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]||c));
  const num=v=>{const x=Number(v);return Number.isFinite(x)?x:0;};
  const fmt=v=>Math.round(num(v)).toLocaleString(lang()==='fr'?'fr-FR':lang()==='it'?'it-IT':lang()==='es'?'es-ES':'en-US');
  const read=(key)=>{try{return JSON.parse(localStorage.getItem(key))||{};}catch(_){return{};}};
  function profile(){return read(PROFILE_KEY);}
  function optimizerState(p=profile()){
    const direct=read(OPTIMIZER_KEY);
    return Object.keys(direct).length?direct:(p.simulatorUi?.optimizer||{});
  }
  function gorilla(p=profile()){
    const list=Array.isArray(p.overlords)?p.overlords:[];
    return list.find(x=>x?.id===OVERLORD_ID)||null;
  }
  function displayName(g){return String(g?.displayName||'').trim()||DEFAULT_NAME;}
  function saveExtra(field,value){
    const p=profile();p.overlords=Array.isArray(p.overlords)?p.overlords:[];
    let i=p.overlords.findIndex(x=>x?.id===OVERLORD_ID);
    if(i<0){p.overlords.push({id:OVERLORD_ID});i=p.overlords.length-1;}
    p.overlords[i][field]=value;
    p.metadata=p.metadata||{};p.metadata.schema=p.metadata.schema||'wfgg-simulator-profile-v1';p.metadata.updatedAt=new Date().toISOString();
    localStorage.setItem(PROFILE_KEY,JSON.stringify(p));
  }
  function ensureProfileFields(){
    const g=gorilla();if(!g)return;
    let changed=false;
    if(g.displayName==null){g.displayName=DEFAULT_NAME;changed=true;}
    ['displayedAttack','displayedDefense','displayedHp'].forEach(k=>{if(g[k]==null){g[k]=0;changed=true;}});
    if(changed){const p=profile(),i=p.overlords.findIndex(x=>x?.id===OVERLORD_ID);p.overlords[i]=g;localStorage.setItem(PROFILE_KEY,JSON.stringify(p));}
  }
  function ensureNameAndStatsUi(){
    const root=document.querySelector('#overlordProfileV1');if(!root)return;
    const grid=root.querySelector('.form-grid');if(!grid)return;
    const g=gorilla()||{};
    if(!root.querySelector('[data-overlord-extra="displayName"]')){
      grid.insertAdjacentHTML('afterbegin',`<label class="overlord-custom-name">${esc(t('name'))}<input data-overlord-extra="displayName" autocomplete="off" value="${esc(displayName(g))}"><small>${esc(t('nameHelp'))}</small></label>`);
    }
    if(!root.querySelector('.overlord-extra-stats')){
      const details=document.createElement('details');details.className='overlord-extra-stats';details.innerHTML=`<summary>${esc(t('optionalStats'))}</summary><p class="fine-print">${esc(t('optionalStatsHelp'))}</p><div class="form-grid three"><label>${esc(t('attack'))}<input data-overlord-extra="displayedAttack" type="number" min="0" step="1" inputmode="numeric" value="${num(g.displayedAttack)}"></label><label>${esc(t('defense'))}<input data-overlord-extra="displayedDefense" type="number" min="0" step="1" inputmode="numeric" value="${num(g.displayedDefense)}"></label><label>${esc(t('hp'))}<input data-overlord-extra="displayedHp" type="number" min="0" step="1" inputmode="numeric" value="${num(g.displayedHp)}"></label></div>`;
      const note=root.querySelector('.overlord-note');root.insertBefore(details,note||null);
    }
    if(!root.dataset.extraBound){
      root.dataset.extraBound='1';
      root.addEventListener('input',e=>{
        const el=e.target;if(!el.dataset.overlordExtra)return;
        const k=el.dataset.overlordExtra;
        saveExtra(k,el.type==='number'?num(el.value):el.value);
      },true);
      root.addEventListener('change',e=>{
        const el=e.target;if(el.dataset.overlordExtra==='displayName'&&!String(el.value).trim()){
          el.value=DEFAULT_NAME;saveExtra('displayName',DEFAULT_NAME);
        }
      },true);
    }
  }
  function isGorillaIncluded(p,s){
    const slot=num(s.squadSlot)||1;
    if(window.WfGgOverlordRuntime?.allocationState)return !!window.WfGgOverlordRuntime.allocationState(slot,p).included;
    const g=gorilla(p);return !!(g?.owned&&g?.deployable&&num(g.assignedSquadSlot)===slot);
  }
  function theoreticalStats(){
    const p=profile(),s=optimizerState(p),ids=Array.isArray(s.heroes)?s.heroes.filter(Boolean).slice(0,5):[];
    const heroes=ids.map(id=>(p.heroes||[]).find(h=>h?.heroId===id)).filter(Boolean);
    const included=isGorillaIncluded(p,s),g=included?gorilla(p):null;
    const sum=key=>heroes.reduce((a,h)=>a+num(h?.[key]),0)+(g?num(g[key]):0);
    const missing=key=>heroes.length<5||heroes.some(h=>!(num(h?.[key])>0));
    return {p,s,heroes,g,included,power:sum('displayedPower'),attack:sum('displayedAttack'),defense:sum('displayedDefense'),hp:sum('displayedHp'),partialPower:missing('displayedPower'),partialAttack:missing('displayedAttack'),partialDefense:missing('displayedDefense'),partialHp:missing('displayedHp')};
  }
  function tile(label,value,partial){return `<div class="team-theory-tile"><strong>${fmt(value)}</strong><small>${esc(label)}${partial?` · ${esc(t('partial'))}`:''}</small></div>`;}
  function renderSummary(){
    const anchor=document.querySelector('#overlordOptimizerResult')||document.querySelector('#optimizerResult');if(!anchor)return;
    let box=document.querySelector('#teamTheoreticalSummary');if(!box){box=document.createElement('section');box.id='teamTheoreticalSummary';box.className='team-theory-card';anchor.insertAdjacentElement('afterend',box);}
    const x=theoreticalStats(),name=x.g?displayName(x.g):DEFAULT_NAME;
    const sixth=x.included?`<div class="team-theory-sixth">🦍 <strong>${esc(name)}</strong><span>${esc(t('sixth'))}</span></div>`:'';
    const html=`<div class="team-theory-head"><strong>${esc(t('title'))}</strong>${sixth}</div><div class="team-theory-grid">${tile(t('globalPower'),x.power,x.partialPower)}${tile(t('globalAttack'),x.attack,x.partialAttack)}${tile(t('globalDefense'),x.defense,x.partialDefense)}${tile(t('globalHp'),x.hp,x.partialHp)}</div><p class="team-theory-note">${esc(t('theory'))}</p><p class="team-theory-ranking">${esc(t('ranking'))}</p>`;
    if(box.innerHTML!==html)box.innerHTML=html;
  }
  function renderOverlordNameInExistingResult(){
    const box=document.querySelector('#overlordOptimizerResult');if(!box)return;
    const p=profile(),s=optimizerState(p);if(!isGorillaIncluded(p,s))return;
    const g=gorilla(p),name=displayName(g);
    const strong=box.querySelector('strong');if(strong&&!strong.textContent.includes(name))strong.textContent=`🦍 ${name} · ${t('sixth')}`;
  }
  function tick(){ensureProfileFields();ensureNameAndStatsUi();renderOverlordNameInExistingResult();renderSummary();}
  setInterval(tick,350);document.addEventListener('DOMContentLoaded',tick);tick();
  window.WfGgTeamTheory=Object.freeze({version:'1.0.0',DEFAULT_NAME,theoreticalStats,displayName});
})();
