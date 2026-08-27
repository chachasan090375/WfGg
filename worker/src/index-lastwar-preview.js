// WFGG_LASTWAR_PREVIEW_ENTRY_V2
// Preview-only sidecar. No binding to the production D1 database.
// It validates the WfGg bearer token by calling the stable /api/me endpoint,
// then writes Last War claims only to env.LAB_DB.

import {
  lastWarProviderCapability,
  listExternalIdentities,
  claimLastWarIdentity,
  revokeLastWarIdentity
} from './lastwar-identities.js';

const JSON_HEADERS = {
  'content-type': 'application/json; charset=utf-8',
  'cache-control': 'no-store',
  'x-content-type-options': 'nosniff'
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
  return String(env.PORTAL_ORIGINS || '')
    .split(',')
    .map((value) => value.trim())
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
  return response;
}

async function previewSessionContext(request, env) {
  const auth = request.headers.get('Authorization') || '';
  if (!auth.startsWith('Bearer ')) fail('UNAUTHORIZED', 401);

  const authApi = String(env.AUTH_API_BASE || 'https://wfgg-api.chachasan090375.workers.dev').replace(/\/$/, '');
  const response = await fetch(`${authApi}/api/me`, {
    method: 'GET',
    headers: { Authorization: auth },
    cache: 'no-store'
  });

  let data = null;
  try { data = await response.json(); } catch (_) {}
  if (response.status === 401) fail('UNAUTHORIZED', 401);
  if (!response.ok) fail(data?.error || `AUTH_API_${response.status}`, 502);
  if (!data?.user?.id) fail('AUTH_CONTEXT_INVALID', 502);

  return { id: data.user.id };
}

async function audit(env, actor, action, targetType = null, targetId = null, details = null) {
  await env.LAB_DB.prepare(
    'INSERT INTO lab_audit_log(actor_wfgg_user_id,action,target_type,target_id,details_json,created_at) VALUES(?,?,?,?,?,?)'
  ).bind(
    actor || null,
    action,
    targetType,
    targetId,
    details ? JSON.stringify(details) : null,
    now()
  ).run();
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      try {
        assertOriginAllowed(request, env);
        return cors(new Response(null, { status: 204 }), request, env);
      } catch (error) {
        return cors(json({ error: error?.message || 'FORBIDDEN' }, error?.status || 403), request, env);
      }
    }

    try {
      assertOriginAllowed(request, env);
      const url = new URL(request.url);
      let response;

      if (url.pathname === '/api/health' && request.method === 'GET') {
        response = json({
          ok: true,
          service: 'wfgg-api-lastwar-preview',
          storage: 'LAB_DB_ONLY',
          production_db_binding: false
        });
      } else if (url.pathname === '/api/auth/providers' && request.method === 'GET') {
        response = json({ providers: [lastWarProviderCapability()] });
      } else if (url.pathname === '/api/me/identities' && request.method === 'GET') {
        response = json(await listExternalIdentities(request, env, previewSessionContext));
      } else if (url.pathname === '/api/me/identities/lastwar/claim' && request.method === 'POST') {
        response = json(
          await claimLastWarIdentity(request, env, previewSessionContext, audit, now, id),
          201
        );
      } else {
        const revoke = url.pathname.match(/^\/api\/me\/identities\/lastwar\/([^/]+)$/);
        if (revoke && request.method === 'DELETE') {
          response = json(
            await revokeLastWarIdentity(
              request,
              env,
              previewSessionContext,
              audit,
              now,
              decodeURIComponent(revoke[1])
            )
          );
        } else {
          response = json({ error: 'NOT_FOUND' }, 404);
        }
      }

      return cors(response, request, env);
    } catch (error) {
      console.error('WFGG_LASTWAR_PREVIEW', error?.message || error);
      return cors(
        json({ error: String(error?.message || 'INTERNAL_ERROR') }, Number(error?.status || 500)),
        request,
        env
      );
    }
  }
};
