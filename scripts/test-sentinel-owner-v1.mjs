import fs from 'node:fs';

const worker = fs.readFileSync('worker/src/index.js', 'utf8');
const edge = fs.readFileSync('frontend/_worker.js', 'utf8');
const trainUi = fs.readFileSync('frontend/train-native/sentinel-train-v1.js', 'utf8');
const trainApp = fs.readFileSync('frontend/train-native/app.v15.js', 'utf8');
const migration = fs.readFileSync('worker/migrations/0003_supervisor_sentinel_access.sql', 'utf8');
const html = fs.readFileSync('frontend/index.html', 'utf8');

const required = [
  [worker.includes("import core from './core.js'"), 'worker delegates legacy API to core.js'],
  [worker.includes("url.pathname === '/api/sentinel/run'"), 'legacy Sentinel route remains present'],
  [worker.includes('modifiesPlanning: false'), 'legacy Sentinel declares planning read-only'],
  [worker.includes('automaticFixes: false'), 'legacy Sentinel declares no automatic fixes'],

  [edge.includes('WFGG_SENTINEL_EDGE_ACCESS_V7'), 'production Pages edge uses Sentinel access v7'],
  [edge.includes("['OWNER','SUPERVISOR'].includes(sentinelRole)"), 'server edge authorizes OWNER and SUPERVISOR only'],
  [edge.includes('SENTINEL_ACCESS_FORBIDDEN'), 'unauthorized Sentinel denial is explicit'],
  [edge.includes("script.src='/train/sentinel-train-v1.js?v=007'"), 'Train loads cache-busted Sentinel v7'],
  [edge.includes('readonly:true'), 'production Sentinel remains read-only'],

  [trainUi.includes("['OWNER', 'SUPERVISOR'].includes(accessRole)"), 'Train launcher follows system access role'],
  [trainUi.includes('WFGG_SENTINEL_ACCESS_RETRY_V7'), 'Train retries server-side access validation'],
  [trainUi.includes('WFGG_SENTINEL_LAUNCH_CAPTURE_V7'), 'Android capture launcher is installed'],
  [trainUi.includes('stopImmediatePropagation'), 'launcher isolates click from Train handlers'],
  [trainUi.includes("portalFetch('/api/sentinel/run')"), 'Train Sentinel calls protected edge endpoint'],
  [trainUi.includes('WFGG_SENTINEL_REPORT_V2'), 'copyable report format is preserved'],

  [migration.includes("role IN ('OWNER','SUPERVISOR')"), 'D1 schema supports OWNER and SUPERVISOR'],
  [migration.includes("'flawene','flawen'"), 'Flawene supervisor seed is present'],
  [migration.includes('εlο ツ'), 'Elo canonical supervisor seed is present'],

  [!trainApp.includes('WFGG_SENTINEL_TRAIN_LOADER_V1'), 'native Train boot remains isolated from Sentinel'],
  [!trainApp.includes("sentinel-train-v1.js"), 'native Train app has no Sentinel side-load during boot'],
  [!html.includes('sentinel-owner-v1.js'), 'Portal home does not load old Sentinel owner panel']
];

for (const [ok, label] of required) {
  if (!ok) {
    console.error(`SENTINEL_CONTRACT_FAIL: ${label}`);
    process.exit(1);
  }
  console.log(`SENTINEL_CONTRACT_OK: ${label}`);
}

console.log('WFGG_SENTINEL_OWNER_SUPERVISOR_V7=OK');
