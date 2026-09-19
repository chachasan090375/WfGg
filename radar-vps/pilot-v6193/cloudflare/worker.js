import { ROLES, assertCapability } from './auth/roles.js';
import { createSession, verifySession, sessionCookie, clearSessionCookie, requireSecret } from './auth/session.js';
import { encryptGameToken, decryptGameToken } from './auth/token-vault.js';
import { normalizeIdentity, validateRole } from './admin/rights.js';
import { bindIdentityToGrant, ensureBootstrapOwnerGrant, getCredential, listGrants, listUsers, saveCredential, saveObservedSnapshot, upsertGrant, audit, saveRadarPlayerObservations } from './db/repository.js';
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

      if (url.pathname === '/api/auth/game-token' && request.method === 'POST') return authenticateGameToken(request, env);

      if (url.pathname === '/api/auth/lastwar/start' && request.method === 'POST') {
        const body = await bodyJson(request);
        const gameUid = String(body.gameUid || '').trim();
        const email = String(body.email || '').trim();
        if (!/^\d{6,64}$/.test(gameUid)) throw Object.assign(new Error('LASTWAR_GAME_UID_REQUIRED'), { status: 400 });
        if (!email || email.length > 320 || !email.includes('@')) throw Object.assign(new Error('LASTWAR_EMAIL_INVALID'), { status: 400 });
        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY, timeoutMs: 40000 });
        try {
          const started = await transport.startEmailAuth(gameUid, email);
          const challengeId = String(started?.challengeId || '').trim();
          if (!challengeId) throw Object.assign(new Error('LASTWAR_EMAIL_CHALLENGE_INVALID'), { status: 502 });
          return json({ ok: true, challengeId, expiresIn: Number(started?.expiresIn || 600) }, 202);
        } finally {
          await transport.close().catch(() => {});
        }
      }

      if (url.pathname === '/api/auth/lastwar/finish' && request.method === 'POST') {
        const body = await bodyJson(request);
        const challengeId = String(body.challengeId || '').trim();
        const code = String(body.code || '').trim();
        if (!/^[A-Za-z0-9_-]{8,128}$/.test(challengeId)) throw Object.assign(new Error('LASTWAR_EMAIL_CHALLENGE_REQUIRED'), { status: 400 });
        if (!/^\d{6}$/.test(code)) throw Object.assign(new Error('LASTWAR_EMAIL_CODE_INVALID'), { status: 400 });
        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY, timeoutMs: 70000 });
        try {
          const completed = await transport.finishEmailAuth(challengeId, code);
          const credential = String(completed?.auth?.credential || '');
          const rawIdentity = completed?.auth?.identity || null;
          if (credential.length < 8 || !rawIdentity?.gameUid) throw Object.assign(new Error('LASTWAR_EMAIL_AUTH_RESULT_INVALID'), { status: 502 });
          if (!rawIdentity?.pseudo || !rawIdentity?.serverId) throw Object.assign(new Error('LASTWAR_IDENTITY_NOT_IN_COLLECTOR'), { status: 409 });
          const identity = normalizeIdentity(rawIdentity);
          await ensureBootstrapOwnerGrant(env, identity);
          const user = await bindIdentityToGrant(env, identity);
          const vaultKey = requireSecret(env.RADAR_TOKEN_VAULT_KEY, 'RADAR_TOKEN_VAULT_KEY');
          const encrypted = await encryptGameToken(credential, vaultKey, identity.gameUid);
          await saveCredential(env, identity.gameUid, encrypted);
          await audit(env, identity.gameUid, 'auth.lastwar-email.success', identity.gameUid, { serverId: identity.serverId, connector: 'lastwar-email-code' });
          const sessionKey = requireSecret(env.RADAR_SESSION_KEY, 'RADAR_SESSION_KEY');
          const ttl = Math.max(900, Math.min(Number(env.RADAR_SESSION_TTL || 3600), 43200));
          const session = await createSession({ gameUid: identity.gameUid, pseudo: identity.pseudo, serverId: identity.serverId, role: user.role }, sessionKey, ttl);
          return json({ ok: true, user: { gameUid: identity.gameUid, pseudo: identity.pseudo, serverId: identity.serverId, role: user.role } }, 200, { 'set-cookie': sessionCookie(session, ttl) });
        } finally {
          await transport.close().catch(() => {});
        }
      }

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

      // WFGG_RADAR_RICH_PROFILE_WORKER_V6191
      if (url.pathname === '/api/radar/profile/rich' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const gameUid = String(url.searchParams.get('uid') || '').trim();
        if (!/^\d{6,64}$/.test(gameUid)) throw Object.assign(new Error('PROFILE_UID_REQUIRED'), { status: 400 });
        const row = await env.DB.prepare(
          'SELECT subject_uid AS gameUid, army_power AS armyPower, army_kill AS armyKill, svip_level AS svipLevel, country, avatar_ref AS avatarRef, observed_at AS observedAt, source_command AS sourceCommand FROM radar_profile_rich WHERE subject_uid = ? LIMIT 1'
        ).bind(gameUid).first();
        return json({ ok: true, readonly: true, profile: row || null });
      }

      // WFGG_RADAR_SEED_SCOUT_WORKER_V6193
      if (url.pathname === '/api/radar/seed-scout/start' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const body = await bodyJson(request);
        const limit = body.limit == null ? 8 : Number(body.limit);
        const region = body.region == null ? 4 : Number(body.region);
        const minTargetPlayers = body.minTargetPlayers == null ? 20 : Number(body.minTargetPlayers);
        const offset = body.offset == null ? 0 : Number(body.offset);
        if (!Number.isInteger(limit) || limit < 1 || limit > 20) throw Object.assign(new Error('SEED_SCOUT_LIMIT_INVALID'), { status: 400 });
        if (!Number.isInteger(region) || region < 0 || region > 8) throw Object.assign(new Error('SEED_SCOUT_REGION_INVALID'), { status: 400 });
        if (!Number.isInteger(minTargetPlayers) || minTargetPlayers < 1 || minTargetPlayers > 500) throw Object.assign(new Error('SEED_SCOUT_MIN_PLAYERS_INVALID'), { status: 400 });
        if (!Number.isInteger(offset) || offset < 0 || offset > 500) throw Object.assign(new Error('SEED_SCOUT_OFFSET_INVALID'), { status: 400 });

        const record = await getCredential(env, session.gameUid);
        if (!record) throw Object.assign(new Error('GAME_CREDENTIAL_NOT_FOUND'), { status: 409 });
        const vaultKey = requireSecret(env.RADAR_TOKEN_VAULT_KEY, 'RADAR_TOKEN_VAULT_KEY');
        const token = await decryptGameToken(
          { ciphertext: record.ciphertext, iv: record.iv, keyVersion: record.key_version },
          vaultKey,
          session.gameUid
        );
        const transport = new RemoteLastWarTransport({
          baseUrl: env.RADAR_CONNECTOR_URL,
          sharedKey: env.RADAR_CONNECTOR_SHARED_KEY,
          timeoutMs: 30000
        });
        try {
          const started = await transport.startSeedScout(token, { limit, region, minTargetPlayers, offset });
          const job = started?.job || null;
          if (!job?.id) throw Object.assign(new Error('SEED_SCOUT_JOB_START_INVALID'), { status: 502 });
          return json({ ok: true, readonly: true, collectorMutation: false, job }, 202);
        } finally {
          await transport.close().catch(() => {});
        }
      }

      if (url.pathname === '/api/radar/seed-scout/status' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const id = String(url.searchParams.get('id') || '').trim();
        if (!/^[a-zA-Z0-9_-]{8,128}$/.test(id)) throw Object.assign(new Error('SEED_SCOUT_JOB_ID_REQUIRED'), { status: 400 });
        const transport = new RemoteLastWarTransport({
          baseUrl: env.RADAR_CONNECTOR_URL,
          sharedKey: env.RADAR_CONNECTOR_SHARED_KEY,
          timeoutMs: 30000
        });
        try {
          const status = await transport.seedScoutStatus(id);
          const job = status?.job || null;
          if (!job) throw Object.assign(new Error('SEED_SCOUT_JOB_STATUS_INVALID'), { status: 502 });
          return json({ ok: true, readonly: true, collectorMutation: false, job });
        } finally {
          await transport.close().catch(() => {});
        }
      }

      if (url.pathname === '/api/radar/search/start' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const body = await bodyJson(request);
        const query = String(body.q || body.query || '').trim();
        if (!query || query.length > 128) throw Object.assign(new Error('RADAR_QUERY_REQUIRED'), { status: 400 });
        const record = await getCredential(env, session.gameUid);
        if (!record) throw Object.assign(new Error('GAME_CREDENTIAL_NOT_FOUND'), { status: 409 });
        const vaultKey = requireSecret(env.RADAR_TOKEN_VAULT_KEY, 'RADAR_TOKEN_VAULT_KEY');
        const token = await decryptGameToken({ ciphertext: record.ciphertext, iv: record.iv, keyVersion: record.key_version }, vaultKey, session.gameUid);
        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY, timeoutMs: 30000 });
        try {
          const started = await transport.startCollectorSearch(query, token);
          const job = started?.job || null;
          if (!job?.id) throw Object.assign(new Error('COLLECTOR_JOB_START_INVALID'), { status: 502 });
          await audit(env, session.gameUid, 'radar.collector-search.start', query, { jobId: job.id, cycleId: job.cycleId || null, joined: Boolean(job.joined) });
          return json({ ok: true, job }, 202);
        } finally {
          await transport.close().catch(() => {});
        }
      }

      if (url.pathname === '/api/radar/search/status' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const id = String(url.searchParams.get('id') || '').trim();
        if (!/^[a-zA-Z0-9_-]{8,128}$/.test(id)) throw Object.assign(new Error('COLLECTOR_JOB_ID_REQUIRED'), { status: 400 });
        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY, timeoutMs: 60000 });
        try {
          const status = await transport.collectorSearchStatus(id);
          const job = status?.job || null;
          if (!job) throw Object.assign(new Error('COLLECTOR_JOB_STATUS_INVALID'), { status: 502 });

          // Credential lifetime telemetry contains timestamps/status only, never
          // the Last War credential itself. A successful Collector cycle proves
          // the credential was still valid. If a generic native scan failure is
          // returned, run one validation probe so an expired credential is not
          // hidden behind MAP_REGION_FAILED/PROFILE_BATCH_FAILED.
          if (job.status === 'SUCCESS' || job.status === 'FAILED') {
            let issuedAt = null;
            let ageSeconds = null;
            try {
              const issued = await env.DB.prepare(`
                SELECT created_at FROM audit_log
                WHERE actor_uid = ? AND action IN ('auth.lastwar-email.success','auth.game-token.success')
                ORDER BY created_at DESC LIMIT 1
              `).bind(String(session.gameUid)).first();
              issuedAt = issued?.created_at || null;
              const issuedMs = issuedAt ? Date.parse(issuedAt) : NaN;
              ageSeconds = Number.isFinite(issuedMs) ? Math.max(0, Math.floor((Date.now() - issuedMs) / 1000)) : null;
            } catch (_) {}

            if (job.status === 'SUCCESS') {
              await audit(env, session.gameUid, 'auth.lastwar.credential-valid', session.gameUid, {
                issuedAt,
                ageSeconds,
                jobId: job.id,
                cycleId: job.cycleId || null,
                source: 'collector-cycle-success'
              });
            } else {
              const maskedScanErrors = new Set(['MAP_REGION_FAILED', 'PROFILE_BATCH_FAILED', 'COLLECTOR_TARGET_REFRESH_FAILED']);
              if (maskedScanErrors.has(String(job.error || ''))) {
                const record = await getCredential(env, session.gameUid);
                if (record) {
                  const vaultKey = requireSecret(env.RADAR_TOKEN_VAULT_KEY, 'RADAR_TOKEN_VAULT_KEY');
                  const token = await decryptGameToken({ ciphertext: record.ciphertext, iv: record.iv, keyVersion: record.key_version }, vaultKey, session.gameUid);
                  try {
                    await transport.authenticate(token);
                  } catch (probeError) {
                    if (String(probeError?.message || '') === 'LASTWAR_AUTH_REJECTED') {
                      job.error = 'LASTWAR_AUTH_REJECTED';
                      await audit(env, session.gameUid, 'auth.lastwar.credential-rejected', session.gameUid, {
                        issuedAt,
                        ageSeconds,
                        jobId: job.id,
                        cycleId: job.cycleId || null,
                        originalCollectorError: String(status?.job?.error || ''),
                        source: 'collector-failure-auth-probe'
                      });
                    }
                  }
                }
              }
            }
          }
          if (job.status === 'SUCCESS' && /^@profile:\d{6,64}$/i.test(String(job.query || '')) && job.player) {
            const gameUid = String(job.player.gameUid || job.player.game_uid || '').trim();
            if (gameUid) {
              const intOrNull = value => (value === null || value === undefined || value === '')
                ? null
                : (Number.isFinite(Number(value)) ? Math.trunc(Number(value)) : null);
              const armyPower = intOrNull(job.player.armyPower);
              const armyKill = intOrNull(job.player.armyKill);
              const svipLevel = intOrNull(job.player.svipLevel);
              const country = String(job.player.country || '').trim() || null;
              const avatarRef = String(job.player.avatarRef || '').trim() || null;
              const observedAt = String(job.player.observedAt || new Date().toISOString());
              await env.DB.prepare(
                'INSERT INTO radar_profile_rich(subject_uid,army_power,army_kill,svip_level,country,avatar_ref,observed_at,source_command) VALUES(?,?,?,?,?,?,?,?) ' +
                'ON CONFLICT(subject_uid) DO UPDATE SET ' +
                'army_power=COALESCE(excluded.army_power,radar_profile_rich.army_power), ' +
                'army_kill=COALESCE(excluded.army_kill,radar_profile_rich.army_kill), ' +
                'svip_level=COALESCE(excluded.svip_level,radar_profile_rich.svip_level), ' +
                'country=COALESCE(excluded.country,radar_profile_rich.country), ' +
                'avatar_ref=COALESCE(excluded.avatar_ref,radar_profile_rich.avatar_ref), ' +
                'observed_at=excluded.observed_at, source_command=excluded.source_command'
              ).bind(gameUid, armyPower, armyKill, svipLevel, country, avatarRef, observedAt, 'get.user.info.multi').run();
              await audit(env, session.gameUid, 'radar.profile.refresh', gameUid, {
                command: 'get.user.info.multi',
                readonly: true,
                richObserved: Boolean(armyPower !== null || armyKill !== null || svipLevel !== null || country || avatarRef)
              });
            }
          }
          return json({ ok: true, job });
        } finally {
          await transport.close().catch(() => {});
        }
      }

      // WFGG_RADAR_FAST_LOOKUP_ROUTE_V611
      // WFGG_RADAR_CACHE_ENRICHMENT_V6111
      if (url.pathname === '/api/radar/search' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const query = String(url.searchParams.get('q') || '').trim();
        const limit = url.searchParams.get('limit') || 50;
        const cached = await searchRadar(env, query, { limit });
        const cachedRows = Array.isArray(cached?.results) ? cached.results : [];
        const cachedPlayer = cachedRows[0] || null;
        const hasValue = (obj, ...keys) => keys.some((key) => obj?.[key] !== undefined && obj?.[key] !== null && obj?.[key] !== '');
        const playerDisplayComplete = (player) => Boolean(player
          && hasValue(player, 'game_uid', 'gameUid', 'uid', 'playerId')
          && hasValue(player, 'server_id', 'serverId', 'server')
          && hasValue(player, 'alliance_tag', 'allianceTag', 'alliance_id', 'allianceId', 'alliance_name', 'allianceName', 'alliance')
          && hasValue(player, 'hq_level', 'hqLevel', 'level', 'baseLevel')
          && hasValue(player, 'power', 'combatPower', 'strength')
          && hasValue(player, 'x', 'mapX', 'pos_x')
          && hasValue(player, 'y', 'mapY', 'pos_y'));
        const cachedComplete = playerDisplayComplete(cachedPlayer);

        if (!query) {
          return json({ ...cached, fastLookup: { attempted: false, status: 'empty', source: 'd1' } });
        }
        if (cachedRows.length > 0 && cachedComplete) {
          return json({ ...cached, fastLookup: { attempted: false, status: 'd1-hit', source: 'd1', complete: true } });
        }

        const hadPartialCache = cachedRows.length > 0;
        const startedAt = Date.now();
        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY, timeoutMs: 10000 });
        try {
          const exact = await transport.collectorFastLookup(query);
          if (exact?.resolved && exact?.player) {
            const stored = await saveRadarPlayerObservations(env, [exact.player], { sourceCommand: 'collector-fast-identity-v6111' });
            const refreshed = await searchRadar(env, query, { limit });
            const refreshedRows = Array.isArray(refreshed?.results) ? refreshed.results : [];
            const refreshedComplete = playerDisplayComplete(refreshedRows[0]);
            const canonicalResults = refreshedComplete ? refreshedRows : [exact.player];
            return json({
              ...refreshed,
              results: canonicalResults,
              fastLookup: {
                attempted: true,
                status: hadPartialCache ? 'cache-enriched' : 'exact-hit',
                source: 'identity-index',
                route: String(exact.route || 'EXACT_PLAYER'),
                matched: 1,
                cached: stored.inserted,
                cacheWasPartial: hadPartialCache,
                canonicalFallback: !refreshedComplete,
                elapsedMs: Date.now() - startedAt
              }
            });
          }
          if (exact?.ambiguous) {
            return json({
              ...cached,
              fastLookup: {
                attempted: true, status: 'ambiguous', source: 'identity-index', route: String(exact.route || 'AMBIGUOUS'),
                candidateCount: Number(exact.candidateCount || 0), elapsedMs: Date.now() - startedAt
              },
              refreshAvailable: false
            });
          }

          // Local fuzzy fallback only. This still queries the persisted Collector index;
          // it never starts a map/profile cycle and never contacts Last War.
          const indexed = await transport.collectorIndexSearch(query, limit);
          const players = Array.isArray(indexed?.players) ? indexed.players : [];
          if (players.length > 0) {
            const stored = await saveRadarPlayerObservations(env, players, { sourceCommand: 'collector-index-fuzzy-v6111' });
            const refreshed = await searchRadar(env, query, { limit });
            return json({
              ...refreshed,
              results: Array.isArray(refreshed?.results) && refreshed.results.length > 0 ? refreshed.results : players,
              fastLookup: {
                attempted: true, status: 'fuzzy-hit', source: 'collector-index', route: 'FUZZY_LOCAL',
                matched: players.length, cached: stored.inserted, elapsedMs: Date.now() - startedAt
              }
            });
          }

          return json({
            ...cached,
            fastLookup: { attempted: true, status: 'miss', source: 'identity-index', route: String(exact?.route || 'MISS'), cacheWasPartial: hadPartialCache, elapsedMs: Date.now() - startedAt },
            refreshAvailable: session.role === ROLES.OWNER
          });
        } catch (error) {
          return json({
            ...cached,
            fastLookup: { attempted: true, status: 'unavailable', source: 'identity-index', error: String(error?.message || 'FAST_LOOKUP_UNAVAILABLE'), cacheWasPartial: hadPartialCache, elapsedMs: Date.now() - startedAt },
            refreshAvailable: session.role === ROLES.OWNER
          });
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
          await audit(env, session.gameUid, 'oracle.live-snapshot.capture', session.gameUid, { batchId: stored.batchId, observations: stored.observationCount, source: snapshot.source || null });
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
