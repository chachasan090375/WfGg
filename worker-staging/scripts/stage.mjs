import fs from 'node:fs';
import path from 'node:path';

const here = process.cwd();
const repoRoot = path.resolve(here, '..');
const sourceWorker = path.join(repoRoot, 'worker', 'src');
const sourceBroker = path.join(repoRoot, 'lastwar-broker');
const targetWorker = path.join(here, 'src');
const targetBroker = path.join(here, 'lastwar-broker');

for (const [source, target, label] of [
  [sourceWorker, targetWorker, 'worker source'],
  [sourceBroker, targetBroker, 'Last War broker']
]) {
  if (!fs.existsSync(source)) throw new Error(`Missing ${label}: ${source}`);
  fs.rmSync(target, { recursive: true, force: true });
  fs.cpSync(source, target, { recursive: true });
}

console.log('[wfgg staging] sources staged inside Workers Builds root');
