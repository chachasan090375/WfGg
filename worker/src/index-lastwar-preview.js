// WFGG_LASTWAR_PREVIEW_ENTRY_V1
// Preview-only sidecar. It adds external-identity routes and delegates every
// existing route to the stable WfGg API implementation.

import baseWorker from './index.js';
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

async function sha256Text(value) {
  const bytes = new TextEncoder().encode(String(value));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

async function previewSessionContext(request, env) {
  const auth = request.headers.get('Authorization') || '';
  if (!auth.startsWith('Bearer ')) fail('UNAUTHORIZED', 401);
  const token = auth.slice(7).trim();
  if (!token) fail('UNAUTHORIZED', 401);
  const hash = await sha256Text(token);

  const row = await env.DB.prepare(`
    SELECT u.id
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

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    try {
      if (url.pathname === '/api/auth/providers' && request.method === 'GET') {
        return json({ providers: [lastWarProviderCapability()] });
      }

      if (url.pathname === '/api/me/identities' && request.method === 'GET') {
        return json(await listExternalIdentities(request, env, previewSessionContext));
      }

      if (url.pathname === '/api/me/identities/lastwar/claim' && request.method === 'POST') {
        return json(
          await claimLastWarIdentity(
            request,
            env,
            previewSessionContext,
            audit,
            now,
            id
          ),
          201
        );
      }

      const revoke = url.pathname.match(/^\/api\/me\/identities\/lastwar\/([^/]+)$/);
      if (revoke && request.method === 'DELETE') {
        return json(
          await revokeLastWarIdentity(
            request,
            env,
            previewSessionContext,
            audit,
            now,
            decodeURIComponent(revoke[1])
          )
        );
      }

      return baseWorker.fetch(request, env, ctx);
    } catch (error) {
      console.error('WFGG_LASTWAR_PREVIEW', error);
      return json({ error: String(error?.message || 'INTERNAL_ERROR') }, Number(error?.status || 500));
    }
  }
};
