#!/usr/bin/env node

import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const VERSION = '1.0.0-readonly';
const SCHEMA = 'wfgg.lastwar.profile.v1';
const DEFAULT_API = process.env.WFGG_CONNECTOR_API || 'https://wfgg-lastwar-connector.workers.dev';
const HOME = path.join(os.homedir(), '.wfgg-lastwar');
const CONFIG_PATH = path.join(HOME, 'connector.json');
const SENSITIVE_KEY = /(password|passcode|access.?token|refresh.?token|login.?key|email.?code|authorization|cookie|session|shumei|device.?id|fingerprint)/i;
const ALLOWED_PROFILE_KEYS = new Set([
  'account','heroes','gear','research','drone','squads','wall','exclusiveWeapons','awakening','decorations','meta'
]);

const [command, ...args] = process.argv.slice(2);

try {
  switch (command) {
    case 'pair':
      await pair(args);
      break;
    case 'sync-file':
      await syncFile(args);
      break;
    case 'doctor':
      await doctor(args);
      break;
    case 'status':
      await status();
      break;
    case 'forget':
      await forget();
      break;
    case 'help':
    case '--help':
    case '-h':
    case undefined:
      help();
      break;
    default:
      throw new Error(`Unknown command: ${command}`);
  }
} catch (error) {
  console.error(`ERROR: ${error.message}`);
  process.exitCode = 1;
}

function help() {
  console.log(`WfGg Last War Connector ${VERSION}\n\nCommands:\n  pair <PAIRING_CODE> [--api URL] [--name DEVICE]\n  sync-file <SNAPSHOT.json>\n  doctor [--api URL]\n  status\n  forget\n\nSecurity model:\n  - WfGg credentials: pairing code -> refresh token -> 15-minute access tokens.\n  - Last War credentials are NOT accepted by this CLI and are never uploaded.\n  - Live Last War collection will plug into the read-only provider layer in a later increment.\n`);
}

function option(args, name, fallback = null) {
  const i = args.indexOf(name);
  if (i < 0 || i + 1 >= args.length) return fallback;
  return args[i + 1];
}

async function pair(args) {
  const pairingCode = String(args[0] || '').trim();
  if (!pairingCode) throw new Error('pair requires a pairing code');
  const api = stripSlash(option(args, '--api', DEFAULT_API));
  const deviceName = option(args, '--name', `${os.hostname()} / ${process.platform}-${process.arch}`);

  const result = await requestJson(`${api}/api/lastwar/pair/exchange`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      pairing_code: pairingCode,
      device_name: deviceName,
      connector_version: VERSION
    })
  });

  await saveConfig({
    api,
    device_id: result.device_id,
    refresh_token: result.refresh_token,
    refresh_expires_at: result.refresh_expires_at,
    device_name: deviceName,
    connector_version: VERSION,
    paired_at: new Date().toISOString()
  });

  console.log(`PAIRED device=${result.device_id}`);
  console.log(`REFRESH_EXPIRES=${result.refresh_expires_at}`);
}

async function syncFile(args) {
  const file = args[0];
  if (!file) throw new Error('sync-file requires a JSON snapshot path');
  const cfg = await loadConfig();
  const raw = JSON.parse(await fs.readFile(file, 'utf8'));
  const envelope = normalizeEnvelope(raw);
  validateEnvelope(envelope);

  const access = await refreshAccess(cfg);
  const result = await requestJson(`${cfg.api}/api/lastwar/sync`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `WfGgDevice ${access.access_token}`
    },
    body: JSON.stringify(envelope)
  });

  console.log(`SYNC_OK received=${result.received_at}`);
  console.log(`SHA256=${result.payload_sha256}`);
}

async function doctor(args) {
  let api = option(args, '--api', null);
  if (!api) {
    try { api = (await loadConfig()).api; } catch (_) { api = DEFAULT_API; }
  }
  api = stripSlash(api);
  const result = await requestJson(`${api}/health`);
  console.log(JSON.stringify(result, null, 2));
}

async function status() {
  const cfg = await loadConfig();
  let tokenStatus = 'unknown';
  try {
    const access = await refreshAccess(cfg);
    tokenStatus = access?.access_token ? 'valid' : 'invalid';
  } catch (error) {
    tokenStatus = `invalid: ${error.message}`;
  }
  console.log(JSON.stringify({
    paired: true,
    api: cfg.api,
    device_id: cfg.device_id,
    device_name: cfg.device_name,
    refresh_expires_at: cfg.refresh_expires_at,
    token_status: tokenStatus
  }, null, 2));
}

async function forget() {
  try {
    await fs.unlink(CONFIG_PATH);
    console.log('LOCAL_PAIRING_REMOVED');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    console.log('LOCAL_PAIRING_ALREADY_EMPTY');
  }
}

async function refreshAccess(cfg) {
  return requestJson(`${cfg.api}/api/lastwar/token/refresh`, {
    method: 'POST',
    headers: { 'Authorization': `WfGgRefresh ${cfg.refresh_token}` }
  });
}

function normalizeEnvelope(raw) {
  if (raw?.schema_version && raw?.profile) return raw;
  return {
    schema_version: SCHEMA,
    collected_at: new Date().toISOString(),
    profile: raw
  };
}

function validateEnvelope(envelope) {
  if (envelope.schema_version !== SCHEMA) throw new Error(`unsupported schema ${envelope.schema_version}`);
  if (!envelope.profile || typeof envelope.profile !== 'object' || Array.isArray(envelope.profile)) {
    throw new Error('profile must be an object');
  }
  for (const key of Object.keys(envelope.profile)) {
    if (!ALLOWED_PROFILE_KEYS.has(key)) throw new Error(`profile section not allowed: ${key}`);
  }
  scanSensitive(envelope.profile, 'profile');
  const uid = String(envelope.profile?.account?.uid || '').trim();
  if (!uid) throw new Error('profile.account.uid is required');
}

function scanSensitive(value, trail) {
  if (!value || typeof value !== 'object') return;
  if (Array.isArray(value)) {
    value.forEach((item, i) => scanSensitive(item, `${trail}[${i}]`));
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    if (SENSITIVE_KEY.test(key)) throw new Error(`sensitive field rejected: ${trail}.${key}`);
    scanSensitive(child, `${trail}.${key}`);
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { error: text || `HTTP_${response.status}` }; }
  if (!response.ok) throw new Error(`${response.status} ${data.error || response.statusText}`);
  return data;
}

async function saveConfig(config) {
  await fs.mkdir(HOME, { recursive: true, mode: 0o700 });
  const tmp = `${CONFIG_PATH}.tmp`;
  await fs.writeFile(tmp, `${JSON.stringify(config, null, 2)}\n`, { mode: 0o600 });
  await fs.rename(tmp, CONFIG_PATH);
  await fs.chmod(CONFIG_PATH, 0o600).catch(() => {});
}

async function loadConfig() {
  let raw;
  try { raw = await fs.readFile(CONFIG_PATH, 'utf8'); }
  catch (error) {
    if (error.code === 'ENOENT') throw new Error('connector is not paired; run pair first');
    throw error;
  }
  const cfg = JSON.parse(raw);
  if (!cfg.api || !cfg.device_id || !cfg.refresh_token) throw new Error('local connector config is incomplete');
  cfg.api = stripSlash(cfg.api);
  return cfg;
}

function stripSlash(value) {
  return String(value || '').replace(/\/+$/, '');
}
