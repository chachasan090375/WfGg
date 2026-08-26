(() => {
  'use strict';
  const base=window.WfGgSimulatorEngine;
  const runtime=window.WfGgTacticsCardRuntime;
  if(!base || !runtime) return;
  const n=(v,f=0)=>{const x=Number(v);return Number.isFinite(x)?x:f;};
  function mergedContext(config,tactics){
    const a=config?.contextBonuses||{}, b=tactics?.team||{};
    return {
      attackPct:n(a.attackPct)+n(b.attackPct),
      defensePct:n(a.defensePct)+n(b.defensePct),
      hpPct:n(a.hpPct)+n(b.hpPct),
      damagePct:n(a.damagePct)+n(b.damagePct),
      pveDamagePct:n(a.pveDamagePct)+n(b.pveDamagePct),
      monsterDamagePct:n(a.monsterDamagePct)+n(b.monsterDamagePct),
      monsterDamageReductionPct:n(a.monsterDamageReductionPct)+n(b.monsterDamageReductionPct),
      resistanceFlat:n(a.resistanceFlat)+n(b.resistanceFlat)
    };
  }
  function optimizePlacement(heroes,objectiveId,config={}){
    const tactics=runtime.evaluate(objectiveId);
    const result=base.optimizePlacement(heroes,objectiveId,Object.assign({},config,{contextBonuses:mergedContext(config,tactics)}));
    result.tacticsCards=tactics;
    if(result.best?.score){
      const s=result.best.score;
      s.appliedTacticsCards=tactics.applied;
      s.ignoredTacticsCards=tactics.ignored;
      s.tacticsPhase=tactics.phase;
      s.tacticsContextBonuses=mergedContext({},tactics);
      if(s.mode==='monster'){
        s.frontlineHp*=1+n(tactics.team.hpPct)/100;
        s.frontlineDefense*=1+n(tactics.team.defensePct)/100;
        s.monsterDamageReductionPct=n(tactics.team.monsterDamageReductionPct);
        s.monsterResistanceFlat=n(tactics.team.resistanceFlat);
      }
    }
    return result;
  }
  window.WfGgSimulatorEngine=Object.freeze(Object.assign({},base,{version:base.version+'+tactics-v1',optimizePlacement}));
})();
