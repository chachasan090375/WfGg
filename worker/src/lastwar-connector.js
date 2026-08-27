const PAIR_TTL_MS = 10 * 60 * 1000;
const ACCESS_TTL_MS = 15 * 60 * 1000;
const REFRESH_TTL_MS = 90 * 24 * 60 * 60 * 1000;
const MAX_PROFILE_BYTES = 750_000;
const SNAPSHOT_SCHEMA = 'wfgg.lastwar.profile.v1';
const PAIR_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const ALLOWED_PROFILE_KEYS = new Set([
  'account',
  'heroes',
  'gear',
  'research',
  'drone',
  'squads',
  'wall',
  'exclusiveWeapons',
  'awakening',
  'decorations',
  'meta'
]);
const SENSITIVE_KEY = /(password|passcode|access.?token|refresh.?token|login.?key|email.?code|authorization|cookie|session|shumei|device.?id|fingerprint)/i;

export async function routeLastWarConnector(request, env, deps) {
  const url = new URL(request.url);
  const { sessionContext, json, fail, audit, now, sha256Text, hmacHex, toBase64Url, id } = deps;

  if (!url.pathname.startsWith('/api/lastwar/')) return null;

  if (url.pathname === '/api/lastwar/pair/start' && request.method === 'POST') {
    const ctx = await sessionContext(request, env);
    const code = makePairCode();
    const codeHash = await pairCodeHash(env, hmacHex, code);
    const pairingId = id('lwpair');
    const createdAt = now();
    const expiresAt = new Date(Date.now() + PAIR_TTL_MS).toISOString();

    await env.DB.batch([
      env.DB.prepare('DELETE FROM lastwar_pairings WHERE user_id=? AND used_at IS NULL').bind(ctx.id),
      env.DB.prepare(
        'INSERT INTO lastwar_pairings(id,user_id,code_hash,created_at,expires_at,used_at) VALUES(?,?,?,?,?,NULL)'
      ).bind(pairingId, ctx.id, codeHash, createdAt, expiresAt)
    ]);

    await audit(env, ctx.id, 'LASTWAR_PAIR_START', 'lastwar_pairing', pairingId, { expires_at: expiresAt });
    return json({ ok: true, pairing_code: formatPairCode(code), expires_at: expiresAt });
  }

  if (url.pathname === '/api/lastwar/pair/exchange' && request.method === 'POST') {
    const body = await safeJson(request, fail);
    const normalizedCode = normalizePairCode(body.pairing_code, fail);
    const codeHash = await pairCodeHash(env, hmacHex, normalizedCode);
    const ts = now();

    const pairing = await env.DB.prepare(
      'SELECT id,user_id,expires_at,used_at FROM lastwar_pairings WHERE code_hash=? LIMIT 1'
    ).bind(codeHash).first();

    if (!pairing || pairing.used_at || new Date(pairing.expires_at).getTime() <= Date.now()) {
      fail('PAIRING_CODE_INVALID_OR_EXPIRED', 401);
    }

    const deviceId = id('lwdev');
    const refreshToken = makeOpaqueToken('wfr1', deviceId, toBase64Url);
    const refreshHash = await sha256Text(refreshToken);
    const refreshExpiresAt = new Date(Date.now() + REFRESH_TTL_MS).toISOString();
    const deviceName = cleanText(body.device_name || 'WfGg Connector', 80);
    const connectorVersion = cleanText(body.connector_version || 'unknown', 40);

    await env.DB.batch([
      env.DB.prepare('UPDATE lastwar_pairings SET used_at=? WHERE id=? AND used_at IS NULL').bind(ts, pairing.id),
      env.DB.prepare(
        `INSERT INTO lastwar_devices(
          id,user_id,refresh_token_hash,device_name,connector_version,source_uid,
          created_at,refresh_expires_at,last_seen_at,last_sync_at,revoked_at
        ) VALUES(?,?,?,?,?,NULL,?,?,?,NULL,NULL)`
      ).bind(deviceId, pairing.user_id, refreshHash, deviceName, connectorVersion, ts, refreshExpiresAt, ts)
    ]);

    const accessToken = await signAccessToken(env, hmacHex, toBase64Url, {
      device_id: deviceId,
      user_id: pairing.user_id,
      scope: 'lastwar:sync'
    });

    await audit(env, pairing.user_id, 'LASTWAR_DEVICE_PAIRED', 'lastwar_device', deviceId, {
      device_name: deviceName,
      connector_version: connectorVersion
    });

    return json({
      ok: true,
      device_id: deviceId,
      refresh_token: refreshToken,
      refresh_expires_at: refreshExpiresAt,
      access_token: accessToken,
      access_expires_in: Math.floor(ACCESS_TTL_MS / 1000),
      scope: 'lastwar:sync'
    }, 201);
  }

  if (url.pathname === '/api/lastwar/token/refresh' && request.method === 'POST') {
    const refreshToken = authScheme(request, 'WfGgRefresh', fail);
    const refreshHash = await sha256Text(refreshToken);
    const device = await env.DB.prepare(
      `SELECT id,user_id,refresh_expires_at,revoked_at
       FROM lastwar_devices WHERE refresh_token_hash=? LIMIT 1`
    ).bind(refreshHash).first();

    if (!device || device.revoked_at || new Date(device.refresh_expires_at).getTime() <= Date.now()) {
      fail('REFRESH_TOKEN_INVALID_OR_EXPIRED', 401);
    }

    const ts = now();
    await env.DB.prepare('UPDATE lastwar_devices SET last_seen_at=? WHERE id=?').bind(ts, device.id).run();

    const accessToken = await signAccessToken(env, hmacHex, toBase64Url, {
      device_id: device.id,
      user_id: device.user_id,
      scope: 'lastwar:sync'
    });

    return json({
      ok: true,
      access_token: accessToken,
      access_expires_in: Math.floor(ACCESS_TTL_MS / 1000),
      scope: 'lastwar:sync'
    });
  }

  if (url.pathname === '/api/lastwar/sync' && request.method === 'POST') {
    const accessToken = authScheme(request, 'WfGgDevice', fail);
    const claims = await verifyAccessToken(env, hmacHex, accessToken, fail);
    if (claims.scope !== 'lastwar:sync') fail('TOKEN_SCOPE_INVALID', 403);

    const device = await env.DB.prepare(
      `SELECT id,user_id,source_uid,revoked_at,refresh_expires_at
       FROM lastwar_devices WHERE id=? AND user_id=? LIMIT 1`
    ).bind(claims.device_id, claims.user_id).first();

    if (!device || device.revoked_at || new Date(device.refresh_expires_at).getTime() <= Date.now()) {
      fail('DEVICE_REVOKED_OR_EXPIRED', 401);
    }

    const contentLength = Number(request.headers.get('Content-Length') || 0);
    if (contentLength > MAX_PROFILE_BYTES) fail('SNAPSHOT_TOO_LARGE', 413);

    const body = await safeJson(request, fail);
    if (body.schema_version !== SNAPSHOT_SCHEMA) fail('SNAPSHOT_SCHEMA_UNSUPPORTED', 400);
    if (!body.profile || typeof body.profile !== 'object' || Array.isArray(body.profile)) fail('PROFILE_REQUIRED', 400);

    validateProfileShape(body.profile, fail);
    const profileJson = JSON.stringify(body.profile);
    if (new TextEncoder().encode(profileJson).byteLength > MAX_PROFILE_BYTES) fail('SNAPSHOT_TOO_LARGE', 413);

    const uid = cleanText(body.profile?.account?.uid, 128);
    if (!uid) fail('PROFILE_UID_REQUIRED', 400);
    if (device.source_uid && device.source_uid !== uid) fail('DEVICE_UID_CHANGED_REPAIR_REQUIRED', 409);

    const serverId = cleanText(body.profile?.account?.serverId ?? body.profile?.account?.server_id, 64) || null;
    const playerName = cleanText(body.profile?.account?.playerName ?? body.profile?.account?.player_name, 80) || null;
    const collectedAt = cleanIso(body.collected_at) || null;
    const receivedAt = now();
    const payloadSha = await sha256Text(profileJson);

    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO lastwar_snapshots(
          user_id,device_id,schema_version,game_uid,server_id,player_name,
          source_collected_at,received_at,payload_sha256,profile_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
          device_id=excluded.device_id,
          schema_version=excluded.schema_version,
          game_uid=excluded.game_uid,
          server_id=excluded.server_id,
          player_name=excluded.player_name,
          source_collected_at=excluded.source_collected_at,
          received_at=excluded.received_at,
          payload_sha256=excluded.payload_sha256,
          profile_json=excluded.profile_json`
      ).bind(device.user_id, device.id, SNAPSHOT_SCHEMA, uid, serverId, playerName, collectedAt, receivedAt, payloadSha, profileJson),
      env.DB.prepare(
        `UPDATE lastwar_devices
         SET source_uid=COALESCE(source_uid,?),last_seen_at=?,last_sync_at=?
         WHERE id=?`
      ).bind(uid, receivedAt, receivedAt, device.id)
    ]);

    await audit(env, device.user_id, 'LASTWAR_PROFILE_SYNC', 'lastwar_device', device.id, {
      uid,
      server_id: serverId,
      payload_sha256: payloadSha,
      schema_version: SNAPSHOT_SCHEMA
    });

    return json({ ok: true, received_at: receivedAt, payload_sha256: payloadSha });
  }

  if (url.pathname === '/api/lastwar/status' && request.method === 'GET') {
    const ctx = await sessionContext(request, env);
    const devices = await env.DB.prepare(
      `SELECT COUNT(*) AS n, MAX(last_sync_at) AS last_sync_at
       FROM lastwar_devices WHERE user_id=? AND revoked_at IS NULL`
    ).bind(ctx.id).first();
    const snapshot = await env.DB.prepare(
      `SELECT game_uid,server_id,player_name,source_collected_at,received_at,payload_sha256
       FROM lastwar_snapshots WHERE user_id=? LIMIT 1`
    ).bind(ctx.id).first();

    return json({
      ok: true,
      connected: Number(devices?.n || 0) > 0,
      active_devices: Number(devices?.n || 0),
      last_sync_at: devices?.last_sync_at || null,
      snapshot: snapshot || null
    });
  }

  if (url.pathname === '/api/lastwar/profile' && request.method === 'GET') {
    const ctx = await sessionContext(request, env);
    const row = await env.DB.prepare(
      `SELECT schema_version,game_uid,server_id,player_name,source_collected_at,received_at,payload_sha256,profile_json
       FROM lastwar_snapshots WHERE user_id=? LIMIT 1`
    ).bind(ctx.id).first();
    if (!row) fail('LASTWAR_PROFILE_NOT_SYNCED', 404);

    return json({
      ok: true,
      schema_version: row.schema_version,
      game_uid: row.game_uid,
      server_id: row.server_id,
      player_name: row.player_name,
      collected_at: row.source_collected_at,
      received_at: row.received_at,
      payload_sha256: row.payload_sha256,
      profile: JSON.parse(row.profile_json)
    });
  }

  if (url.pathname === '/api/lastwar/devices' && request.method === 'GET') {
    const ctx = await sessionContext(request, env);
    const result = await env.DB.prepare(
      `SELECT id,device_name,connector_version,source_uid,created_at,refresh_expires_at,last_seen_at,last_sync_at,revoked_at
       FROM lastwar_devices WHERE user_id=? ORDER BY created_at DESC`
    ).bind(ctx.id).all();
    return json({ ok: true, devices: result.results || [] });
  }

  const deviceMatch = url.pathname.match(/^\/api\/lastwar\/devices\/([^/]+)$/);
  if (deviceMatch && request.method === 'DELETE') {
    const ctx = await sessionContext(request, env);
    const deviceId = decodeURIComponent(deviceMatch[1]);
    const ts = now();
    const result = await env.DB.prepare(
      'UPDATE lastwar_devices SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL'
    ).bind(ts, deviceId, ctx.id).run();
    if (!result.meta?.changes) fail('LASTWAR_DEVICE_NOT_FOUND', 404);
    await audit(env, ctx.id, 'LASTWAR_DEVICE_REVOKED', 'lastwar_device', deviceId);
    return json({ ok: true, revoked_at: ts });
  }

  fail('NOT_FOUND', 404);
}

function cleanText(value, max) {
  if (value === null || value === undefined) return '';
  return String(value).trim().slice(0, max);
}

function cleanIso(value) {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

async function safeJson(request, fail) {
  try {
    return await request.json();
  } catch (_) {
    fail('INVALID_JSON', 400);
  }
}

function authScheme(request, scheme, fail) {
  const raw = request.headers.get('Authorization') || '';
  const prefix = `${scheme} `;
  if (!raw.startsWith(prefix)) fail('UNAUTHORIZED', 401);
  const token = raw.slice(prefix.length).trim();
  if (!token) fail('UNAUTHORIZED', 401);
  return token;
}

function makePairCode() {
  const bytes = new Uint8Array(10);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => PAIR_ALPHABET[b % PAIR_ALPHABET.length]).join('');
}

function formatPairCode(code) {
  return `${code.slice(0, 4)}-${code.slice(4, 7)}-${code.slice(7)}`;
}

function normalizePairCode(value, fail) {
  const code = String(value || '').toUpperCase().replace(/[^A-Z2-9]/g, '');
  if (code.length !== 10) fail('PAIRING_CODE_INVALID', 400);
  for (const c of code) if (!PAIR_ALPHABET.includes(c)) fail('PAIRING_CODE_INVALID', 400);
  return code;
}

async function pairCodeHash(env, hmacHex, code) {
  return hmacHex(env.APP_SECRET, `wfgg-lastwar-pair:v1:${code}`);
}

function makeOpaqueToken(prefix, deviceId, toBase64Url) {
  const random = new Uint8Array(32);
  crypto.getRandomValues(random);
  return `${prefix}.${deviceId}.${toBase64Url(random)}`;
}

async function signAccessToken(env, hmacHex, toBase64Url, claims) {
  const issuedAt = Math.floor(Date.now() / 1000);
  const payload = {
    v: 1,
    did: claims.device_id,
    uid: claims.user_id,
    scp: claims.scope,
    iat: issuedAt,
    exp: issuedAt + Math.floor(ACCESS_TTL_MS / 1000)
  };
  const encoded = toBase64Url(new TextEncoder().encode(JSON.stringify(payload)));
  const sig = await hmacHex(env.APP_SECRET, `wfgg-lastwar-access:v1:${encoded}`);
  return `wfa1.${encoded}.${sig}`;
}

async function verifyAccessToken(env, hmacHex, token, fail) {
  const parts = String(token || '').split('.');
  if (parts.length !== 3 || parts[0] !== 'wfa1') fail('ACCESS_TOKEN_INVALID', 401);
  const [, encoded, suppliedSig] = parts;
  const expectedSig = await hmacHex(env.APP_SECRET, `wfgg-lastwar-access:v1:${encoded}`);
  if (!constantTimeEqual(expectedSig, suppliedSig)) fail('ACCESS_TOKEN_INVALID', 401);

  let payload;
  try {
    const padded = encoded.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(encoded.length / 4) * 4, '=');
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    payload = JSON.parse(new TextDecoder().decode(bytes));
  } catch (_) {
    fail('ACCESS_TOKEN_INVALID', 401);
  }

  const nowSec = Math.floor(Date.now() / 1000);
  if (payload?.v !== 1 || !payload.did || !payload.uid || !payload.scp || Number(payload.exp || 0) <= nowSec) {
    fail('ACCESS_TOKEN_EXPIRED_OR_INVALID', 401);
  }

  return { device_id: payload.did, user_id: payload.uid, scope: payload.scp, expires_at: payload.exp };
}

function constantTimeEqual(a, b) {
  const left = String(a || '');
  const right = String(b || '');
  if (left.length !== right.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i += 1) diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
  return diff === 0;
}

function validateProfileShape(profile, fail) {
  for (const key of Object.keys(profile)) {
    if (!ALLOWED_PROFILE_KEYS.has(key)) fail(`PROFILE_SECTION_NOT_ALLOWED:${key}`, 400);
  }
  scanSensitiveKeys(profile, fail, 'profile');

  if (profile.heroes !== undefined && !Array.isArray(profile.heroes)) fail('PROFILE_HEROES_MUST_BE_ARRAY', 400);
  if (Array.isArray(profile.heroes) && profile.heroes.length > 100) fail('PROFILE_HEROES_TOO_MANY', 400);
  if (profile.gear !== undefined && !Array.isArray(profile.gear)) fail('PROFILE_GEAR_MUST_BE_ARRAY', 400);
  if (Array.isArray(profile.gear) && profile.gear.length > 500) fail('PROFILE_GEAR_TOO_MANY', 400);
}

function scanSensitiveKeys(value, fail, path) {
  if (!value || typeof value !== 'object') return;
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i += 1) scanSensitiveKeys(value[i], fail, `${path}[${i}]`);
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    if (SENSITIVE_KEY.test(key)) fail(`SENSITIVE_FIELD_REJECTED:${path}.${key}`, 400);
    scanSensitiveKeys(child, fail, `${path}.${key}`);
  }
}

export const __test = {
  SNAPSHOT_SCHEMA,
  normalizePairCode,
  formatPairCode,
  signAccessToken,
  verifyAccessToken,
  validateProfileShape
};
