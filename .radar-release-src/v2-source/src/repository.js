import { ROLES, normalizePseudo } from '../auth/roles.js';

function nowIso() { return new Date().toISOString(); }

function requireDb(env) {
  if (!env?.DB) throw Object.assign(new Error('RADAR_DB_NOT_CONFIGURED'), { status: 503 });
  return env.DB;
}

export async function getUserByUid(env, gameUid) {
  return requireDb(env).prepare('SELECT * FROM users WHERE game_uid = ? LIMIT 1').bind(String(gameUid)).first();
}

export async function listUsers(env) {
  const out = await requireDb(env).prepare(
    'SELECT game_uid, pseudo, server_id, role, active, created_at, updated_at, last_login_at FROM users ORDER BY role DESC, pseudo COLLATE NOCASE ASC'
  ).all();
  return out.results || [];
}

export async function getGrantByPseudo(env, pseudo) {
  const key = normalizePseudo(pseudo);
  return requireDb(env).prepare('SELECT * FROM access_grants WHERE pseudo_key = ? LIMIT 1').bind(key).first();
}

export async function getGrantByBoundUid(env, gameUid) {
  if (!gameUid) return null;
  return requireDb(env).prepare('SELECT * FROM access_grants WHERE bound_game_uid = ? LIMIT 1').bind(String(gameUid)).first();
}

export async function ensureBootstrapOwnerGrant(env, identity) {
  const rawConfigured = String(env?.RADAR_OWNER_PSEUDO || '');
  const configured = normalizePseudo(rawConfigured);
  const identityPseudo = normalizePseudo(identity?.pseudo || '');
  if (!identityPseudo) return null;

  const bound = await getGrantByBoundUid(env, identity.gameUid);
  if (bound) return bound;
  const byPseudo = await getGrantByPseudo(env, identity.pseudo);
  if (byPseudo) return byPseudo;

  if (rawConfigured === '__AUTO_BOOTSTRAP_FIRST_VALID__') {
    const existingOwner = await requireDb(env)
      .prepare('SELECT pseudo_key FROM access_grants WHERE role = ? AND active = 1 LIMIT 1')
      .bind(ROLES.OWNER)
      .first();
    if (existingOwner) return null;
    return upsertGrant(env, { pseudo: identity.pseudo, role: ROLES.OWNER, active: true, actorUid: null });
  }

  if (!configured || configured !== identityPseudo) return null;
  return upsertGrant(env, { pseudo: identity.pseudo, role: ROLES.OWNER, active: true, actorUid: null });
}

export async function listGrants(env) {
  const out = await requireDb(env).prepare(
    'SELECT pseudo_key, display_pseudo, role, active, bound_game_uid, created_at, updated_at FROM access_grants ORDER BY role DESC, display_pseudo COLLATE NOCASE ASC'
  ).all();
  return out.results || [];
}

export async function upsertGrant(env, { pseudo, role = ROLES.USER, active = true, actorUid = null }) {
  const db = requireDb(env);
  const pseudoKey = normalizePseudo(pseudo);
  if (!pseudoKey) throw Object.assign(new Error('PSEUDO_REQUIRED'), { status: 400 });
  const ts = nowIso();
  const existing = await getGrantByPseudo(env, pseudo);
  if (existing?.role === ROLES.OWNER && (role !== ROLES.OWNER || !active)) throw Object.assign(new Error('OWNER_GRANT_IMMUTABLE'), { status: 409 });
  await db.prepare(`
    INSERT INTO access_grants(pseudo_key, display_pseudo, role, active, bound_game_uid, created_at, updated_at)
    VALUES(?,?,?,?,NULL,?,?)
    ON CONFLICT(pseudo_key) DO UPDATE SET display_pseudo=excluded.display_pseudo, role=excluded.role, active=excluded.active, updated_at=excluded.updated_at
  `).bind(pseudoKey, String(pseudo).trim(), role, active ? 1 : 0, ts, ts).run();
  await audit(env, actorUid, 'admin.grant.upsert', pseudoKey, { role, active: Boolean(active) });
  return getGrantByPseudo(env, pseudo);
}

export async function bindIdentityToGrant(env, identity) {
  const db = requireDb(env);
  const grant = await getGrantByBoundUid(env, identity.gameUid) || await getGrantByPseudo(env, identity.pseudo);
  if (!grant || !grant.active) throw Object.assign(new Error('RADAR_ACCESS_NOT_GRANTED'), { status: 403 });
  if (grant.bound_game_uid && String(grant.bound_game_uid) !== String(identity.gameUid)) {
    throw Object.assign(new Error('PSEUDO_ALREADY_BOUND_TO_ANOTHER_UID'), { status: 403 });
  }
  const ts = nowIso();
  if (!grant.bound_game_uid) {
    await db.prepare('UPDATE access_grants SET bound_game_uid = ?, updated_at = ? WHERE pseudo_key = ?')
      .bind(String(identity.gameUid), ts, grant.pseudo_key).run();
  } else if (grant.display_pseudo !== identity.pseudo) {
    await db.prepare('UPDATE access_grants SET display_pseudo = ?, updated_at = ? WHERE pseudo_key = ?')
      .bind(String(identity.pseudo), ts, grant.pseudo_key).run();
  }
  const existingUser = await getUserByUid(env, identity.gameUid);
  if (existingUser?.role === ROLES.OWNER && grant.role !== ROLES.OWNER) {
    throw Object.assign(new Error('OWNER_ROLE_IMMUTABLE'), { status: 409 });
  }
  await db.prepare(`
    INSERT INTO users(game_uid, pseudo, server_id, role, active, created_at, updated_at, last_login_at)
    VALUES(?,?,?,?,1,?,?,?)
    ON CONFLICT(game_uid) DO UPDATE SET pseudo=excluded.pseudo, server_id=excluded.server_id, active=1, updated_at=excluded.updated_at, last_login_at=excluded.last_login_at
  `).bind(String(identity.gameUid), String(identity.pseudo), identity.serverId || null, grant.role, ts, ts, ts).run();
  return getUserByUid(env, identity.gameUid);
}


export async function getCredential(env, gameUid) {
  return requireDb(env).prepare('SELECT game_uid, ciphertext, iv, key_version FROM game_credentials WHERE game_uid = ? LIMIT 1').bind(String(gameUid)).first();
}

export async function saveObservedSnapshot(env, observerUid, snapshot = {}) {
  const db = requireDb(env);
  const observations = Array.isArray(snapshot.observations) ? snapshot.observations : [];
  const safe = observations.filter(o => String(o?.status || '').toUpperCase() === 'OBSERVED' && o?.path && o?.source).slice(0, 500);
  const observedAt = safe[0]?.observedAt || new Date().toISOString();
  const meta = await db.prepare(`
    INSERT INTO game_observation_batches(observer_uid, source, readonly, transcript_sha256, observed_at)
    VALUES(?,?,?,?,?) RETURNING id
  `).bind(
    observerUid ? String(observerUid) : null,
    String(snapshot.source || 'unknown'),
    snapshot.readonly === true ? 1 : 0,
    snapshot.session?.transcriptSha256 || null,
    observedAt
  ).first();
  const batchId = meta?.id;
  if (!batchId) throw new Error('OBSERVATION_BATCH_INSERT_FAILED');
  for (const o of safe) {
    await db.prepare(`
      INSERT INTO game_observation_fields(batch_id, field_path, value_json, source, status, observed_at)
      VALUES(?,?,?,?,?,?)
    `).bind(batchId, String(o.path), JSON.stringify(o.value ?? null), String(o.source), 'OBSERVED', o.observedAt || observedAt).run();
  }
  return { batchId, observationCount: safe.length, observedAt };
}
export async function saveRadarPlayerObservations(env, players = [], { sourceCommand = 'native-template-player-scan-v2', rawRef = null } = {}) {
  const db = requireDb(env);
  const safe = Array.isArray(players) ? players.slice(0, 100) : [];
  let inserted = 0;
  for (const player of safe) {
    const pseudo = String(player?.pseudo || '').trim();
    const subjectUid = player?.gameUid ? String(player.gameUid).trim() : null;
    if (!pseudo && !subjectUid) continue;
    const observedAt = String(player?.observedAt || nowIso());
    const intOrNull = value => (value === null || value === undefined || value === '') ? null : (Number.isFinite(Number(value)) ? Math.trunc(Number(value)) : null);
    await db.prepare(`
      INSERT INTO radar_observations(
        subject_uid, pseudo, server_id, alliance_id, alliance_tag,
        x, y, hq_level, power, shield_state,
        observed_at, source_command, raw_ref
      ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
    `).bind(
      subjectUid,
      pseudo || null,
      player?.serverId ? String(player.serverId) : null,
      player?.allianceId ? String(player.allianceId) : null,
      player?.allianceTag ? String(player.allianceTag) : null,
      intOrNull(player?.x), intOrNull(player?.y), intOrNull(player?.hqLevel), intOrNull(player?.power),
      player?.shieldState == null ? null : String(player.shieldState),
      observedAt, String(sourceCommand || 'native-template-player-scan-v2'), rawRef ? String(rawRef) : null
    ).run();
    inserted++;
  }
  return { inserted };
}

export async function saveRadarIdentityObservation(env, { identity = null, session = null, batchId = null, observedAt = null } = {}) {
  const gameUid = String(identity?.gameUid || '').trim();
  const pseudo = String(identity?.pseudo || '').trim();
  if (!gameUid || !pseudo) return null;
  const ts = observedAt || nowIso();
  const serverId = identity?.serverId || session?.serverId || null;
  const rawRef = batchId ? `game_observation_batch:${batchId}` : null;
  await requireDb(env).prepare(`
    INSERT INTO radar_observations(
      subject_uid, pseudo, server_id, alliance_id, alliance_tag,
      x, y, hq_level, power, shield_state,
      observed_at, source_command, raw_ref
    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
  `).bind(
    gameUid, pseudo, serverId ? String(serverId) : null, null, null,
    null, null, null, null, null,
    ts, 'oracle.live-snapshot.identity', rawRef
  ).run();
  return { subjectUid: gameUid, pseudo, serverId: serverId ? String(serverId) : null, observedAt: ts, rawRef };
}

export async function saveCredential(env, gameUid, encrypted) {
  const ts = nowIso();
  await requireDb(env).prepare(`
    INSERT INTO game_credentials(game_uid, ciphertext, iv, key_version, updated_at)
    VALUES(?,?,?,?,?)
    ON CONFLICT(game_uid) DO UPDATE SET ciphertext=excluded.ciphertext, iv=excluded.iv, key_version=excluded.key_version, updated_at=excluded.updated_at
  `).bind(String(gameUid), encrypted.ciphertext, encrypted.iv, encrypted.keyVersion, ts).run();
}

export async function searchObservations(env, query, limit = 50) {
  const q = String(query || '').trim();
  const safeLimit = Math.max(1, Math.min(Number(limit) || 50, 200));
  if (!q) return [];
  const like = `%${q}%`;
  const out = await requireDb(env).prepare(`
    SELECT id, subject_uid, pseudo, server_id, alliance_id, alliance_tag, x, y, hq_level, power, shield_state, observed_at, source_command
    FROM radar_observations
    WHERE subject_uid = ? OR pseudo LIKE ? COLLATE NOCASE OR alliance_tag LIKE ? COLLATE NOCASE
    ORDER BY observed_at DESC LIMIT ?
  `).bind(q, like, like, safeLimit).all();
  return out.results || [];
}

export async function audit(env, actorUid, action, target = null, detail = null) {
  if (!env?.DB) return;
  await env.DB.prepare('INSERT INTO audit_log(actor_uid, action, target, detail_json, created_at) VALUES(?,?,?,?,?)')
    .bind(actorUid ? String(actorUid) : null, String(action), target ? String(target) : null, detail ? JSON.stringify(detail) : null, nowIso()).run();
}
