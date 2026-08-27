import fs from 'node:fs';
import path from 'node:path';

const here = process.cwd();
const repoRoot = path.resolve(here, '..');
const sourceWorker = path.join(repoRoot, 'worker', 'src');
const targetWorker = path.join(here, 'src');
const overrideIdentity = path.join(here, 'overrides', 'lastwar-identity.js');

if (!fs.existsSync(sourceWorker)) throw new Error(`Missing worker source: ${sourceWorker}`);
if (!fs.existsSync(overrideIdentity)) throw new Error(`Missing external broker override: ${overrideIdentity}`);

fs.rmSync(targetWorker, { recursive: true, force: true });
fs.cpSync(sourceWorker, targetWorker, { recursive: true });
fs.copyFileSync(overrideIdentity, path.join(targetWorker, 'lastwar-identity.js'));

const indexPath = path.join(targetWorker, 'index.js');
let indexText = fs.readFileSync(indexPath, 'utf8');
indexText = indexText.replace("export { LastWarUserContainer } from './lastwar-container.js';\n", '');
indexText = indexText.replace("version: '0.5.0-lastwar-container', admin_gate: 'R4_R5_ONLY', lastwar_container: Boolean(env.LASTWAR_USER)", "version: '0.6.0-lastwar-external', admin_gate: 'R4_R5_ONLY', lastwar_external: Boolean(env.LASTWAR_BROKER_URL)");
fs.writeFileSync(indexPath, indexText, 'utf8');

console.log('[wfgg staging] canonical Worker staged with external Last War broker override');
