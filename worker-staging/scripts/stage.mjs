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

const identityPath = path.join(targetWorker, 'lastwar-identity.js');
let identityText = fs.readFileSync(identityPath, 'utf8');
identityText = identityText.replace(
  "      'LASTWAR_RATE_LIMITED'\n    ]);",
  "      'LASTWAR_RATE_LIMITED',\n      'LASTWAR_UPSTREAM_UNAVAILABLE',\n      'LASTWAR_ACCOUNT_DATA_MISSING',\n      'LASTWAR_RECONNECT_STATE_MISSING',\n      'BROKER_STATE_ENCRYPTION_FAILED'\n    ]);"
);
identityText = identityText.replace(
  'let stateTableReady = false;',
  'let stateTableReady = false;\nlet connectorTablesReady = false;'
);
identityText = identityText.replace(
  '    try {\n      await env.DB.prepare(`\n        INSERT INTO lastwar_devices(',
  '    try {\n      await ensureConnectorTables(env);\n      await env.DB.prepare(`\n        INSERT INTO lastwar_devices('
);
identityText = identityText.replace(
  'async function ensureStateTable(env) {',
  `async function ensureConnectorTables(env) {
  if (connectorTablesReady) return;

  await env.DB.prepare(\`
    CREATE TABLE IF NOT EXISTS lastwar_devices (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      refresh_token_hash TEXT NOT NULL UNIQUE,
      device_name TEXT NOT NULL,
      connector_version TEXT,
      source_uid TEXT,
      created_at TEXT NOT NULL,
      refresh_expires_at TEXT NOT NULL,
      last_seen_at TEXT,
      last_sync_at TEXT,
      revoked_at TEXT,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
  \`).run();

  const info = await env.DB.prepare('PRAGMA table_info(lastwar_devices)').all();
  const columns = new Set((info.results || []).map((row) => String(row.name)));
  const additions = [
    ['connector_version', 'TEXT'],
    ['source_uid', 'TEXT'],
    ['last_seen_at', 'TEXT'],
    ['last_sync_at', 'TEXT'],
    ['revoked_at', 'TEXT']
  ];
  for (const [name, type] of additions) {
    if (!columns.has(name)) await env.DB.prepare(\`ALTER TABLE lastwar_devices ADD COLUMN \${name} \${type}\`).run();
  }

  await env.DB.prepare(\`
    CREATE TABLE IF NOT EXISTS lastwar_snapshots (
      user_id TEXT PRIMARY KEY,
      device_id TEXT NOT NULL,
      schema_version TEXT NOT NULL,
      game_uid TEXT NOT NULL,
      server_id TEXT,
      player_name TEXT,
      source_collected_at TEXT,
      received_at TEXT NOT NULL,
      payload_sha256 TEXT NOT NULL,
      profile_json TEXT NOT NULL,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY (device_id) REFERENCES lastwar_devices(id) ON DELETE CASCADE
    )
  \`).run();

  await env.DB.prepare('CREATE INDEX IF NOT EXISTS idx_lastwar_devices_user ON lastwar_devices(user_id, revoked_at)').run();
  await env.DB.prepare('CREATE INDEX IF NOT EXISTS idx_lastwar_devices_refresh ON lastwar_devices(refresh_token_hash)').run();
  await env.DB.prepare('CREATE INDEX IF NOT EXISTS idx_lastwar_snapshots_received ON lastwar_snapshots(received_at DESC)').run();

  connectorTablesReady = true;
}

async function ensureStateTable(env) {`
);
fs.writeFileSync(identityPath, identityText, 'utf8');

const indexPath = path.join(targetWorker, 'index.js');
let indexText = fs.readFileSync(indexPath, 'utf8');
indexText = indexText.replace("export { LastWarUserContainer } from './lastwar-container.js';\n", '');
indexText = indexText.replace("version: '0.5.0-lastwar-container', admin_gate: 'R4_R5_ONLY', lastwar_container: Boolean(env.LASTWAR_USER)", "version: '0.6.1-lastwar-external-d1', admin_gate: 'R4_R5_ONLY', lastwar_external: Boolean(env.LASTWAR_BROKER_URL)");
fs.writeFileSync(indexPath, indexText, 'utf8');

console.log('[wfgg staging] canonical Worker staged with external Last War broker override + D1 self-heal');
