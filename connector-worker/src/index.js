import { routeLastWarConnector } from '../../worker/src/lastwar-connector.js';

const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8' };

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
          version: '1.0.0-readonly',
          mode: 'read-only',
          credential_storage: 'local-only'
        }), request, env);
      }

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
      console.error(err);
      return cors(json({ error: err?.message || 'INTERNAL_ERROR' }, err?.status || 500), request, env);
    }
  }
};

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
