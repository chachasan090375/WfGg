(() => {
  'use strict';
  const STORAGE_KEY='wfgg-simulator-tactics-v2';
  const RULES={
    'universal-zombie-killer':{availability:'season6-only',contexts:['world-pve'],score:{attackPct:'attackPct'},survival:{defensePct:'defensePct',hpPct:'hpPct'}},
    'core-purgator-monster-slayer':{availability:'season-and-offseason',contexts:['pve-monsters'],survival:{monsterDamageReductionPct:'monsterDamageReductionPct'}},
    'universal-dimensional-crit':{availability:'season6-only',contexts:['pvp']},
    'universal-frontal-suppression':{availability:'season6-only',contexts:['pvp']},
    'universal-aftermath-burst':{availability:'season6-only',contexts:['pvp']},
    'universal-counter-reversal':{availability:'season6-only',contexts:['pvp-countered']},
    'universal-hybrid-squad':{availability:'legacy-not-season6',contexts:['pvp']}
  };
  const OBJECTIVE_CONTEXTS={
    'wanted-39':['wanted-39','wanted'],
    'wanted-64':['wanted-64','wanted'],
    'wanted-87':['wanted-87','wanted'],
    'monster-generic':['world-pve','pve-monsters','monster']
  };
  const n=v=>{const x=Number(v);return Number.isFinite(x)?x:0;};
  function state(){
    try{return JSON.parse(localStorage.getItem(STORAGE_KEY))||{};}catch(_){return {};}
  }
  function available(rule,phase,kind){
    if(kind==='battle'&&phase!=='season6') return false;
    if(rule?.availability==='legacy-not-season6'&&phase==='season6') return false;
    if(rule?.availability==='season6-only'&&phase!=='season6') return false;
    return true;
  }
  function slots(s){
    const out=[];
    (s.coreSlots||[]).forEach((x,i)=>out.push({...x,kind:'core',slot:i+1}));
    (s.battleSlots||[]).forEach((x,i)=>out.push({...x,kind:'battle',slot:i+1}));
    return out;
  }
  function resolve(objectiveId){
    const s=state(),phase=s.phase||'season6',contexts=OBJECTIVE_CONTEXTS[objectiveId]||[];
    const contextBonuses={attackPct:0,damagePct:0,pveDamagePct:0,monsterDamagePct:0};
    const survival={defensePct:0,hpPct:0,monsterDamageReductionPct:0};
    const applied=[],ignored=[];
    slots(s).forEach(slot=>{
      if(!slot.cardId||slot.enabled===false) return;
      const rule=RULES[slot.cardId];
      if(!rule){ignored.push({cardId:slot.cardId,reason:'catalogued-no-runtime-rule'});return;}
      if(!available(rule,phase,slot.kind)){ignored.push({cardId:slot.cardId,reason:'inactive-in-current-phase'});return;}
      if(!(rule.contexts||[]).some(c=>contexts.includes(c))){ignored.push({cardId:slot.cardId,reason:'context-mismatch'});return;}
      const values=slot.values||{},entry={cardId:slot.cardId,kind:slot.kind,slot:slot.slot,values:{}};
      Object.entries(rule.score||{}).forEach(([target,source])=>{const v=n(values[source]);if(v){contextBonuses[target]=(contextBonuses[target]||0)+v;entry.values[target]=v;}});
      Object.entries(rule.survival||{}).forEach(([target,source])=>{const v=n(values[source]);if(v){survival[target]=(survival[target]||0)+v;entry.values[target]=v;}});
      applied.push(entry);
    });
    return {phase,objectiveId,contextBonuses,survival,applied,ignored};
  }
  function mergeBonuses(base,extra){const out={...(base||{})};Object.entries(extra||{}).forEach(([k,v])=>out[k]=n(out[k])+n(v));return out;}
  const api={version:'1.0.0-research',STORAGE_KEY,resolve,state};
  window.WfGgTacticsRuntime=Object.freeze(api);
  const engine=window.WfGgSimulatorEngine;
  if(engine?.optimizePlacement){
    const wrapped={...engine,optimizePlacement(heroes,objectiveId,config={}){
      const card=resolve(objectiveId);
      const merged={...config,contextBonuses:mergeBonuses(config.contextBonuses,card.contextBonuses)};
      const result=engine.optimizePlacement(heroes,objectiveId,merged);
      result.tactics=card;
      if(result.best?.score){
        result.best.score.appliedTactics=card.applied;
        result.best.score.tacticsPhase=card.phase;
        if(result.best.score.mode==='monster'){
          result.best.score.frontlineHp*=1+n(card.survival.hpPct)/100;
          result.best.score.frontlineDefense*=1+n(card.survival.defensePct)/100;
          result.best.score.monsterDamageReductionPct=n(card.survival.monsterDamageReductionPct);
        }
      }
      return result;
    }};
    window.WfGgSimulatorEngine=Object.freeze(wrapped);
  }
})();
