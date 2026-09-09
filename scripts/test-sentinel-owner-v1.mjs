import fs from 'node:fs';

const worker = fs.readFileSync('worker/src/index.js', 'utf8');
const trainUi = fs.readFileSync('frontend/train-native/sentinel-train-v1.js', 'utf8');
const trainApp = fs.readFileSync('frontend/train-native/app.v15.js', 'utf8');
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

  [trainUi.includes("data?.system?.role === 'OWNER'"), 'Train Sentinel UI only appears for OWNER'],
  [trainUi.includes("portalFetch('/api/sentinel/run')"), 'Train Sentinel calls protected Sentinel endpoint'],
  [trainUi.includes('WFGG_SENTINEL_TRAIN_ROUND_LAUNCHER_V1'), 'round Train launcher design exists'],
  [trainUi.includes('findNameAnchor()'), 'Train launcher anchors beside current player name'],
  [trainUi.includes("button.innerHTML = '<span class=\"wfgg-sentinel-flask\""), 'round launcher contains Sentinel flask icon'],
  [trainUi.includes('max-height:min(88dvh,850px)'), 'Sentinel opens as popup rather than full page'],
  [trainUi.includes('navigator.serviceWorker.getRegistrations'), 'device Service Worker diagnostics exist'],
  [trainUi.includes('pushManager.getSubscription'), 'device Push subscription diagnostics exist'],
  [trainUi.includes('WFGG_SENTINEL_REPORT_V2'), 'copied Train report has stable assistant-friendly header'],
  [trainUi.includes('navigator.clipboard?.writeText'), 'copy action uses modern clipboard API'],
  [trainUi.includes("document.execCommand('copy')"), 'copy action has browser fallback'],
  [trainUi.includes('Aucune correction automatique effectuée par Sentinel.'), 'copied report states read-only mode'],

  [trainApp.includes('WFGG_SENTINEL_TRAIN_LOADER_V1'), 'native Train app loads Sentinel module'],
  [trainApp.includes("script.src = '/train-native/sentinel-train-v1.js?v=001'"), 'native Train loader targets Sentinel asset'],

  [!html.includes('sentinel-owner-v1.js'), 'Portal home no longer loads Sentinel owner panel'],
  [!html.includes('sentinel-launcher-v2.js'), 'Portal home no longer loads old Sentinel launcher'],
  [!html.includes('sentinel-copy-report-v1.js'), 'Portal home no longer loads old Sentinel copy helper']
];

for (const [ok, label] of required) {
  if (!ok) {
    console.error(`SENTINEL_CONTRACT_FAIL: ${label}`);
    process.exit(1);
  }
  console.log(`SENTINEL_CONTRACT_OK: ${label}`);
}

console.log('WFGG_SENTINEL_OWNER_TRAIN_V1=OK');
