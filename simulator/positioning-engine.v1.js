(() => {
  'use strict';

  const POSITIONS = ['front-left','front-right','back-left','back-center','back-right'];
  const CODE_OBJECTIVES = {
    'wanted-39': {code:39, preferredTroopType:'aircraft', typeDamagePct:50, durationSeconds:90},
    'wanted-64': {code:64, preferredTroopType:'missile', typeDamagePct:50, durationSeconds:90},
    'wanted-87': {code:87, preferredTroopType:'tank', typeDamagePct:50, durationSeconds:90}
  };

  function n(v, fallback=0){const x=Number(v);return Number.isFinite(x)?x:fallback;}
  function norm(v){return String(v??'').trim().toLowerCase();}

  function permutations(items){
    if(items.length<=1) return [items.slice()];
    const out=[];
    items.forEach((item,index)=>{
      const rest=items.slice(0,index).concat(items.slice(index+1));
      permutations(rest).forEach(p=>out.push([item].concat(p)));
    });
    return out;
  }

  function placementFromHeroes(heroes){
    const map={};
    POSITIONS.forEach((position,index)=>{map[position]=heroes[index]||null;});
    return map;
  }

  function heroAt(placement, position){return placement[position]||null;}
  function entries(placement){return POSITIONS.map(position=>({position,hero:heroAt(placement,position)})).filter(x=>x.hero);}
  function findProviderEntry(placement, heroId){const wanted=norm(heroId);return entries(placement).find(x=>norm(x.hero.heroId)===wanted)||null;}
  function findProviderPosition(placement, heroId){return findProviderEntry(placement,heroId)?.position||null;}

  function sameRowPositions(position){
    return position.startsWith('front-') ? ['front-left','front-right'] : ['back-left','back-center','back-right'];
  }

  function selectorTargets(effect, placement, geometry){
    const providerEntry=findProviderEntry(placement,effect.providerHeroId);
    if(!providerEntry) return [];
    const providerPosition=providerEntry.position, provider=providerEntry.hero, all=entries(placement);
    let targetPositions=[];
    switch(effect.selector){
      case 'self': targetPositions=[providerPosition]; break;
      case 'all-allies': targetPositions=POSITIONS.slice(); break;
      case 'all-other-allies': targetPositions=POSITIONS.filter(p=>p!==providerPosition); break;
      case 'same-row': targetPositions=sameRowPositions(providerPosition); break;
      case 'front-row': targetPositions=['front-left','front-right']; break;
      case 'back-row': targetPositions=['back-left','back-center','back-right']; break;
      case 'adjacent': targetPositions=(geometry?.candidateAdjacencyGraph?.[providerPosition]||[]).slice(); break;
      case 'explicit-slots': targetPositions=(effect.explicitSlots||[]).slice(); break;
      case 'highest-atk': {
        const sorted=all.slice().sort((a,b)=>n(b.hero.displayedAttack)-n(a.hero.displayedAttack));
        targetPositions=sorted.length?[sorted[0].position]:[]; break;
      }
      case 'lowest-atk': {
        const sorted=all.slice().sort((a,b)=>n(a.hero.displayedAttack)-n(b.hero.displayedAttack));
        targetPositions=sorted.length?[sorted[0].position]:[]; break;
      }
      case 'same-troop-type': targetPositions=all.filter(x=>x.hero.troopType===provider.troopType).map(x=>x.position); break;
      case 'different-troop-type': targetPositions=all.filter(x=>x.hero.troopType!==provider.troopType).map(x=>x.position); break;
      default: targetPositions=[];
    }
    return targetPositions.map(position=>({position,hero:heroAt(placement,position)})).filter(x=>x.hero).filter(x=>{
      if(effect.troopTypeFilter && x.hero.troopType!==effect.troopTypeFilter) return false;
      if(effect.roleFilter && x.hero.role!==effect.roleFilter) return false;
      if(effect.damageTypeFilter && x.hero.damageType!==effect.damageTypeFilter) return false;
      return true;
    });
  }

  function isEffectActive(effect, objectiveId, options={}){
    if(!effect) return false;
    if(effect.confidence==='needs-in-game-validation' && !options.includeUnverified) return false;
    if(effect.confidence==='strong-community' && options.verifiedOnly) return false;
    const contexts=effect.contexts||['all'];
    return contexts.includes('all') || contexts.includes('pve') || contexts.includes('wanted') || contexts.includes(objectiveId);
  }

  function effectValue(effect, placement){
    if(effect.valueSourceField){
      const provider=findProviderEntry(placement,effect.providerHeroId)?.hero;
      return provider?n(provider[effect.valueSourceField]):0;
    }
    return n(effect.value);
  }

  function formationAttackPct(heroes){
    const counts={tank:0,aircraft:0,missile:0};
    heroes.forEach(h=>{if(counts[h.troopType]!=null) counts[h.troopType]++;});
    const sorted=Object.values(counts).sort((a,b)=>b-a);
    if(sorted[0]===5) return 20;
    if(sorted[0]===4) return 15;
    if(sorted[0]===3 && sorted[1]===2) return 10;
    if(sorted[0]===3) return 5;
    return 0;
  }

  function baseHeroOffense(hero, objective){
    const attack=n(hero.displayedAttack);
    let multiplier=1;
    const offense=hero.offense||{};
    multiplier*=1+n(offense.damagePct)/100;
    multiplier*=1+n(offense.skillDamagePct)/100;
    multiplier*=1+n(offense.pveDamagePct)/100;
    multiplier*=1+n(offense.monsterDamagePct)/100;
    multiplier*=1+n(offense.attackSpeedPct)/100;
    multiplier*=1+n(offense.cooldownReductionPct)/100;
    if(hero.troopType===objective.preferredTroopType) multiplier*=1+objective.typeDamagePct/100;
    return {attack,multiplier,score:attack*multiplier};
  }

  function applyPositionalEffects(placement, objectiveId, effects, geometry, options={}){
    const modifiers={};
    entries(placement).forEach(({hero})=>{modifiers[hero.heroId]={attackPct:0,damagePct:0,skillDamagePct:0,critRatePct:0,critDamagePct:0,attackSpeedPct:0,cooldownReductionPct:0,pveDamagePct:0,monsterDamagePct:0,targetDamageTakenPct:0};});
    const applied=[];
    (effects||[]).forEach(effect=>{
      if(!isEffectActive(effect,objectiveId,options)) return;
      const value=effectValue(effect,placement);
      if(!value) return;
      const targets=selectorTargets(effect,placement,geometry);
      targets.forEach(({hero,position})=>{
        const m=modifiers[hero.heroId]; if(!m) return;
        const key=effect.stat.endsWith('Pct')?effect.stat:effect.stat+'Pct';
        if(key in m){m[key]+=value;applied.push({effectId:effect.id,providerHeroId:effect.providerHeroId,targetHeroId:hero.heroId,targetPosition:position,stat:key,value});}
      });
    });
    return {modifiers,applied};
  }

  function scoreCodePlacement(placement, objectiveId, config={}){
    const objective=CODE_OBJECTIVES[objectiveId];
    if(!objective) throw new Error('Unsupported Code objective: '+objectiveId);
    const heroes=entries(placement).map(x=>x.hero);
    const formationPct=formationAttackPct(heroes);
    const positional=applyPositionalEffects(placement,objectiveId,config.heroEffects||[],config.geometry||{},config.options||{});
    let total=0;
    const heroScores=[];
    heroes.forEach(hero=>{
      const base=baseHeroOffense(hero,objective);
      const m=positional.modifiers[hero.heroId]||{};
      let score=base.score;
      score*=1+formationPct/100;
      score*=1+n(m.attackPct)/100;
      score*=1+n(m.damagePct)/100;
      score*=1+n(m.skillDamagePct)/100;
      score*=1+n(m.pveDamagePct)/100;
      score*=1+n(m.monsterDamagePct)/100;
      score*=1+n(m.attackSpeedPct)/100;
      score*=1+n(m.cooldownReductionPct)/100;
      total+=score;
      heroScores.push({heroId:hero.heroId,displayedAttack:base.attack,relativeOffenseScore:score,defenseWeight:0,hpWeight:0,displayedPowerWeight:0});
    });
    return {
      objectiveId,
      code:objective.code,
      durationSeconds:objective.durationSeconds,
      targetMetric:'estimated-total-offensive-output-over-90s',
      scoreKind:'relative-offense-proxy-not-final-damage-formula',
      relativeOffenseScore:total,
      formationAttackPct:formationPct,
      heroScores,
      appliedPositionalEffects:positional.applied,
      excludedFromScore:['defense','hp','displayedPower'],
      note:'DEF/HP/Power are intentionally excluded for Codes because the boss does not attack. They may only re-enter later if a verified offensive skill explicitly scales from or triggers on one of those stats.'
    };
  }

  function optimizePlacement(heroes, objectiveId, config={}){
    if(!Array.isArray(heroes)||heroes.length!==5) throw new Error('Exactly five heroes are required for placement optimization.');
    const ids=heroes.map(h=>h.heroId);
    if(new Set(ids.map(norm)).size!==5 || ids.some(x=>!x)) throw new Error('Five unique heroId values are required.');
    const probe=placementFromHeroes(heroes);
    const activePositional=(config.heroEffects||[]).some(e=>isEffectActive(e,objectiveId,config.options||{}) && effectValue(e,probe)!==0 && findProviderEntry(probe,e.providerHeroId) && ['same-row','front-row','back-row','adjacent','explicit-slots','highest-atk','lowest-atk'].includes(e.selector));
    const candidates=activePositional?permutations(heroes):[heroes.slice()];
    let best=null;
    candidates.forEach(order=>{
      const placement=placementFromHeroes(order);
      const score=scoreCodePlacement(placement,objectiveId,config);
      if(!best || score.relativeOffenseScore>best.score.relativeOffenseScore){best={placement,score};}
    });
    return {objectiveId,evaluatedPlacements:candidates.length,fullPermutationSpace:120,positionalOptimizationActive:activePositional,best};
  }

  window.WfGgSimulatorEngine = Object.freeze({
    version:'1.1.0-research',
    POSITIONS:POSITIONS.slice(),
    CODE_OBJECTIVES,
    permutations,
    placementFromHeroes,
    selectorTargets,
    scoreCodePlacement,
    optimizePlacement
  });
})();
