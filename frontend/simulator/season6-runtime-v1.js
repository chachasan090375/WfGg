(() => {
'use strict';
const PROFILE_KEY='wfgg-simulator-profile-v1',TACTICS_KEY='wfgg-simulator-tactics-v2';
const n=v=>{const x=Number(v);return Number.isFinite(x)?x:0;};
function profile(){try{return JSON.parse(localStorage.getItem(PROFILE_KEY))||{};}catch(_){return{};}}
function phase(){try{return(JSON.parse(localStorage.getItem(TACTICS_KEY))||{}).phase||'season6';}catch(_){return'season6';}}
function totemPct(p,type){if(phase()!=='season6')return 0;const t=p.season6?.totemLevels||{};const level=type==='tank'?t.bearTank:type==='aircraft'?t.eagleAircraft:type==='missile'?t.jaguarMissile:0;return Math.max(0,Math.min(30,n(level)))*0.5;}
function decorateHeroes(heroes){const p=profile();return heroes.map(h=>{const pct=totemPct(p,h.troopType);if(!pct)return h;const x={...h,offense:{...(h.offense||{})}};x.offense.damagePct=n(x.offense.damagePct)+pct;return x;});}
function trace(heroes){const p=profile(),active=phase()==='season6';const totals={tank:active?totemPct(p,'tank'):0,aircraft:active?totemPct(p,'aircraft'):0,missile:active?totemPct(p,'missile'):0};const awakeningPending=(heroes||[]).filter(h=>h.awakeningUnlocked&&['kimberly','dva','tesla'].includes(String(h.heroId||'').trim().toLowerCase())).map(h=>({heroId:h.heroId,awakeningStars:n(h.awakeningStars),awakeningTier:n(h.awakeningTier),awakeningSkillLevel:n(h.awakeningSkillLevel),status:'structure-known-skill-curve-not-fully-calibrated'}));return{phase:phase(),totemDamagePct:totals,awakeningPending};}
const engine=window.WfGgSimulatorEngine;
if(engine?.optimizePlacement){const wrapped={...engine,optimizePlacement(heroes,objectiveId,config={}){const decorated=decorateHeroes(heroes),result=engine.optimizePlacement(decorated,objectiveId,config);result.season6=trace(heroes);if(result.best?.score)result.best.score.season6=result.season6;return result;}};window.WfGgSimulatorEngine=Object.freeze(wrapped);}
window.WfGgSeason6Runtime=Object.freeze({version:'1.0.0-research',phase,totemPct,decorateHeroes,trace});
})();
