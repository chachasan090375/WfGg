import { GameConnector, normalizedIdentity } from './connector.js';
import { RemoteLastWarTransport } from './remote-transport.js';

/**
 * Last War connector boundary.
 * No endpoint, account, token, fingerprint or replay material is embedded in source.
 * A transport must be injected by the server environment.
 */
export class LastWarAdapter extends GameConnector {
  constructor({ transport = null, logger = console } = {}) {
    super();
    this.transport = transport;
    this.logger = logger;
    this.identity = null;
    this.connected = false;
    this.sessionToken = null;
  }

  async authenticate(token) {
    if (!token) throw Object.assign(new Error('GAME_TOKEN_REQUIRED'), { status: 400 });
    if (!this.transport?.authenticate) throw Object.assign(new Error('LASTWAR_LIVE_CONNECTOR_NOT_CONFIGURED'), { status: 503 });
    const result = await this.transport.authenticate(token);
    this.identity = normalizedIdentity(result?.identity || result);
    this.sessionToken = String(token);
    this.connected = true;
    return { identity: { ...this.identity }, sessionMeta: result?.sessionMeta || null };
  }

  async getCurrentIdentity() {
    if (!this.connected || !this.identity) throw new Error('GAME_SESSION_REQUIRED');
    return { ...this.identity };
  }

  async getRawStateSnapshot() {
    if (!this.connected || !this.sessionToken || !this.transport?.snapshot) throw new Error('GAME_SESSION_REQUIRED');
    const result = await this.transport.snapshot(this.sessionToken);
    return result?.snapshot || result;
  }

  async scanPlayer(query) {
    if (!this.connected || !this.transport?.scanPlayer) throw new Error('GAME_SESSION_REQUIRED');
    return this.transport.scanPlayer(query, this.sessionToken);
  }

  async close() {
    try { await this.transport?.close?.(); } finally { this.connected = false; this.identity = null; this.sessionToken = null; }
  }
}

export function connectorFromEnv(env, logger = console) {
  const transport = env?.RADAR_CONNECTOR_URL && env?.RADAR_CONNECTOR_SHARED_KEY
    ? new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY })
    : null;
  return new LastWarAdapter({ transport, logger });
}
