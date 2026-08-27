import { Container, getContainer } from '@cloudflare/containers';
import { env } from 'cloudflare:workers';

const ALLOWED_PATHS = new Set([
  '/v1/identity/resolve',
  '/v1/identity/send-code',
  '/v1/identity/verify-code',
  '/v1/profile/sync'
]);
const MAX_BODY_BYTES = 32_768;
const MAX_CLOCK_SKEW_SECONDS = 90;

export class LastWarUserContainer extends Container {
  defaultPort = 8080;
  sleepAfter = '12m';
  enableInternet = true;
  envVars = {
    WFGG_STATE_KEY: env.LASTWAR_STATE_KEY || '',
    WFGG_UPSTREAM_REVISION: env.BROKER_REVISION || ''
  };

  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === '/ping') return this.containerFetch(request);

    const sealedState = await this.ctx.storage.get('sealed_state');
    const headers = new Headers(request.headers);
    headers.set('X-WfGg-Container-Auth', '1');
    if (sealedState) headers.set('X-WfGg-Sealed-State', String(sealedState));

    const proxied = new Request(request.url, {
      method: request.method,
      headers,
      body: request.method === 'GET' || request.method === 'HEAD' ? undefined : await request.arrayBuffer()
    });
    const response = await this.containerFetch(proxied);

    const contentType = response.headers.get('Content-Type') || '';
    if (!contentType.includes('application/json')) return response;

    let data;
    try {
      data = await response.clone().json();
    } catch (_) {
      return response;
    }

    if (data && typeof data === 'object' && !Array.isArray(data)) {
      if (typeof data._wfgg_sealed_state === 'string' && data._wfgg_sealed_state.length <= 16_384) {
        await this.ctx.storage.put('sealed_state', data._wfgg_sealed_state);
      }
      for (const key of Object.keys(data)) {
        if (key.startsWith('_wfgg_')) delete data[key];
      }
    }

    const outHeaders = new Headers(response.headers);
    outHeaders.set('Content-Type', 'application/json; charset=utf-8');
    outHeaders.set('Cache-Control', 'no-store');
    return new Response(JSON.stringify(data), { status: response.status, headers: outHeaders });
  }
}

export default {
  async fetch(request, runtimeEnv) {
    try {
      const url = new URL(request.url);
      if (url.pathname === '/health' && request.method === 'GET') {
        return json({
          ok: true,
          service: 'wfgg-lastwar-broker',
          mode: 'read-only',
          revision: runtimeEnv.BROKER_REVISION || null,
          per_user_isolation: true
        });
      }

      if (request.method !== 'POST' || !ALLOWED_PATHS.has(url.pathname)) {
        return json({ error: 'NOT_FOUND' }, 404);
      }

      const rawBody = await boundedBody(request);
      await verifyConnectorSignature(request, runtimeEnv, url.pathname, rawBody);

      let body;
      try { body = JSON.parse(rawBody); } catch (_) { return json({ error: 'INVALID_JSON' }, 400); }
      const userId = cleanUserId(body?.user_id);
      if (!userId) return json({ error: 'INVALID_USER_ID' }, 400);

      const instanceKey = `u-${(await sha256Text(userId)).slice(0, 48)}`;
      const instance = getContainer(runtimeEnv.LASTWAR_USER, instanceKey);

      const headers = new Headers();
      headers.set('Content-Type', 'application/json');
      headers.set('X-WfGg-Container-Auth', '1');
      const forwarded = new Request(`https://container.internal${url.pathname}`, {
        method: 'POST',
        headers,
        body: rawBody
      });
      const response = await instance.fetch(forwarded);
      const outHeaders = new Headers(response.headers);
      outHeaders.set('Cache-Control', 'no-store');
      outHeaders.set('X-Content-Type-Options', 'nosniff');
      return new Response(response.body, { status: response.status, headers: outHeaders });
    } catch (err) {
      console.error(err?.message || 'broker request failed');
      return json({ error: err?.safeCode || 'BROKER_INTERNAL_ERROR' }, err?.status || 500);
    }
  }
};

async function boundedBody(request) {
  const declared = Number(request.headers.get('Content-Length') || 0);
  if (declared > MAX_BODY_BYTES) throw safeError('BODY_TOO_LARGE', 413);
  const text = await request.text();
  if (new TextEncoder().encode(text).byteLength > MAX_BODY_BYTES) throw safeError('BODY_TOO_LARGE', 413);
  return text;
}

async function verifyConnectorSignature(request, runtimeEnv, path, rawBody) {
  const secret = String(runtimeEnv.BROKER_SHARED_SECRET || '');
  if (!secret) throw safeError('BROKER_SECRET_MISSING', 500);

  const timestamp = String(request.headers.get('X-WfGg-Timestamp') || '');
  const suppliedBodySha = String(request.headers.get('X-WfGg-Body-SHA256') || '').toLowerCase();
  const suppliedSig = String(request.headers.get('X-WfGg-Signature') || '').toLowerCase();
  const ts = Number(timestamp);
  const now = Math.floor(Date.now() / 1000);
  if (!Number.isFinite(ts) || Math.abs(now - ts) > MAX_CLOCK_SKEW_SECONDS) throw safeError('BROKER_SIGNATURE_EXPIRED', 401);

  const actualBodySha = await sha256Text(rawBody);
  if (!constantTimeEqual(actualBodySha, suppliedBodySha)) throw safeError('BROKER_BODY_HASH_INVALID', 401);

  const expected = await hmacHex(secret, `${timestamp}\nPOST\n${path}\n${actualBodySha}`);
  if (!constantTimeEqual(expected, suppliedSig)) throw safeError('BROKER_SIGNATURE_INVALID', 401);
}

function cleanUserId(value) {
  const s = String(value || '').trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(s)) return '';
  return s;
}

function safeError(code, status) {
  const err = new Error(code);
  err.safeCode = code;
  err.status = status;
  return err;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff'
    }
  });
}

async function sha256Text(value) {
  const bytes = new TextEncoder().encode(String(value));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function hmacHex(secret, value) {
  const key = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(value));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

function constantTimeEqual(a, b) {
  const x = String(a || '');
  const y = String(b || '');
  if (x.length !== y.length) return false;
  let diff = 0;
  for (let i = 0; i < x.length; i += 1) diff |= x.charCodeAt(i) ^ y.charCodeAt(i);
  return diff === 0;
}
