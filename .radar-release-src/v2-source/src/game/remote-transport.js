const enc = new TextEncoder();

function hex(bytes) {
  return [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
}

async function sha256Hex(value) {
  return hex(new Uint8Array(await crypto.subtle.digest('SHA-256', enc.encode(value))));
}

async function hmacHex(secret, value) {
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return hex(new Uint8Array(await crypto.subtle.sign('HMAC', key, enc.encode(value))));
}

function nonce() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return hex(bytes);
}

export async function connectorSignature({ method, path, timestamp, nonce: requestNonce, body = '', secret }) {
  const bodyHash = await sha256Hex(body);
  const canonical = `${String(method).toUpperCase()}\n${path}\n${timestamp}\n${requestNonce}\n${bodyHash}`;
  return hmacHex(secret, canonical);
}

export class RemoteLastWarTransport {
  constructor({ baseUrl, sharedKey, timeoutMs = 65000, fetchImpl = (...args) => globalThis.fetch(...args) } = {}) {
    if (!baseUrl) throw new Error('RADAR_CONNECTOR_URL_REQUIRED');
    if (!sharedKey || String(sharedKey).length < 32) throw new Error('RADAR_CONNECTOR_SHARED_KEY_MISSING_OR_WEAK');
    this.baseUrl = String(baseUrl).replace(/\/+$/, '');
    this.sharedKey = String(sharedKey);
    this.timeoutMs = timeoutMs;
    this.fetchImpl = fetchImpl;
  }

  async request(path, { method = 'POST', body = null } = {}) {
    const bodyText = body === null ? '' : JSON.stringify(body);
    const timestamp = String(Math.floor(Date.now() / 1000));
    const requestNonce = nonce();
    // The connector deliberately signs URL.Path only. Query parameters remain in
    // the request URL but are not part of the HMAC canonical path.
    const parsed = new URL(this.baseUrl + path);
    const signature = await connectorSignature({ method, path: parsed.pathname, timestamp, nonce: requestNonce, body: bodyText, secret: this.sharedKey });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort('timeout'), this.timeoutMs);
    try {
      const response = await this.fetchImpl(parsed.toString(), {
        method,
        headers: {
          'content-type': 'application/json',
          'x-radar-timestamp': timestamp,
          'x-radar-nonce': requestNonce,
          'x-radar-signature': signature
        },
        body: bodyText || undefined,
        signal: controller.signal,
        cache: 'no-store'
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const error = new Error(data.error || `CONNECTOR_HTTP_${response.status}`);
        error.status = response.status === 401 || response.status === 403 ? 503 : response.status;
        throw error;
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }

  authenticate(token) { return this.request('/v1/authenticate', { body: { token } }); }
  snapshot(token) { return this.request('/v1/snapshot', { body: { token } }); }
  scanPlayer(query, token) { return this.request('/v1/scan/player', { body: { token, query } }); }
  startCollectorSearch(query, token) { return this.request('/v1/collector/search/start', { body: { token, query } }); }
  collectorSearchStatus(id) { return this.request(`/v1/collector/search/status?id=${encodeURIComponent(id)}`, { method: 'GET' }); }
  health() { return this.request('/v1/health', { method: 'GET' }); }
  async close() {}
}
