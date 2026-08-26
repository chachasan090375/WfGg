(() => {
  'use strict';

  const POSITIONS=['front-left','front-right','back-left','back-center','back-right'];
  const FRONT=['front-left','front-right'];
  const OBJECTIVES={
    'wanted-39':{group:'wanted',code:39,preferredTroopType:'aircraft',typeDamagePct:50,durationSeconds:90,enemyAttacks:false},
    'wanted-64':{group:'wanted',code:64,preferredTroopType:'missile',typeDamagePct:50,durationSeconds:90,enemyAttacks:false},
    'wanted-87':{group:'wanted',code:87,preferredTroopType:'tank',typeDamagePct:50,durationSeconds:90,enemyAttacks:false},
    'monster-generic':{group:'monster',code:null,preferredTroopType:null,typeDamagePct:0,durationSeconds:null,enemyAttacks:true}
  };

  function n(v,fallback=0){const x=Number(v);return Number.isFinite(x)?x:fallback;}
  function norm(v){return String(v??'').trim().toLowerCase();}
  function permutations(items){if(items.length<=1)return[items.slice()];const out=[];items.forEach((item,index)=>{const rest=items.slice(0,index).concat(items.slice(index+1));permutations(rest).forEach(p=>out.push([item].concat(p)));});return out;}
  function placementFromHeroes(heroes){const map={};POSITIONS.forEach((position,index)=>{map[position]=heroes[index]||null;});return map;}
  function heroAt(placement,position){return placement[position]||null;}
  function entries(placement){return POSITIONS.map(position=>({position,hero:heroAt(placement,position)})).filter(x=>x.hero);}
  function findProviderEntry(placement,heroId){const wanted=norm(heroId);return entries(placement).find(x=>norm(x.hero.heroId)===wanted)||null;}
  function sameRowPositions(position){return position.startsWith('front-')?FR.slice():['back-left','back-center','back-right'];}

  function selectorTargets(effect,placement,geometry){
    const providerEntry=findProviderEntry(placement,effect.providerHeroId);if(!providerEntry)return[];
    const providerPosition=providerEntry.position,provider=providerEntry.hero,all=entries(placement);let targetPositions=[];
    switch(effect.selector){
      case 'self':targetPositions=[providerPosition];break;
      case 'all-allies':targetPositions=POSITIONS.slice();break;
      case 'all-other-allies':targetPositions=POSITIONS.filter(p=>p!==providerPosition);break;
      case 'same-row':targetPositions=sameRowPositions(providerPosition);break;
      case 'front-row':targetPositions=FR.slice();break;
      case 'back-row':targetPositions=['back-left','back-center','back-right'];break;
      case 'adjacent':targetPositions=(geometry?.candidateAdjacencyGraph?.[providerPosition]||[]).slice();break;
      case 'explicit-slots':targetPositions=(effect.explicitSlots||[]).slice();break;
      case 'highest-atk':{const sorted=all.slice().sort((a,b)=>n(b.hero.displayedAttack)-n(a.hero.displayedAttack));targetPositions=sorted.length?[sorted[0].position]:[];break;}
      case 'lowest-atk':{const sorted=all.slice().sort((a,b)=>n(a.hero.displayedAttack)-n(b.hero.displayedAttack));targetPositions=sorted.length?[sorted[0].position]:[];break;}
      case 'same-troop-type':targetPositions=all.filter(x=>x.hero.troopType===provider.troopType).map(x=>x.position);break;
      case 'different-troop-type':targetPositions=all.filter(x=>x.hero.troopType!==provider.troopType).map(x=>x.position);break;
      default:targetPositions=[];
    }
    return targetPositions.map(position=>({position,hero:heroAt(placement,position)})).filter(x=>x.hero).filter(x=>{
      if(effect.troopTypeFilter&&x.hero.troopType!==effect.troopTypeFilter)return false;
      if(effect.roleFilter&&x.hero.role!==effect.roleFilter)return false;
      if(effect.damageTypeFilter&&x.hero.damageType!==effect.damageTypeFilter)return false;
      return true;
    });
  }

  function isEffectActive(effect,objectiveId,options={}){
    if(!effect)return false;
    if(effect.confidence==='needs-in-game-validation'&&!options.includeUnverified)return false;
    if(effect.confidence==='strong-community'&&options.verifiedOnly)return false;
    const objective=OBJECTIVES[objectiveId];if(!objective)return false;
    const contexts=effect.contexts||['all'];
    if(contexts.includes('all')||contexts.includes(objectiveId))return true;
    if(contexts.includes('pve')&&(objective.group==='wanted'||objective.group==='monster'))return true;
    if(contexts.includes('wanted')&&objective.group==='wanted')return true;
    if((contexts.includes('monster')||contexts.includes('monsters'))&&objective.group==='monster')return true;
    return false;
  }

  function effectValue(effect,placement){if(effect.valueSourceField){const provider=findProviderEntry(placement,effect.providerHeroId)?.hero;return provider?n(provider[effect.valueSourceField]):0;}return n(effect.value);}
  function formationAttackPct(heroes){const counts={tank:0,aircraft:0,missile:0};heroes.forEach(h=>{if(counts[h.troopType]!=null)counts[h.troopType]++;});const sorted=Object.values(counts).sort((a,b)=>b-a);if(sorted[0]===5)return 20;if(sorted[0]===4)return 15;if(sorted[0]===3&&sorted[1]===2)return 10;if(sorted[0]===3)return 5;return 0;}

  function baseHeroOffense(hero,objective){
    const attack=n(hero.displayedAttack);let multiplier=1;const offense=hero.offense||{};
    multiplier*=1+n(offense.damagePct)/100;
    multiplier*=1+n(offense.skillDamagePct)/100;
    multiplier*=1+(n(hero.pveDamagePct)+n(offense.pveDamagePct))/100;
    multiplier*=1+(n(hero.monsterDamagePct)+n(offense.monsterDamagePct))/100;
    multiplier*=1+n(offense.attackSpeedPct)/100;
    multiplier*=1+n(offense.cooldownReductionPct)/100;
    if(objective.preferredTroopType&&hero.troopType===objective.preferredTroopType)multiplier*=1+n(objective.typeDamagePct)/100;
    return{attack,multiplier,score:attack*multiplier};
  }

  function applyPositionalEffects(placement,objectiveId,effects,geometry,options={}){
    const modifiers={};entries(placement).forEach(({hero})=>{modifiers[hero.heroId]={attackPct:0,damagePct:0,skillDamagePct:0,critRatePct:0,critDamagePct:0,attackSpeedPct:0,cooldownReductionPct:0,pveDamagePct:0,monsterDamagePct:0,targetDamageTakenPct:0};});
    const applied=[];(effects||[]).forEach(effect=>{if(!isEffectActive(effect,objectiveId,options))return;const value=effectValue(effect,placement);if(!value)return;selectorTargets(effect,placement,geometry).forEach(({hero,position})=>{const m=modifiers[hero.heroId];if(!m)return;const key=effect.stat.endsWith('Pct')?effect.stat:effect.stat+'Pct';if(key in m){m[key]+=value;applied.push({effectId:effect.id,providerHeroId:effect.providerHeroId,targetHeroId:hero.heroId,targetPosition:position,stat:key,value});}});});
    return{modifiers,applied};
  }

  function offensiveScore(placement,objectiveId,config={}){
    const objective=OBJECTIVES[objectiveId];const heroes=entries(placement).map(x=>x.hero);const formationPct=formationAttackPct(heroes);const positional=applyPositionalEffects(placement,objectiveId,config.heroEffects||[],config.geometry||{},config.options||{});let total=0;const heroScores=[];
    heroes.forEach(hero=>{const base=baseHeroOffense(hero,objective);const m=positional.modifiers[hero.heroId]||{};let score=base.score;score*=1+formationPct/100;score*=1+n(m.attackPct)/100;score*=1+n(m.damagePct)/100;score*=1+n(m.skillDamagePct)/100;score*=1+n(m.pveDamagePct)/100;score*=1+n(m.monsterDamagePct)/100;score*=1+n(m.attackSpeedPct)/100;score*=1+n(m.cooldownReductionPct)/100;total+=score;heroScores.push({heroId:hero.heroId,displayedAttack:base.attack,relativeOffenseScore:score});});
    return{relativeOffenseScore:total,formationAttackPct:formationPct,heroScores,appliedPositionalEffects:positional.applied};
  }

  function scoreCodePlacement(placement,objectiveId,config={}){
    const objective=OBJECTIVES[objectiveId];if(!objective||objective.group!=='wanted')throw new Error('Unsupported Code objective: '+objectiveId);const offense=offensiveScore(placement,objectiveId,config);
    return Object.assign({objectiveId,mode:'wanted',code:objective.code,durationSeconds:90,targetMetric:'estimated-total-offensive-output-over-90s',scoreKind:'relative-offense-proxy-not-final-damage-formula',excludedFromScore:['defense','hp','displayedPower'],note:'DEF/HP/Power are excluded from Wanted Code offense because the boss does not attack. They may re-enter only through a verified offensive mechanic.'},offense);
  }

  function scoreMonsterPlacement(placement,config={}){
    const objectiveId='monster-generic',offense=offensiveScore(placement,objectiveId,config),heroes=entries(placement).map(x=>x.hero),frontEntries=FR.map(position=>({position,hero:heroAt(placement,position)})).filter(x=>x.hero);
    const defenseRoleTotal=heroes.filter(h=>norm(h.role)==='defense').length,requiredFrontDefenseCount=Math.min(2,defenseRoleTotal),frontDefenseRoleCount=frontEntries.filter(x=>norm(x.hero.role)==='defense').length;
    const formationFactor=1+offense.formationAttackPct/100;
    const frontlineHp=frontEntries.reduce((sum,x)=>sum+n(x.hero.displayedHp)*formationFactor,0),frontlineDefense=frontEntries.reduce((sum,x)=>sum+n(x.hero.displayedDefense)*formationFactor,0);
    return Object.assign({objectiveId,mode:'monster',targetMetric:'relative-offense-with-frontline-survival-gate',scoreKind:'two-axis-research-proxy-not-final-kill-time-formula',survivalEligible:frontDefenseRoleCount>=requiredFrontDefenseCount,requiredFrontDefenseCount,frontDefenseRoleCount,frontlineHp,frontlineDefense,displayedPowerWeight:0,defenseUsage:'frontline-survival-only',hpUsage:'frontline-survival-only',note:'Monster mode does not combine ATK, DEF and HP into fake Power. Defense-role placement is enforced first; offensive output is optimized inside that survival constraint. HP and DEF remain separate diagnostics until mitigation is calibrated.'},offense);
  }

  function scorePlacement(placement,objectiveId,config={}){const objective=OBJECTIVES[objectiveId];if(!objective)throw new Error('Unsupported objective: '+objectiveId);return objective.group==='wanted'?scoreCodePlacement(placement,objectiveId,config):scoreMonsterPlacement(placement,config);}

  function optimizePlacement(heroes,objectiveId,config={}){
    if(!Array.isArray(heroes)||heroes.length!==5)throw new Error('Exactly five heroes are required for placement optimization.');
    const ids=heroes.map(h=>h.heroId);if(new Set(ids.map(norm)).size!==5||ids.some(x=>!x))throw new Error('Five unique heroId values are required.');
    const objective=OBJECTIVES[objectiveId];if(!objective)throw new Error('Unsupported objective: '+objectiveId);
    const probe=placementFromHeroes(heroes);const activePositional=(config.heroEffects||[]).some(e=>isEffectActive(e,objectiveId,config.options||{})&&effectValue(e,probe)!==0&&findProviderEntry(probe,e.providerHeroId)&&['same-row','front-row','back-row','adjacent','explicit-slots','highest-atk','lowest-atk'].includes(e.selector));
    const candidates=objective.group==='monster'||activePositional?permutations(heroes):[heroes.slice()];let best=null,eligibleCount=0;
    candidates.forEach(order=>{const placement=placementFromHeroes(order),score=scorePlacement(placement,objectiveId,config);if(score.mode==='monster'&&!score.survivalEligible)return;eligibleCount++;if(!best||score.relativeOffenseScore>best.score.relativeOffenseScore||(score.relativeOffenseScore===best.score.relativeOffenseScore&&score.mode==='monster'&&(score.frontlineHp>best.score.frontlineHp||(score.frontlineHp===best.score.frontlineHp&&score.frontlineDefense>best.score.frontlineDefense))))best={placement,score};});
    if(!best)throw new Error('No placement satisfies the monster frontline survival gate.');
    return{objectiveId,mode:objective.group,evaluatedPlacements:candidates.length,eligiblePlacements:eligibleCount,fullPermutationSpace:120,positionalOptimizationActive:activePositional||objective.group==='monster',best};
  }

  window.WfGgSimulatorEngine=Object.freeze({version:'1.2.0-research',POSITIONS:POSITIONS.slice(),OBJECTIVES,permutations,placementFromHeroes,selectorTargets,scoreCodePlacement,scoreMonsterPlacement,scorePlacement,optimizePlacement});
})();
