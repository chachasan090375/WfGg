import { routeLastWarConnector } from '../../worker/src/lastwar-connector.js';

const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8' };
const UID_RE = /^\d{8,24}$/;
const CODE_RE = /^\d{6}$/;
const BROKER_SENSITIVE_KEY = /(password|passcode|access.?token|refresh.?token|login.?key|authorization|cookie|session.?token|shumei|device.?id|fingerprint)/i;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      try {
        assertOriginAllowed(request, env);
        return cors(new Response(null, { status: 204 }), request, env);
      } catch (err) {
        return cors(json({ error: err?.message || 'FORBIDDEN' }, err?.status || 403), request, env);
      }
    }

    try {
      assertOriginAllowed(request, env);

      if (url.pathname === '/health' && request.method === 'GET') {
        return cors(json({
          ok: true,
          service: 'wfgg-lastwar-connector',
          version: '1.1.0-uid-first',
          mode: 'read-only',
          credential_storage: 'broker-encrypted-only',
          uid_first: true,
          broker_ready: Boolean(env.LASTWAR_BROKER_URL && env.LASTWAR_BROKER_SECRET)
        }), request, env);
      }

      const identityResponse = await routeUidFirstIdentity(request, env, url);
      if (identityResponse) return cors(identityResponse, request, env);

      const response = await routeLastWarConnector(request, env, {
        sessionContext,
        json,
        fail,
        audit,
        now,
        sha256Text,
        hmacHex,
        toBase64Url,
        id
      });

      return cors(response || json({ error: 'NOT_FOUND' }, 404), request, env);
    } catch (err) {
      console.error(err?.message || 'connector request failed');
      return cors(json({ error: err?.message || 'INTERNAL_ERROR' }, err?.status || 500), request, env);
    }
  }
};

async function routeUidFirstIdentity(request, env, url) {
  if (!url.pathname.startsWith('/api/lastwar/identity/')) return null;
  if (request.method !== 'POST') return json({ error: 'METHOD_NOT_ALLOWED' }, 405);

  const ctx = await sessionContext(request, env);
  const body = await safeJson(request);

  if (url.pathname === '/api/lastwar/identity/resolve') {
    const uid = normalizeUid(body.uid);
    if (!uid) fail('LASTWAR_UID_INVALID', 400);

    const broker = await brokerCall(env, '/v1/identity/resolve', {
      user_id: ctx.id,
      uid,
      locale: cleanLocale(ctx.language)
    });

    if (!broker) {
      await audit(env, ctx.id, 'LASTWAR_UID_RESOLVE_FALLBACK', 'lastwar_uid', uid, { next: 'email_required' });
      return json({
        ok: true,
        uid,
        contact_hint: null,
        player_name: null,
        server_id: null,
        next: 'email_required',
        source: 'uid-only'
      });
    }

    rejectSensitiveBrokerFields(broker);
    const contactHint = cleanContactHint(broker.contact_hint);
    const playerName = cleanText(broker.player_name, 80) || null;
    const serverId = cleanText(broker.server_id, 64) || null;
    const next = contactHint ? 'send_code' : 'email_required';

    await audit(env, ctx.id, 'LASTWAR_UID_RESOLVED', 'lastwar_uid', uid, {
      contact_hint_available: Boolean(contactHint),
      player_name: playerName,
      server_id: serverId,
      next
    });

    return json({
      ok: true,
      uid,
      contact_hint: contactHint,
      player_name: playerName,
      server_id: serverId,
      next,
      source: 'broker'
    });
  }

  if (url.pathname === '/api/lastwar/identity/send-code') {
    const uid = normalizeUid(body.uid);
    if (!uid) fail('LASTWAR_UID_INVALID', 400);
    const email = cleanEmail(body.email);

    const broker = await brokerCallRequired(env, '/v1/identity/send-code', {
      user_id: ctx.id,
      uid,
      email: email || undefined,
      locale: cleanLocale(ctx.language)
    });
    rejectSensitiveBrokerFields(broker);

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

    const broker = await brokerCallRequired(env, '/v1/identity/verify-code', {
      user_id: ctx.id,
      uid,
      code,
      auth_transaction: authTransaction,
      locale: cleanLocale(ctx.language)
    });
    rejectSensitiveBrokerFields(broker);

    const verifiedUid = normalizeUid(broker.uid || uid);
    if (!verifiedUid || verifiedUid !== uid) fail('BROKER_UID_MISMATCH', 502);

    await audit(env, ctx.id, 'LASTWAR_ACCOUNT_VERIFIED', 'lastwar_uid', uid, {
      role_count: clampInt(broker.role_count, 0, 100, 0),
      initial_sync_available: Boolean(broker.initial_sync_available)
    });

    return json({
      ok: true,
      verified: true,
      uid,
      player_name: cleanText(broker.player_name, 80) || null,
      server_id: cleanText(broker.server_id, 64) || null,
      role_count: clampInt(broker.role_count, 0, 100, 0),
      initial_sync_available: Boolean(broker.initial_sync_available)
    });
  }

  return json({ error: 'NOT_FOUND' }, 404);
}

async function brokerCallRequired(env, path, payload) {
  const result = await brokerCall(env, path, payload);
  if (!result) fail('LASTWAR_BROKER_NOT_CONFIGURED', 503);
  return result;
}

async function brokerCall(env, path, payload) {
  const base = String(env.LASTWAR_BROKER_URL || '').replace(/\/+$/, '');
  const secret = String(env.LASTWAR_BROKER_SECRET || '');
  if (!base || !secret) return null;

  const body = JSON.stringify(payload);
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const bodySha = await sha256Text(body);
  const signature = await hmacHex(secret, `${timestamp}\nPOST\n${path}\n${bodySha}`);

  let response;
  try {
    response = await fetch(base + path, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-WfGg-Timestamp': timestamp,
        'X-WfGg-Body-SHA256': bodySha,
        'X-WfGg-Signature': signature
      },
      body,
      redirect: 'error'
    });
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
      'LASTWAR_RATE_LIMITED'
    ]);
    const code = cleanText(data?.error, 80);
    fail(allowed.has(code) ? code : 'LASTWAR_BROKER_ERROR', response.status >= 400 && response.status < 500 ? response.status : 502);
  }
  return data && typeof data === 'object' && !Array.isArray(data) ? data : {};
}

function rejectSensitiveBrokerFields(value, path = 'broker') {
  if (!value || typeof value !== 'object') return;
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i += 1) rejectSensitiveBrokerFields(value[i], `${path}[${i}]`);
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    if (BROKER_SENSITIVE_KEY.test(key)) fail(`BROKER_SENSITIVE_FIELD_REJECTED:${path}.${key}`, 502);
    rejectSensitiveBrokerFields(child, `${path}.${key}`);
  }
}

function normalizeUid(value) {
  const uid = String(value || '').replace(/\D/g, '').slice(0, 24);
  return UID_RE.test(uid) ? uid : '';
}

function cleanContactHint(value) {
  const s = cleanText(value, 160);
  if (!s) return null;
  if (!s.includes('*') || !s.includes('@')) return null;
  return s;
}

function cleanEmail(value) {
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

async function safeJson(request) {
  try { return await request.json(); } catch (_) { fail('INVALID_JSON', 400); }
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

function fail(message, status = 400) {
  const error = new Error(message);
  error.status = status;
  throw error;
}

function now() {
  return new Date().toISOString();
}

function id(prefix) {
  return `${prefix}_${crypto.randomUUID()}`;
}

function allowedOrigins(env) {
  return String(env.CONNECTOR_ORIGINS || 'https://wfgg.pages.dev,https://simulator-standalone-v1.wfgg.pages.dev')
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean);
}

function assertOriginAllowed(request, env) {
  const origin = request.headers.get('Origin');
  if (!origin) return;
  if (!allowedOrigins(env).includes(origin)) fail('ORIGIN_NOT_ALLOWED', 403);
}

function cors(response, request, env) {
  const origin = request.headers.get('Origin');
  if (origin && allowedOrigins(env).includes(origin)) {
    response.headers.set('Access-Control-Allow-Origin', origin);
    response.headers.set('Vary', 'Origin');
  }
  response.headers.set('Access-Control-Allow-Headers', 'Authorization, Content-Type');
  response.headers.set('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  response.headers.set('Referrer-Policy', 'no-referrer');
  return response;
}

function toBase64Url(bytes) {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

async function sha256Text(value) {
  const bytes = new TextEncoder().encode(String(value));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function hmacHex(secret, value) {
  if (!secret) fail('SERVER_SECRET_MISSING', 500);
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(value));
  return [...new Uint8Array(signature)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function sessionContext(request, env) {
  const auth = request.headers.get('Authorization') || '';
  if (!auth.startsWith('Bearer ')) fail('UNAUTHORIZED', 401);
  const token = auth.slice(7).trim();
  if (!token) fail('UNAUTHORIZED', 401);

  const hash = await sha256Text(token);
  const row = await env.DB.prepare(`
    SELECT u.id,u.player_name,u.display_name,u.language,u.active,s.expires_at
    FROM sessions s
    JOIN users u ON u.id=s.user_id
    WHERE s.token_hash=? AND s.expires_at>? AND u.active=1
    LIMIT 1
  `).bind(hash, now()).first();
  if (!row) fail('UNAUTHORIZED', 401);
  return row;
}

async function audit(env, actor, action, targetType = null, targetId = null, details = null) {
  await env.DB.prepare(
    'INSERT INTO audit_log(actor_user_id,action,target_type,target_id,details_json,created_at) VALUES(?,?,?,?,?,?)'
  ).bind(
    actor || null,
    action,
    targetType,
    targetId,
    details ? JSON.stringify(details) : null,
    now()
  ).run();
}
