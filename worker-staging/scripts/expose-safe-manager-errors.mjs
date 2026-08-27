import fs from 'node:fs';
import path from 'node:path';

const identityPath = path.resolve(process.cwd(), 'src', 'lastwar-identity.js');
let text = fs.readFileSync(identityPath, 'utf8');

const marker = "      'LASTWAR_UPSTREAM_UNAVAILABLE',";
const code = "      'LASTWAR_BROKER_UNAVAILABLE',";

if (!text.includes(code)) {
  if (!text.includes(marker)) {
    throw new Error('staging broker diagnostic allow-list marker not found');
  }
  text = text.replace(marker, `${marker}\n${code}`);
  fs.writeFileSync(identityPath, text, 'utf8');
}

if (!fs.readFileSync(identityPath, 'utf8').includes(code)) {
  throw new Error('LASTWAR_BROKER_UNAVAILABLE diagnostic was not staged');
}

console.log('[wfgg staging] safe manager transport diagnostic enabled');
