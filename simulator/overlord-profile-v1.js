(() => {
  'use strict';
  const PROFILE_KEY='wfgg-simulator-profile-v1';
  const OPTIMIZER_KEY='wfgg-simulator-optimizer-ui-v1';
  const OVERLORD_ID='gorilla-overlord';
  const L={
    fr:{title:'Overlord · 6e unité',text:'Le Gorilla Overlord est une unité auxiliaire distincte des 5 héros. Il n’occupe aucun emplacement héros et ne peut être affecté qu’à une seule escouade à la fois.',owned:'Gorilla débloqué',deployable:'Déployable en escouade',assigned:'Escouade affectée',none:'Non affecté',promotion:'Niveau de promotion',bond:'Bond Rating affiché',power:'Puissance affichée',reference:'Référence uniquement',training:'Entraînement spécialisé',skills:'Compétences Overlord',pending:'terme local à confirmer',accountRule:'Les niveaux d’entraînement sont enregistrés mais ne sont pas ajoutés une seconde fois aux stats héros si leur effet est déjà visible dans les ATK/DEF/PV affichés.',sixth:'6e unité',notOwned:'Gorilla Overlord non débloqué',notDeployable:'Gorilla Overlord possédé mais pas encore déployable',available:'Gorilla Overlord disponible mais non affecté',other:'Gorilla Overlord réservé à une autre escouade',included:'Gorilla Overlord affecté à cette escouade',wanted:'Codes : les effets défensifs ont un poids nul. Riot Shot est bien identifié comme contribution offensive, mais reste hors score numérique tant que sa formule n’est pas calibrée.',monster:'Monstres : le Gorilla est inclus structurellement. Ses effets de survie/réaction restent séparés du score offensif jusqu’à calibration.',future:'L’optimiseur multi-escouades devra choisir une seule équipe pour cet Overlord.'},
    en:{title:'Overlord · 6th unit',text:'Gorilla Overlord is an auxiliary unit separate from the 5 heroes. It consumes no hero slot and can only be assigned to one squad at a time.',owned:'Gorilla unlocked',deployable:'Deployable in squad',assigned:'Assigned squad',none:'Unassigned',promotion:'Promotion level',bond:'Displayed Bond Rating',power:'Displayed Power',reference:'Reference only',training:'Specialized Training',skills:'Overlord Skills',pending:'local game term pending',accountRule:'Training levels are stored but are not added a second time to hero stats when their effect is already reflected in displayed ATK/DEF/HP.',sixth:'6th unit',notOwned:'Gorilla Overlord not unlocked',notDeployable:'Gorilla Overlord owned but not yet deployable',available:'Gorilla Overlord available but unassigned',other:'Gorilla Overlord reserved for another squad',included:'Gorilla Overlord assigned to this squad',wanted:'Wanted: defensive effects have zero weight. Riot Shot is tracked as offensive contribution but remains outside the numeric score until its formula is calibrated.',monster:'Monsters: Gorilla is structurally included. Survival/reactive effects stay separate from offense until calibrated.',future:'The multi-squad optimizer must allocate this Overlord to one squad only.'},
    it:{title:'Overlord · 6ª unità',text:'Il Gorilla Overlord è un’unità ausiliaria separata dai 5 eroi. Non occupa uno slot eroe e può essere assegnato a una sola squadra alla volta.',owned:'Gorilla sbloccato',deployable:'Schierabile in squadra',assigned:'Squadra assegnata',none:'Non assegnato',promotion:'Livello promozione',bond:'Bond Rating mostrato',power:'Potenza mostrata',reference:'Solo riferimento',training:'Specialized Training',skills:'Competenze Overlord',pending:'termine locale da confermare',accountRule:'I livelli di training sono registrati ma non vengono sommati una seconda volta alle statistiche eroe se sono già inclusi in ATK/DIF/PS mostrati.',sixth:'6ª unità',notOwned:'Gorilla Overlord non sbloccato',notDeployable:'Gorilla Overlord posseduto ma non ancora schierabile',available:'Gorilla Overlord disponibile ma non assegnato',other:'Gorilla Overlord riservato a un’altra squadra',included:'Gorilla Overlord assegnato a questa squadra',wanted:'Wanted: gli effetti difensivi hanno peso zero. Riot Shot è tracciato come contributo offensivo ma resta fuori dal punteggio numerico finché la formula non è calibrata.',monster:'Mostri: il Gorilla è incluso strutturalmente. Gli effetti di sopravvivenza/reazione restano separati dall’offesa fino alla calibrazione.',future:'L’ottimizzatore multi-squadra dovrà assegnare questo Overlord a una sola squadra.'},
    es:{title:'Overlord · 6.ª unidad',text:'Gorilla Overlord es una unidad auxiliar separada de los 5 héroes. No ocupa una plaza de héroe y solo puede asignarse a una escuadra a la vez.',owned:'Gorilla desbloqueado',deployable:'Desplegable en escuadra',assigned:'Escuadra asignada',none:'Sin asignar',promotion:'Nivel de promoción',bond:'Bond Rating mostrado',power:'Poder mostrado',reference:'Solo referencia',training:'Specialized Training',skills:'Habilidades Overlord',pending:'término local por confirmar',accountRule:'Los niveles de entrenamiento se guardan pero no se suman de nuevo a las estadísticas de héroes si ya están reflejados en ATQ/DEF/PV mostrados.',sixth:'6.ª unidad',notOwned:'Gorilla Overlord no desbloqueado',notDeployable:'Gorilla Overlord disponible pero aún no desplegable',available:'Gorilla Overlord disponible pero sin asignar',other:'Gorilla Overlord reservado para otra escuadra',included:'Gorilla Overlord asignado a esta escuadra',wanted:'Wanted: los efectos defensivos pesan cero. Riot Shot se registra como contribución ofensiva, pero queda fuera de la puntuación numérica hasta calibrar su fórmula.',monster:'Monstruos: Gorilla se incluye estructuralmente. Los efectos de supervivencia/reacción quedan separados del ataque hasta calibrarlos.',future:'El optimizador multiescuadra deberá asignar este Overlord a una sola escuadra.'}
  };
  const lang=()=>L[document.documentElement.lang]?document.documentElement.lang:'fr';
  const t=k=>L[lang()][k]||L.fr[k]||k;
  const esc=v=>String(v??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]||c));
  const num=v=>{const x=Number(v);return Number.isFinite(x)?x:0;};
  const readJson=(key)=>{try{return JSON.parse(localStorage.getItem(key))||{};}catch(_){return{};}};
  const defaultGorilla=()=>({id:OVERLORD_ID,owned:false,deployable:false,assignedSquadSlot:0,promotionLevel:0,bondRating:'',displayedPower:0,training:{jointAttack:0,defenseSupport:0,survivalTraining:0},skills:{riotShot:0,overlordsArmor:0,brutalRoar:0,furiousHunt:0,expertOverlordUnlocked:false}});

  function profile(){return readJson(PROFILE_KEY);}
  function getGorilla(p=profile()){
    const list=Array.isArray(p.overlords)?p.overlords:[];
    const found=list.find(x=>x?.id===OVERLORD_ID);
    return Object.assign(defaultGorilla(),found||{}, {training:Object.assign(defaultGorilla().training,found?.training||{}),skills:Object.assign(defaultGorilla().skills,found?.skills||{})});
  }
  function saveGorilla(g){
    const p=profile();p.overlords=Array.isArray(p.overlords)?p.overlords:[];
    const i=p.overlords.findIndex(x=>x?.id===OVERLORD_ID);
    const value=JSON.parse(JSON.stringify(g));
    if(i>=0)p.overlords[i]=value;else p.overlords.push(value);
    p.metadata=p.metadata||{};p.metadata.schema=p.metadata.schema||'wfgg-simulator-profile-v1';p.metadata.updatedAt=new Date().toISOString();
    localStorage.setItem(PROFILE_KEY,JSON.stringify(p));
  }
  function maxSquads(){const p=profile();return Math.max(1,Math.min(4,num(p.account?.activeSquads)||3));}
  function squadOptions(value){let s=`<option value="0">${esc(t('none'))}</option>`;for(let i=1;i<=maxSquads();i++)s+=`<option value="${i}" ${num(value)===i?'selected':''}>${i}</option>`;return s;}

  function accountHtml(g){
    const disabled=!(g.owned&&g.deployable)?'disabled':'';
    return `<section id="overlordProfileV1" class="section-card overlord-card">
      <div class="overlord-head"><div class="overlord-title-row"><span class="overlord-icon">🦍</span><div><p class="eyebrow">Overlord</p><strong>${esc(t('title'))}</strong></div></div><span class="overlord-status ${g.owned&&g.deployable?'active':''}">${esc(g.owned?(g.deployable?t('included'):t('notDeployable')):t('notOwned'))}</span></div>
      <p class="muted">${esc(t('text'))}</p>
      <div class="form-grid">
        <label class="toggle-field">${esc(t('owned'))}<input data-overlord="owned" type="checkbox" ${g.owned?'checked':''}></label>
        <label class="toggle-field">${esc(t('deployable'))}<input data-overlord="deployable" type="checkbox" ${g.deployable?'checked':''} ${g.owned?'':'disabled'}></label>
        <label>${esc(t('assigned'))}<select data-overlord="assignedSquadSlot" ${disabled}>${squadOptions(g.assignedSquadSlot)}</select></label>
        <label>${esc(t('promotion'))}<input data-overlord="promotionLevel" type="number" min="0" max="60" value="${num(g.promotionLevel)}" inputmode="numeric"></label>
        <label>${esc(t('bond'))}<input data-overlord="bondRating" value="${esc(g.bondRating)}" autocomplete="off" placeholder="Rookie Partner I"></label>
        <label class="reference-only">${esc(t('power'))}<input data-overlord="displayedPower" type="number" min="0" value="${num(g.displayedPower)}" inputmode="numeric"><small>${esc(t('reference'))}</small></label>
      </div>
      <details><summary>${esc(t('training'))} · <span class="pending-tag">${esc(t('pending'))}</span></summary><div class="form-grid three" style="margin-top:10px">
        <label>Joint Attack<input data-overlord-training="jointAttack" type="number" min="0" max="800" value="${num(g.training.jointAttack)}" inputmode="numeric"></label>
        <label>Defense Support<input data-overlord-training="defenseSupport" type="number" min="0" max="800" value="${num(g.training.defenseSupport)}" inputmode="numeric"></label>
        <label>Survival Training<input data-overlord-training="survivalTraining" type="number" min="0" max="800" value="${num(g.training.survivalTraining)}" inputmode="numeric"></label>
      </div></details>
      <details style="margin-top:10px"><summary>${esc(t('skills'))} · <span class="pending-tag">${esc(t('pending'))}</span></summary><div class="overlord-skill-grid" style="margin-top:10px">
        <label>Riot Shot<input data-overlord-skill="riotShot" type="number" min="0" max="40" value="${num(g.skills.riotShot)}" inputmode="numeric"></label>
        <label>Overlord's Armor<input data-overlord-skill="overlordsArmor" type="number" min="0" max="40" value="${num(g.skills.overlordsArmor)}" inputmode="numeric"></label>
        <label>Brutal Roar<input data-overlord-skill="brutalRoar" type="number" min="0" max="40" value="${num(g.skills.brutalRoar)}" inputmode="numeric"></label>
        <label>Furious Hunt<input data-overlord-skill="furiousHunt" type="number" min="0" max="40" value="${num(g.skills.furiousHunt)}" inputmode="numeric"></label>
        <label class="toggle-field">Expert Overlord<input data-overlord-skill="expertOverlordUnlocked" type="checkbox" ${g.skills.expertOverlordUnlocked?'checked':''}></label>
      </div></details>
      <p class="overlord-note">${esc(t('accountRule'))}</p>
    </section>`;
  }

  function bindAccount(root){
    root.addEventListener('input',e=>{
      const el=e.target,g=getGorilla();
      if(el.dataset.overlord){const k=el.dataset.overlord;g[k]=el.type==='checkbox'?el.checked:(el.type==='number'||k==='assignedSquadSlot'?num(el.value):el.value);if(k==='owned'&&!g.owned){g.deployable=false;g.assignedSquadSlot=0;}if(k==='deployable'&&!g.deployable)g.assignedSquadSlot=0;saveGorilla(g);}
      else if(el.dataset.overlordTraining){g.training[el.dataset.overlordTraining]=num(el.value);saveGorilla(g);}
      else if(el.dataset.overlordSkill){g.skills[el.dataset.overlordSkill]=el.type==='checkbox'?el.checked:num(el.value);saveGorilla(g);}
    },true);
    root.addEventListener('change',e=>{
      const el=e.target;if(!el.matches('[data-overlord="owned"],[data-overlord="deployable"],[data-overlord="assignedSquadSlot"]'))return;
      renderAccount(true);
    },true);
  }

  function renderAccount(force=false){
    const host=document.querySelector('#step-account');if(!host||!host.children.length)return;
    let root=document.querySelector('#overlordProfileV1');const g=getGorilla();
    const html=accountHtml(g);
    if(!root){host.insertAdjacentHTML('beforeend',html);root=document.querySelector('#overlordProfileV1');bindAccount(root);return;}
    if(force){root.outerHTML=html;root=document.querySelector('#overlordProfileV1');bindAccount(root);}
  }

  function allocationState(slot,p=profile()){
    const g=getGorilla(p),s=num(slot)||1;
    if(!g.owned)return{status:'not-owned',included:false,gorilla:g};
    if(!g.deployable)return{status:'not-deployable',included:false,gorilla:g};
    if(!num(g.assignedSquadSlot))return{status:'available',included:false,gorilla:g};
    if(num(g.assignedSquadSlot)!==s)return{status:'assigned-other',included:false,gorilla:g};
    return{status:'included',included:true,gorilla:g};
  }
  function objective(){const u=readJson(OPTIMIZER_KEY);return String(u.objective||'wanted-39');}
  function currentSlot(){const u=readJson(OPTIMIZER_KEY);return num(u.squadSlot)||1;}
  function resultText(a){
    if(a.status==='not-owned')return t('notOwned');if(a.status==='not-deployable')return t('notDeployable');if(a.status==='available')return t('available');if(a.status==='assigned-other')return `${t('other')} · ${a.gorilla.assignedSquadSlot}`;return t('included');
  }
  function renderOptimizer(){
    const out=document.querySelector('#optimizerResult');if(!out)return;
    let box=document.querySelector('#overlordOptimizerResult');if(!box){box=document.createElement('div');box.id='overlordOptimizerResult';out.insertAdjacentElement('afterend',box);}
    const a=allocationState(currentSlot()),isWanted=objective().startsWith('wanted-');
    const html=`<div class="overlord-result"><div class="overlord-result-row"><div><strong>🦍 ${esc(resultText(a))}</strong><small>${esc(a.status==='available'?t('future'):(isWanted?t('wanted'):t('monster')))}</small></div><span class="overlord-sixth">${esc(t('sixth'))}</span></div></div>`;
    if(box.innerHTML!==html)box.innerHTML=html;
  }
  function renderSummary(){
    const host=document.querySelector('#step-summary');if(!host||!host.children.length)return;
    let box=document.querySelector('#overlordSummaryV1');if(!box){box=document.createElement('div');box.id='overlordSummaryV1';host.appendChild(box);}
    const g=getGorilla(),txt=!g.owned?t('notOwned'):!g.deployable?t('notDeployable'):num(g.assignedSquadSlot)?`${t('included')} · ${g.assignedSquadSlot}`:t('available');
    const html=`<div class="section-card overlord-card"><div class="overlord-title-row"><span class="overlord-icon">🦍</span><div><p class="eyebrow">Overlord</p><strong>${esc(txt)}</strong></div></div><p class="overlord-note">${esc(t('future'))}</p></div>`;
    if(box.innerHTML!==html)box.innerHTML=html;
  }

  setInterval(()=>{renderAccount(false);renderOptimizer();renderSummary();},450);
  window.WfGgOverlordRuntime=Object.freeze({version:'1.0.0',OVERLORD_ID,getGorilla,allocationState,objectiveContribution:(objectiveId,slot)=>{const a=allocationState(slot);return{...a,objectiveId,numericScoreAdjustment:0,directOffenseCalibrationPending:a.included&&String(objectiveId).startsWith('wanted-')}}});
})();
