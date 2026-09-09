import fs from 'node:fs';

const worker = fs.readFileSync('worker/src/index.js', 'utf8');
const ui = fs.readFileSync('frontend/sentinel-owner-v1.js', 'utf8');
const html = fs.readFileSync('frontend/index.html', 'utf8');

const required = [
  [worker.includes("import core from './core.js'"), 'worker delegates legacy API to core.js'],
  [worker.includes("url.pathname === '/api/sentinel/run'"), 'owner-only Sentinel route exists'],
  [worker.includes("meCall.data?.system?.role !== 'OWNER'"), 'server enforces OWNER role'],
  [worker.includes("SENTINEL_OWNER_ONLY"), 'non-owner denial is explicit'],
  [worker.includes("modifiesPlanning: false"), 'Sentinel declares planning read-only'],
  [worker.includes("automaticFixes: false"), 'Sentinel declares no automatic fixes'],
  [worker.includes('portal-train-snapshot-bridge'), 'Portal→Train snapshot check exists'],
  [worker.includes('train-runtime-contract'), 'live runtime contract check exists'],
  [worker.includes('rotation-rank-contract'), 'rotation business rule check exists'],
  [ui.includes("data?.system?.role === 'OWNER'"), 'UI only appears for OWNER'],
  [ui.includes("fetch('/api/sentinel/run'"), 'UI calls Sentinel endpoint'],
  [ui.includes('navigator.serviceWorker.getRegistrations'), 'device Service Worker diagnostics exist'],
  [ui.includes('pushManager.getSubscription'), 'device Push subscription diagnostics exist'],
  [html.includes('sentinel-owner-v1.js?v=001'), 'Portal loads Sentinel UI']
];

for (const [ok, label] of required) {
  if (!ok) {
    console.error(`SENTINEL_CONTRACT_FAIL: ${label}`);
    process.exit(1);
  }
  console.log(`SENTINEL_CONTRACT_OK: ${label}`);
}

console.log('WFGG_SENTINEL_OWNER_V1=OK');
