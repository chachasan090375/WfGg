import { getContainer } from '@cloudflare/containers';

const UID_RE = /^\d{8,24}$/;
const CODE_RE = /^\d{6}$/;
const BROKER_SENSITIVE_KEY = /(password|passcode|access.?token|refresh.?token|login.?key|authorization|cookie|session.?token|shumei|device.?id|fingerprint)/i;
const BROKER_REVISION = 'ee5f64de160a8051c2f9f98189b75038dd225a0a';

export async function routeLastWarIdentity(request, env, url, deps) {
  if (!url.pathname.startsWith('/api/lastwar/identity/')) return null;

  const { sessionContext, json, fail, audit, now, sha256Text } = deps;
  if (request.method !== 'POST') return json({ error: 'METHOD_NOT_ALLOWED' }, 405);

  const ctx = await sessionContext(request, env);
  const body = await safeJson(request, fail);

  if (url.pathname === '/api/lastwar/identity/resolve') {
    const uid = normalizeUid(body.uid);
    if (!uid) fail('LASTWAR_UID_INVALID', 400);

    const broker = await containerCall(env, ctx.id, '/v1/identity/resolve', {
      user_id: ctx.id,
      uid,
      locale: cleanLocale(ctx.language)
    }, sha256Text, fail);

    rejectSensitiveBrokerFields(broker, fail);
    const contactHint = cleanContactHint(broker.contact_hint);
    const playerName = cleanText(broker.player_name, 80) || null;
    const serverId = cleanText(broker.server_id, 64) || null;
    const next = contactHint ? 'send_code' : 'email_required';

    await audit(env, ctx.id, 'LASTWAR_UID_RESOLVED', 'lastwar_uid', uid, {
      contact_hint_available: Boolean(contactHint),
      player_name: playerName,
      server_id: serverId,
      already_linked: Boolean(broker.already_linked),
      next
    });

    return json({
      ok: true,
      uid,
      contact_hint: contactHint,
      player_name: playerName,
      server_id: serverId,
      already_linked: Boolean(broker.already_linked),
      next,
      source: 'wfgg-container'
    });
  }

  if (url.pathname === '/api/lastwar/identity/send-code') {
    const uid = normalizeUid(body.uid);
    const email = cleanEmail(body.email, fail);
    if (!uid) fail('LASTWAR_UID_INVALID', 400);
    if (!email) fail('LASTWAR_EMAIL_REQUIRED', 400);

    const broker = await containerCall(env, ctx.id, '/v1/identity/send-code', {
      user_id: ctx.id,
      uid,
      email,
      locale: cleanLocale(ctx.language)
    }, sha256Text, fail);

    rejectSensitiveBrokerFields(broker, fail);
    const authTransaction = cleanOpaque(broker.auth_transaction, 160);
    if (!authTransaction) fail('BROKER_AUTH_TRANSACTION_MISSING', 502);
    const contactHint = cleanContactHint(broker.contact_hint);

    await audit(env, ctx.id, 'LASTWAR_EMAIL_CODE_SENT', 'lastwar_uid', uid, {
      contact_hint_available: Boolean(contactHint)
    });

    return json({
      ok: true,
      uid,
      auth_transaction: authTransaction,
      contact_hint: contactHint,
      expires_in: clampInt(broker.expires_in, 60, 900, 300)
    });
  }

  if (url.pathname === '/api/lastwar/identity/verify-code') {
    const uid = normalizeUid(body.uid);
    const code = String(body.code || '').replace(/\D/g, '');
    const authTransaction = cleanOpaque(body.auth_transaction, 160);
    if (!uid) fail('LASTWAR_UID_INVALID', 400);
    if (!CODE_RE.test(code)) fail('LASTWAR_VERIFY_CODE_INVALID', 400);
    if (!authTransaction) fail('LASTWAR_AUTH_TRANSACTION_REQUIRED', 400);

    const broker = await containerCall(env, ctx.id, '/v1/identity/verify-code', {
      user_id: ctx.id,
      uid,
      code,
      auth_transaction: authTransaction,
      locale: cleanLocale(ctx.language)
    }, sha256Text, fail);

    rejectSensitiveBrokerFields(broker, fail);
    const verifiedUid = normalizeUid(broker.uid || uid);
    if (!verifiedUid || verifiedUid !== uid) fail('BROKER_UID_MISMATCH', 502);

    const playerName = cleanText(broker.player_name, 80) || null;
    const serverId = cleanText(broker.server_id, 64) || null;
    const ts = now();
    const cloudDeviceId = `lwcloud_${(await sha256Text(ctx.id)).slice(0, 24)}`;
    const cloudLinkHash = await sha256Text(`wfgg-cloud-link:v1:${ctx.id}:${uid}`);

    try {
      await env.DB.prepare(`
        INSERT INTO lastwar_devices(
          id,user_id,refresh_token_hash,device_name,connector_version,source_uid,
          created_at,refresh_expires_at,last_seen_at,last_sync_at,revoked_at
        ) VALUES(?,?,?,?,?,?,?,?,?,NULL,NULL)
        ON CONFLICT(id) DO UPDATE SET
          refresh_token_hash=excluded.refresh_token_hash,
          device_name=excluded.device_name,
          connector_version=excluded.connector_version,
          source_uid=excluded.source_uid,
          refresh_expires_at=excluded.refresh_expires_at,
          last_seen_at=excluded.last_seen_at,
          revoked_at=NULL
      `).bind(
        cloudDeviceId,
        ctx.id,
        cloudLinkHash,
        'WfGg Cloud Last War',
        `broker-${BROKER_REVISION.slice(0, 8)}`,
        uid,
        ts,
        '9999-12-31T23:59:59.000Z',
        ts
      ).run();
    } catch (err) {
      console.error('lastwar cloud link persistence failed', err?.message || err);
      fail('LASTWAR_LINK_PERSISTENCE_FAILED', 500);
    }

    await audit(env, ctx.id, 'LASTWAR_ACCOUNT_VERIFIED', 'lastwar_uid', uid, {
      role_count: clampInt(broker.role_count, 0, 100, 0),
      initial_sync_available: Boolean(broker.initial_sync_available),
      cloud_device_id: cloudDeviceId
    });

    return json({
      ok: true,
      verified: true,
      uid,
      player_name: playerName,
      server_id: serverId,
      role_count: clampInt(broker.role_count, 0, 100, 0),
      initial_sync_available: Boolean(broker.initial_sync_available)
    });
  }

  return json({ error: 'NOT_FOUND' }, 404);
}

export async function routeLastWarCloudSync(request, env, url, deps) {
  if (url.pathname !== '/api/lastwar/cloud-sync') return null;
  const { sessionContext, json, fail, audit, now, sha256Text } = deps;
  if (request.method !== 'POST') return json({ error: 'METHOD_NOT_ALLOWED' }, 405);

  const ctx = await sessionContext(request, env);
  const broker = await containerCall(env, ctx.id, '/v1/profile/sync', {
    user_id: ctx.id,
    locale: cleanLocale(ctx.language)
  }, sha256Text, fail);

  rejectSensitiveBrokerFields(broker, fail);
  const uid = normalizeUid(broker.uid);
  if (!uid || !broker.session_valid) fail('LASTWAR_SYNC_SESSION_INVALID', 502);
  const ts = now();

  await env.DB.prepare(
    `UPDATE lastwar_devices SET last_seen_at=?,last_sync_at=?
     WHERE user_id=? AND source_uid=? AND revoked_at IS NULL`
  ).bind(ts, ts, ctx.id, uid).run();

  await audit(env, ctx.id, 'LASTWAR_CLOUD_SESSION_SYNC', 'lastwar_uid', uid, {
    profile_sync_version: cleanText(broker.profile_sync_version, 80) || null
  });

  return json({
    ok: true,
    uid,
    session_valid: true,
    synced_at: ts,
    profile_sync_version: cleanText(broker.profile_sync_version, 80) || null
  });
}

async function containerCall(env, userId, path, payload, sha256Text, fail) {
  if (!env.LASTWAR_USER) fail('LASTWAR_BROKER_NOT_CONFIGURED', 503);
  const instanceKey = `u-${(await sha256Text(userId)).slice(0, 48)}`;
  const instance = getContainer(env.LASTWAR_USER, instanceKey);
  let response;
  try {
    response = await instance.fetch(new Request(`https://container.internal${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }));
  } catch (_) {
    fail('LASTWAR_BROKER_UNAVAILABLE', 503);
  }

  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (!response.ok) {
    const allowed = new Set([
      'LASTWAR_UID_NOT_FOUND',
      'LASTWAR_EMAIL_REQUIRED',
      'LASTWAR_EMAIL_MISMATCH',
      'LASTWAR_VERIFY_CODE_INVALID',
      'LASTWAR_VERIFY_CODE_EXPIRED',
      'LASTWAR_VERIFY_CODE_ALREADY_SUBMITTED',
      'LASTWAR_UID_LINK_NOT_CONFIRMED',
      'LASTWAR_UPSTREAM_TIMEOUT',
      'LASTWAR_RECONNECT_STATE_REQUIRED',
      'LASTWAR_RECONNECT_STATE_INVALID',
      'LASTWAR_RATE_LIMITED'
    ]);
    const code = cleanText(data?.error, 100);
    const status = response.status >= 400 && response.status < 500 ? response.status : 502;
    fail(allowed.has(code) ? code : 'LASTWAR_BROKER_ERROR', status);
  }
  return data && typeof data === 'object' && !Array.isArray(data) ? data : {};
}

function rejectSensitiveBrokerFields(value, fail, path = 'broker') {
  if (!value || typeof value !== 'object') return;
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i += 1) rejectSensitiveBrokerFields(value[i], fail, `${path}[${i}]`);
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    if (BROKER_SENSITIVE_KEY.test(key)) fail(`BROKER_SENSITIVE_FIELD_REJECTED:${path}.${key}`, 502);
    rejectSensitiveBrokerFields(child, fail, `${path}.${key}`);
  }
}

function normalizeUid(value) {
  const uid = String(value || '').replace(/\D/g, '').slice(0, 24);
  return UID_RE.test(uid) ? uid : '';
}

function cleanContactHint(value) {
  const s = cleanText(value, 160);
  if (!s || !s.includes('*') || !s.includes('@')) return null;
  return s;
}

function cleanEmail(value, fail) {
  const s = cleanText(value, 254).toLowerCase();
  if (!s) return '';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s)) fail('LASTWAR_EMAIL_INVALID', 400);
  return s;
}

function cleanOpaque(value, max) {
  const s = cleanText(value, max);
  if (!s || !/^[A-Za-z0-9._:-]+$/.test(s)) return '';
  return s;
}

function cleanLocale(value) {
  const s = cleanText(value, 8).toLowerCase();
  return ['fr', 'it', 'en', 'es'].includes(s) ? s : 'en';
}

function clampInt(value, min, max, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(n)));
}

function cleanText(value, max) {
  if (value === null || value === undefined) return '';
  return String(value).trim().slice(0, max);
}

async function safeJson(request, fail) {
  try { return await request.json(); } catch (_) { fail('INVALID_JSON', 400); }
}
