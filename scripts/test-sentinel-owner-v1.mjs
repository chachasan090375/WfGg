import fs from 'node:fs';

const worker = fs.readFileSync('worker/src/index.js', 'utf8');
const ui = fs.readFileSync('frontend/sentinel-owner-v1.js', 'utf8');
const launcher = fs.readFileSync('frontend/sentinel-launcher-v2.js', 'utf8');
const copier = fs.readFileSync('frontend/sentinel-copy-report-v1.js', 'utf8');
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
  [launcher.includes("const LEGACY_MENU_ID = 'wfggSentinelMenu'"), 'launcher depends on OWNER-only Sentinel control'],
  [launcher.includes("const LAUNCHER_ID = 'wfggSentinelLauncher'"), 'dedicated launcher exists beside owner name'],
  [launcher.includes("name?.closest('h2')"), 'launcher anchors beside displayed owner name'],
  [launcher.includes("ownerButton.click()"), 'launcher opens existing protected Sentinel panel'],
  [launcher.includes('max-height:min(86dvh,860px)'), 'Sentinel is presented as a popup rather than a full page'],
  [launcher.includes('#${LEGACY_MENU_ID}{display:none!important}'), 'old profile-menu Sentinel entry is hidden'],
  [copier.includes("const BUTTON_ID = 'wfggSentinelCopyReport'"), 'copy-report action exists in Sentinel popup'],
  [copier.includes('WFGG_SENTINEL_REPORT_V1'), 'copied report has a stable assistant-friendly header'],
  [copier.includes('navigator.clipboard?.writeText'), 'copy action uses modern clipboard API'],
  [copier.includes("document.execCommand('copy')"), 'copy action has Android/browser fallback'],
  [copier.includes("root.querySelectorAll('.wfgg-sentinel-check')"), 'copy action exports rendered Sentinel checks'],
  [copier.includes('Aucune correction automatique effectuée par Sentinel.'), 'copied report states read-only mode'],
  [html.includes('sentinel-owner-v1.js?v=002'), 'Portal loads Sentinel owner UI with cache bust'],
  [html.includes('sentinel-launcher-v2.js?v=002'), 'Portal loads Sentinel launcher popup v2'],
  [html.includes('sentinel-copy-report-v1.js?v=001'), 'Portal loads Sentinel report copy helper']
];

for (const [ok, label] of required) {
  if (!ok) {
    console.error(`SENTINEL_CONTRACT_FAIL: ${label}`);
    process.exit(1);
  }
  console.log(`SENTINEL_CONTRACT_OK: ${label}`);
}

console.log('WFGG_SENTINEL_OWNER_V3=OK');
