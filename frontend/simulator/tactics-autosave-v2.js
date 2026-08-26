(() => {
  'use strict';
  const PROFILE_KEY='wfgg-simulator-profile-v1';
  const TACTICS_KEY='wfgg-simulator-tactics-v2';
  const parse=v=>{try{return JSON.parse(v)||{};}catch(_){return {};}};
  const n=v=>{const x=Number(v);return Number.isFinite(x)?x:0;};
  let pendingTimer=null;

  function readSlot(node){
    const values={};
    node.querySelectorAll('[data-card-value]').forEach(el=>{values[el.dataset.cardValue]=el.value===''?'':n(el.value);});
    return {
      cardId:node.querySelector('[data-card-id]')?.value||'',
      level:n(node.querySelector('[data-card-level]')?.value),
      bonusLevels:n(node.querySelector('[data-card-bonus-levels]')?.value),
      enabled:node.querySelector('[data-card-enabled]')?.checked!==false,
      confirmWantedApplicability:node.querySelector('[data-card-wanted-confirm]')?.checked===true,
      values,
      secondaryText:node.querySelector('[data-card-secondary]')?.value||''
    };
  }

  function serialize(){
    const root=document.querySelector('#tacticsCardsV2');
    if(!root)return null;
    const coreSlots=[...root.querySelectorAll('.tactics-slot[data-kind="core"]')].map(readSlot).slice(0,2);
    const battleSlots=[...root.querySelectorAll('.tactics-slot[data-kind="battle"]')].map(readSlot).slice(0,4);
    while(coreSlots.length<2)coreSlots.push({cardId:'',level:0,bonusLevels:0,enabled:true,confirmWantedApplicability:false,values:{},secondaryText:''});
    while(battleSlots.length<4)battleSlots.push({cardId:'',level:0,bonusLevels:0,enabled:true,confirmWantedApplicability:false,values:{},secondaryText:''});
    return {
      phase:root.querySelector('[data-tactics-phase]')?.value||'season6',
      coreSlots,
      battleSlots,
      globalExpeditionNonCoreTotalLevel:n(root.querySelector('[data-expedition-level]')?.value)
    };
  }

  function persist(){
    if(pendingTimer!==null){clearTimeout(pendingTimer);pendingTimer=null;}
    const state=serialize();if(!state)return;
    localStorage.setItem(TACTICS_KEY,JSON.stringify(state));
    const profile=parse(localStorage.getItem(PROFILE_KEY));
    profile.metadata=profile.metadata||{};
    profile.metadata.schema=profile.metadata.schema||'wfgg-simulator-profile-v1';
    profile.metadata.updatedAt=new Date().toISOString();
    profile.season6=profile.season6||{};
    profile.season6.tacticsV2=state;
    localStorage.setItem(PROFILE_KEY,JSON.stringify(profile));
  }

  function schedulePersist(e){
    if(!e.target?.closest?.('#tacticsCardsV2'))return;
    if(pendingTimer!==null)clearTimeout(pendingTimer);
    pendingTimer=setTimeout(()=>{pendingTimer=null;persist();},20);
  }

  document.addEventListener('input',schedulePersist,true);
  document.addEventListener('change',schedulePersist,true);
  window.addEventListener('pagehide',persist,true);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)persist();},true);
  window.WfGgTacticsAutosave=Object.freeze({version:'2.1.0',serialize,persist});
})();
