import { ROLES, assertCapability } from './auth/roles.js';
import { createSession, verifySession, sessionCookie, clearSessionCookie, requireSecret } from './auth/session.js';
import { encryptGameToken, decryptGameToken } from './auth/token-vault.js';
import { normalizeIdentity, validateRole } from './admin/rights.js';
import { bindIdentityToGrant, ensureBootstrapOwnerGrant, getCredential, listGrants, listUsers, saveCredential, saveObservedSnapshot, saveRadarIdentityObservation, saveRadarPlayerObservations, upsertGrant, audit } from './db/repository.js';
import { connectorFromEnv } from './game/lastwar-adapter.js';
import { RemoteLastWarTransport } from './game/remote-transport.js';
import { searchRadar } from './radar/service.js';
import { RadarSentinel, defaultSentinelChecks } from './agents/sentinel.js';
import { RadarGuardian } from './agents/guardian.js';
import { RadarAgentOrchestrator } from './agents/orchestrator.js';
import { RadarOracleAgent } from './agents/oracle-agent.js';
import { approveAction, getAgentOverview, getRuntimeConfig, publishEvent, reportClientRuntime } from './agents/bus.js';
import { AGENTS, EVENT_TYPES } from './agents/protocol.js';

const APP_VERSION = '0.5.0';
const SCHEMA_VERSION = 'radar-schema-v0.2';

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', ...headers } });
}

function cookieValue(request, name) {
  const cookie = request.headers.get('cookie') || '';
  const match = cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]+)`));
  return match ? decodeURIComponent(match[1]) : '';
}

function assertSameOriginMutation(request) {
  if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method)) return;
  const origin = request.headers.get('origin');
  if (!origin) return;
  if (new URL(request.url).origin !== origin) throw Object.assign(new Error('CROSS_ORIGIN_MUTATION_DENIED'), { status: 403 });
}

async function bodyJson(request) {
  if (!(request.headers.get('content-type') || '').toLowerCase().includes('application/json')) {
    throw Object.assign(new Error('JSON_REQUIRED'), { status: 415 });
  }
  try { return await request.json(); } catch { throw Object.assign(new Error('INVALID_JSON'), { status: 400 }); }
}

async function currentSession(request, env) {
  const token = cookieValue(request, 'radar_session');
  return verifySession(token, env.RADAR_SESSION_KEY);
}

async function requireSession(request, env) {
  const session = await currentSession(request, env);
  if (!session) throw Object.assign(new Error('RADAR_SESSION_REQUIRED'), { status: 401 });
  return session;
}

async function authenticateGameToken(request, env) {
  assertSameOriginMutation(request);
  const { token } = await bodyJson(request);
  if (!token || String(token).length < 8) throw Object.assign(new Error('GAME_TOKEN_REQUIRED'), { status: 400 });
  const connector = connectorFromEnv(env, { info() {}, warn() {}, error() {} });
  try {
    const auth = await connector.authenticate(String(token));
    const identity = normalizeIdentity(auth.identity);
    await ensureBootstrapOwnerGrant(env, identity);
    const user = await bindIdentityToGrant(env, identity);
    const vaultKey = requireSecret(env.RADAR_TOKEN_VAULT_KEY, 'RADAR_TOKEN_VAULT_KEY');
    const encrypted = await encryptGameToken(String(token), vaultKey, identity.gameUid);
    await saveCredential(env, identity.gameUid, encrypted);
    await audit(env, identity.gameUid, 'auth.game-token.success', identity.gameUid, { serverId: identity.serverId, connector: 'lastwar' });
    const sessionKey = requireSecret(env.RADAR_SESSION_KEY, 'RADAR_SESSION_KEY');
    const ttl = Math.max(900, Math.min(Number(env.RADAR_SESSION_TTL || 3600), 43200));
    const session = await createSession({ gameUid: identity.gameUid, pseudo: identity.pseudo, serverId: identity.serverId, role: user.role }, sessionKey, ttl);
    return json({ ok: true, user: { gameUid: identity.gameUid, pseudo: identity.pseudo, serverId: identity.serverId, role: user.role } }, 200, { 'set-cookie': sessionCookie(session, ttl) });
  } finally {
    await connector.close().catch(() => {});
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    try {
      if (url.pathname.startsWith('/api/')) assertSameOriginMutation(request);

      if (url.pathname === '/api/health') {
        const holds = env?.DB ? await getRuntimeConfig(env, 'deployment_holds', {}) : {};
        const cacheEpoch = env?.DB ? await getRuntimeConfig(env, 'cache_epoch', null) : null;
        return json({
          ok: true,
          app: 'wfgg-radar',
          version: APP_VERSION,
          schemaVersion: SCHEMA_VERSION,
          mode: 'standalone',
          gameConnector: env.RADAR_CONNECTOR_URL && String(env.RADAR_CONNECTOR_SHARED_KEY || '').length >= 32 ? 'configured' : 'not-configured',
          agents: { oracle: 'v0.5', sentinel: 'v0.5', guardian: 'v0.5', orchestrator: 'v0.5' },
          automation: { enabled: Boolean(env?.DB), deploymentHold: Object.keys(holds || {}).length > 0, holdReasons: Object.keys(holds || {}), cacheEpoch }
        });
      }

      if (url.pathname === '/api/auth/logout' && request.method === 'POST') {
        const session = await currentSession(request, env);
        if (session) await audit(env, session.gameUid, 'auth.logout', session.gameUid);
        return json({ ok: true }, 200, { 'set-cookie': clearSessionCookie() });
      }

      if (url.pathname === '/api/auth/game-token' && request.method === 'POST') return await authenticateGameToken(request, env);

      if (url.pathname === '/api/me' && request.method === 'GET') {
        const session = await requireSession(request, env);
        return json({ user: { gameUid: session.gameUid, pseudo: session.pseudo, serverId: session.serverId || null, role: session.role } });
      }

      if (url.pathname === '/api/admin/users' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'admin.users');
        return json({ users: await listUsers(env), grants: await listGrants(env) });
      }

      if (url.pathname === '/api/admin/grants' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'admin.grants');
        const body = await bodyJson(request);
        const role = validateRole(body.role || ROLES.USER);
        const grant = await upsertGrant(env, { pseudo: body.pseudo, role, active: body.active !== false, actorUid: session.gameUid });
        return json({ grant });
      }

      if (url.pathname === '/api/radar/search' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const query = String(url.searchParams.get('q') || '').trim();
        const limit = url.searchParams.get('limit') || 50;
        const cached = await searchRadar(env, query, { limit });
        if (!query || cached.results.length > 0 || session.role !== ROLES.OWNER) return json(cached);

        // Experimental V0.6 live fallback: OWNER-only until the native READONLY
        // player-search template is validated in production. Search failures never
        // destroy the cached Radar result; they are reported as sanitized metadata.
        const record = await getCredential(env, session.gameUid);
        if (!record) return json({ ...cached, liveScan: { attempted: false, status: 'credential-missing' } });
        const vaultKey = requireSecret(env.RADAR_TOKEN_VAULT_KEY, 'RADAR_TOKEN_VAULT_KEY');
        const token = await decryptGameToken({ ciphertext: record.ciphertext, iv: record.iv, keyVersion: record.key_version }, vaultKey, session.gameUid);
        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY });
        try {
          const result = await transport.scanPlayer(query, token);
          const players = Array.isArray(result?.players) ? result.players : [];
          const stored = await saveRadarPlayerObservations(env, players, { sourceCommand: 'native-template-player-scan-v2' });
          await audit(env, session.gameUid, 'radar.live-player-scan', query, { observedPlayers: players.length, inserted: stored.inserted });
          const refreshed = await searchRadar(env, query, { limit });
          return json({ ...refreshed, liveScan: { attempted: true, status: 'ok', observedPlayers: players.length, inserted: stored.inserted } });
        } catch (error) {
          const code = String(error?.message || 'LASTWAR_PLAYER_SCAN_FAILED');
          return json({ ...cached, liveScan: { attempted: true, status: 'unavailable', error: code } });
        } finally {
          await transport.close().catch(() => {});
        }
      }

      if (url.pathname === '/api/oracle/status' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'oracle.simulate');
        return json({ engine: 'oracle-v0.2-provenance', arithmetic: 'BigInt rational', provenance: 'OBSERVED/INFERRED/PROVEN', status: 'ready-for-live-evidence', exactRules: 0 });
      }


      if (url.pathname === '/api/oracle/capture-live' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'oracle.raw');
        const record = await getCredential(env, session.gameUid);
        if (!record) throw Object.assign(new Error('GAME_CREDENTIAL_NOT_FOUND'), { status: 409 });
        const vaultKey = requireSecret(env.RADAR_TOKEN_VAULT_KEY, 'RADAR_TOKEN_VAULT_KEY');
        const token = await decryptGameToken({ ciphertext: record.ciphertext, iv: record.iv, keyVersion: record.key_version }, vaultKey, session.gameUid);
        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY });
        try {
          const result = await transport.snapshot(token);
          const snapshot = result?.snapshot || result;
          if (snapshot?.readonly !== true) throw Object.assign(new Error('LIVE_SNAPSHOT_NOT_READONLY'), { status: 502 });
          const stored = await saveObservedSnapshot(env, session.gameUid, snapshot);
          const indexedIdentity = await saveRadarIdentityObservation(env, {
            identity: snapshot.identity || null,
            session: snapshot.session || null,
            batchId: stored.batchId,
            observedAt: stored.observedAt
          });
          await audit(env, session.gameUid, 'oracle.live-snapshot.capture', session.gameUid, { batchId: stored.batchId, observations: stored.observationCount, indexedIdentity: Boolean(indexedIdentity), source: snapshot.source || null });
          const event = await publishEvent(env, {
            type: EVENT_TYPES.GAME_SNAPSHOT_OBSERVED,
            source: 'radar-runtime',
            target: AGENTS.ORACLE,
            severity: 'info',
            payload: { batchId: stored.batchId, observationCount: stored.observationCount, source: snapshot.source || null, observerUid: session.gameUid }
          });
          if (ctx?.waitUntil) {
            const orchestrator = new RadarAgentOrchestrator({ appVersion: APP_VERSION });
            ctx.waitUntil(orchestrator.cycle(env, { activeVersion: APP_VERSION }).catch(() => {}));
          }
          return json({ ok: true, batch: stored, identity: snapshot.identity || null, session: snapshot.session || null, readonly: true, agentEventId: event.id });
        } finally {
          await transport.close().catch(() => {});
        }
      }

      if (url.pathname === '/api/sentinel/run' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'sentinel.full');
        const sentinel = new RadarSentinel();
        for (const check of defaultSentinelChecks()) sentinel.addCheck(check);
        const report = await sentinel.runAndPublish({ env, session, expectedVersion: APP_VERSION, activeVersion: APP_VERSION });
        const orchestrator = new RadarAgentOrchestrator({ appVersion: APP_VERSION });
        const cycle = await orchestrator.cycle(env, { activeVersion: APP_VERSION });
        return json({ report, automation: { processed: cycle.processed, actionsExecuted: cycle.actionsExecuted } });
      }

      if (url.pathname === '/api/guardian/plan' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'guardian.repair');
        const body = await bodyJson(request);
        const guardian = new RadarGuardian({ expectedVersion: APP_VERSION });
        return json({ manifest: guardian.validateManifest(body.manifest || {}), cleanup: guardian.planRuntimeCleanup(body.cleanup || { activeVersion: APP_VERSION }) });
      }

      if (url.pathname === '/api/agents/client-runtime' && request.method === 'POST') {
        const session = await requireSession(request, env);
        const body = await bodyJson(request);
        const version = String(body.version || '').trim();
        if (!/^\d+\.\d+\.\d+$/.test(version)) throw Object.assign(new Error('CLIENT_VERSION_INVALID'), { status: 400 });
        await reportClientRuntime(env, session.gameUid, version, body.cacheEpoch || null);
        return json({ ok: true, expectedVersion: APP_VERSION });
      }

      if (url.pathname === '/api/agents/status' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'guardian.repair');
        return json(await getAgentOverview(env));
      }

      if (url.pathname === '/api/agents/cycle' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'guardian.repair');
        const orchestrator = new RadarAgentOrchestrator({ appVersion: APP_VERSION });
        await orchestrator.bootstrap(env);
        return json(await orchestrator.cycle(env, { activeVersion: APP_VERSION, actorUid: session.gameUid }));
      }

      const approveMatch = url.pathname.match(/^\/api\/agents\/actions\/(\d+)\/approve$/);
      if (approveMatch && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'guardian.repair');
        const action = await approveAction(env, Number(approveMatch[1]), session.gameUid);
        await audit(env, session.gameUid, 'agents.action.approve', String(action.id), { actionType: action.action_type });
        const orchestrator = new RadarAgentOrchestrator({ appVersion: APP_VERSION });
        const cycle = await orchestrator.cycle(env, { activeVersion: APP_VERSION, actorUid: session.gameUid });
        return json({ ok: true, actionId: action.id, cycle: { processed: cycle.processed, actionsExecuted: cycle.actionsExecuted } });
      }

      if (url.pathname === '/api/oracle/compare' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'oracle.rules.write');
        const body = await bodyJson(request);
        if (!body.ruleKey || body.computed === undefined || body.expected === undefined) throw Object.assign(new Error('ORACLE_COMPARISON_REQUIRED'), { status: 400 });
        const exact = JSON.stringify(body.computed) === JSON.stringify(body.expected);
        const oracleAgent = new RadarOracleAgent();
        await oracleAgent.publishComparison(env, { ruleKey: String(body.ruleKey), exact, computed: body.computed, expected: body.expected, buildId: body.buildId || null, seasonId: body.seasonId || null });
        const orchestrator = new RadarAgentOrchestrator({ appVersion: APP_VERSION });
        const cycle = await orchestrator.cycle(env, { activeVersion: APP_VERSION, actorUid: session.gameUid });
        return json({ exact, automation: { processed: cycle.processed, actionsExecuted: cycle.actionsExecuted } });
      }

      return json({ error: 'NOT_FOUND' }, 404);
    } catch (error) {
      return json({ error: error.code || error.message || 'INTERNAL_ERROR' }, error.status || 500);
    }
  },

  async scheduled(_event, env, ctx) {
    const run = async () => {
      const orchestrator = new RadarAgentOrchestrator({ appVersion: APP_VERSION });
      await orchestrator.bootstrap(env);
      return orchestrator.cycle(env, { activeVersion: APP_VERSION });
    };
    if (ctx?.waitUntil) ctx.waitUntil(run().catch((error) => console.error('RADAR_AGENT_CYCLE_FAILED', error?.message || error)));
    else await run();
  }
};
