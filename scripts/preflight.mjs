import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const required = [
  'frontend/index.html', 'frontend/styles.css', 'frontend/app.js', 'frontend/config.js',
  'frontend/_headers', 'frontend/manifest.webmanifest', 'worker/src/index.js',
  'worker/migrations/0001_initial.sql', 'worker/wrangler.jsonc', 'worker/package.json',
  'README.md', 'docs/ARCHITECTURE.md', 'docs/DECISIONS.md', 'docs/DEPLOYMENT_NOTES.md', 'docs/STATUS.md'
];

let failed = false;
for (const rel of required) {
  if (!fs.existsSync(path.join(root, rel))) {
    console.error(`MISSING ${rel}`);
    failed = true;
  }
}

const html = fs.readFileSync(path.join(root, 'frontend/index.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'frontend/app.js'), 'utf8');
const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]));
const jsIds = new Set([...js.matchAll(/\$\('([^']+)'\)/g)].map((m) => m[1]));
for (const id of jsIds) {
  if (!ids.has(id)) {
    console.error(`JS references missing HTML id: ${id}`);
    failed = true;
  }
}

for (const rank of ['R1','R2','R3','R4','R5']) {
  if (!js.includes(`'${rank}'`) || !fs.readFileSync(path.join(root, 'worker/migrations/0001_initial.sql'), 'utf8').includes(`'${rank}'`)) {
    console.error(`Rank missing from frontend/schema: ${rank}`);
    failed = true;
  }
}

JSON.parse(fs.readFileSync(path.join(root, 'frontend/manifest.webmanifest'), 'utf8'));
JSON.parse(fs.readFileSync(path.join(root, 'worker/package.json'), 'utf8'));
JSON.parse(fs.readFileSync(path.join(root, 'worker/wrangler.jsonc'), 'utf8'));

if (failed) process.exit(1);
console.log('WFGG Portal preflight: OK');
