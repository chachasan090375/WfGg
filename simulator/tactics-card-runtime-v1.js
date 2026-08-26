(() => {
  'use strict';

  const STORAGE_KEY = 'wfgg-simulator-tactics-profile-v1';
  const DEFAULT_STATE = {
    schema:'wfgg-simulator-tactics-profile-v1',
    phase:'season6',
    coreSlots:[
      {cardId:'',level:0,activeSkill:false,values:{},secondaryText:''},
      {cardId:'',level:0,activeSkill:false,values:{},secondaryText:''}
    ],
    battleSlots:[0,1,2,3].map(()=>({cardId:'',baseLevel:0,bonusLevels:0,values:{},confirmWantedApplicability:false,secondaryText:''})),
    updatedAt:null
  };

  const n = (v,f=0) => { const x=Number(v); return Number.isFinite(x)?x:f; };
  const clone = x => JSON.parse(JSON.stringify(x));

  function normalizeState(raw){
    const out=clone(DEFAULT_STATE);
    if(!raw || raw.schema!==DEFAULT_STATE.schema) return out;
    out.phase = raw.phase==='offseason'?'offseason':'season6';
    if(Array.isArray(raw.coreSlots)) out.coreSlots = out.coreSlots.map((d,i)=>Object.assign(d,raw.coreSlots[i]||{}, {values:Object.assign({},d.values,raw.coreSlots[i]?.values||{})}));
    if(Array.isArray(raw.battleSlots)) out.battleSlots = out.battleSlots.map((d,i)=>Object.assign(d,raw.battleSlots[i]||{}, {values:Object.assign({},d.values,raw.battleSlots[i]?.values||{})}));
    out.updatedAt=raw.updatedAt||null;
    return out;
  }

  function getState(){
    try{return normalizeState(JSON.parse(localStorage.getItem(STORAGE_KEY)));}
    catch(_){return clone(DEFAULT_STATE);}
  }

  function saveState(state){
    const clean=normalizeState(Object.assign({},state,{schema:DEFAULT_STATE.schema}));
    clean.updatedAt=new Date().toISOString();
    localStorage.setItem(STORAGE_KEY,JSON.stringify(clean));
    return clean;
  }

  function add(team,key,value){team[key]=(team[key]||0)+n(value);}

  function evaluate(objectiveId){
    const state=getState();
    const team={attackPct:0,defensePct:0,hpPct:0,damagePct:0,pveDamagePct:0,monsterDamagePct:0,monsterDamageReductionPct:0,resistanceFlat:0};
    const applied=[],ignored=[];
    const isWanted=/^wanted-/.test(objectiveId);
    const isMonster=objectiveId==='monster-generic';

    state.coreSlots.forEach((slot,index)=>{
      if(!slot.cardId) return;
      if(slot.cardId==='core-purgator-monster-slayer'){
        if(isMonster && slot.activeSkill){
          add(team,'monsterDamageReductionPct',slot.values.monsterDamageReductionPct);
          add(team,'resistanceFlat',slot.values.resistanceFlat);
          applied.push({slotType:'core',slot:index+1,cardId:slot.cardId,effect:'monster-survival',values:clone(slot.values)});
        } else ignored.push({slotType:'core',slot:index+1,cardId:slot.cardId,reason:isMonster?'active-skill-not-enabled':'context-mismatch'});
      } else {
        ignored.push({slotType:'core',slot:index+1,cardId:slot.cardId,reason:'stored-not-yet-scored'});
      }
    });

    state.battleSlots.forEach((slot,index)=>{
      if(!slot.cardId) return;
      if(state.phase!=='season6'){
        ignored.push({slotType:'battle',slot:index+1,cardId:slot.cardId,reason:'offseason-inactive'});
        return;
      }
      if(slot.cardId==='universal-zombie-killer'){
        const allowed=isMonster || (isWanted && slot.confirmWantedApplicability===true);
        if(allowed){
          add(team,'attackPct',slot.values.attackPct);
          add(team,'defensePct',slot.values.defensePct);
          add(team,'hpPct',slot.values.hpPct);
          applied.push({slotType:'battle',slot:index+1,cardId:slot.cardId,effect:isMonster?'world-pve':'wanted-manually-confirmed',values:clone(slot.values)});
        } else ignored.push({slotType:'battle',slot:index+1,cardId:slot.cardId,reason:isWanted?'wanted-not-confirmed':'context-mismatch'});
      } else {
        ignored.push({slotType:'battle',slot:index+1,cardId:slot.cardId,reason:'context-not-supported-by-current-pve-engine'});
      }
    });

    return {phase:state.phase,team,applied,ignored};
  }

  window.WfGgTacticsCardRuntime=Object.freeze({
    version:'1.0.0-research', STORAGE_KEY, DEFAULT_STATE:clone(DEFAULT_STATE), getState, saveState, evaluate
  });
})();
