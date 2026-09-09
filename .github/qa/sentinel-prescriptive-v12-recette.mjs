import fs from 'node:fs';
import assert from 'node:assert/strict';

const worker=fs.readFileSync('frontend/_worker.js','utf8');
const client=fs.readFileSync('frontend/train-native/sentinel-train-v1.js','utf8');

assert.match(worker,/WFGG_SENTINEL_PRESCRIPTIVE_EDGE_V12/);
assert.match(worker,/\/api\/sentinel\/repair-plan\?/);
assert.match(worker,/X-WfGg-Sentinel-Diagnostic':'v12'/);
assert.match(worker,/repairPlan,/);
assert.match(worker,/readonly:true,applied:false/);
assert.match(worker,/sentinel-train-v1\.js\?v=013/);

assert.match(client,/const VERSION = 'sentinel-train-v12'/);
assert.match(client,/WFGG_SENTINEL_REPORT_V5/);
assert.match(client,/WFGG_SENTINEL_LOCAL_REPAIR_V12/);
assert.match(client,/localRepairCandidatesV12/);
assert.match(client,/repairRecommended/);
assert.match(client,/renderRepairPlanV12/);
assert.match(client,/CORRECTIFS SIMULÉS/);
assert.match(client,/AUCUN CORRECTIF APPLIQUÉ/);
assert.match(client,/Appliqué: NON/);

// Edge V12 may only observe/call GET diagnostics; no mutation methods.
const edgeStart=worker.indexOf('/* WFGG_SENTINEL_PRESCRIPTIVE_EDGE_V12');
const edgeEnd=worker.indexOf('const counts=',edgeStart);
assert.ok(edgeStart>=0&&edgeEnd>edgeStart);
const edge=worker.slice(edgeStart,edgeEnd);
for(const forbidden of ["method:'POST'","method:'PUT'","method:'DELETE'",'saveState(','INSERT INTO','UPDATE app_state','DELETE FROM']){
  assert.equal(edge.includes(forbidden),false,`edge V12 contains mutation: ${forbidden}`);
}

// Local proposals are descriptors only: they must not call fetch or user actions.
const localStart=client.indexOf('/* WFGG_SENTINEL_LOCAL_REPAIR_V12');
const localEnd=client.indexOf('async function runSentinel()',localStart);
assert.ok(localStart>=0&&localEnd>localStart);
const local=client.slice(localStart,localEnd);
for(const forbidden of ['fetch(','.click(','pushManager.subscribe(','serviceWorker.register(','localStorage.setItem(']){
  assert.equal(local.includes(forbidden),false,`local V12 proposal executes action: ${forbidden}`);
}

for(const id of [
  'repair-local-notification-export-v12','repair-push-sw-register-v12','repair-local-push-subscribe-v12',
  'repair-notification-permission-v12','repair-ui-export-contract-v12','repair-calendar-runtime-v12'
]) assert.ok(client.includes(id),`missing local repair candidate ${id}`);

console.log('SENTINEL_PRESCRIPTIVE_PORTAL_V12=PASS observer-only=1 report-v5=1 repair-rendering=1');
