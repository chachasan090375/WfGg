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

  [trainUi.includes("data?.system?.role === 'OWNER'"), 'Train Sentinel UI remains OWNER-only'],
  [trainUi.includes("portalFetch('/api/sentinel/run')"), 'Train Sentinel can call protected Sentinel endpoint'],
  [trainUi.includes('WFGG_SENTINEL_TRAIN_ROUND_LAUNCHER_V1'), 'round Train launcher design is preserved for safe re-enable'],
  [trainUi.includes('WFGG_SENTINEL_REPORT_V2'), 'copyable Sentinel report format is preserved'],

  [!trainApp.includes('WFGG_SENTINEL_TRAIN_LOADER_V1'), 'native Train boot is isolated from Sentinel while boot regression is fixed'],
  [!trainApp.includes("sentinel-train-v1.js"), 'native Train app has no Sentinel side-load during boot'],

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

console.log('WFGG_SENTINEL_OWNER_TRAIN_BOOT_SAFE_V1=OK');
