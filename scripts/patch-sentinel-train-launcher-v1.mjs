import fs from 'node:fs';
import crypto from 'node:crypto';

const appPath = 'frontend/train-native/app.v15.js';
const shaPath = 'frontend/train-native/app.v15.js.sha256';
const marker = 'WFGG_SENTINEL_TRAIN_LOADER_V1';
const loader = `\n\n/* ${marker}\n   Sentinel reste un module séparé : app.v15 ne fait que charger le contrôleur OWNER\n   dans l'interface Train. Aucun changement des règles de rotation ici. */\n(() => {\n  if (window.__WFGG_SENTINEL_TRAIN_LOADER_V1__) return;\n  window.__WFGG_SENTINEL_TRAIN_LOADER_V1__ = true;\n  const script = document.createElement('script');\n  script.src = '/train-native/sentinel-train-v1.js?v=001';\n  script.async = true;\n  script.dataset.wfggSentinelTrain = 'v1';\n  document.head.appendChild(script);\n})();\n`;

let app = fs.readFileSync(appPath, 'utf8');
if (!app.includes(marker)) {
  app = app.replace(/\s*$/, '') + loader;
  fs.writeFileSync(appPath, app, 'utf8');
  console.log('PATCHED: Train Sentinel loader appended');
} else {
  console.log('UNCHANGED: Train Sentinel loader already present');
}

const finalApp = fs.readFileSync(appPath);
const hash = crypto.createHash('sha256').update(finalApp).digest('hex');
fs.writeFileSync(shaPath, `${hash}  ${appPath}\n`, 'utf8');
console.log(`SHA256=${hash}`);
