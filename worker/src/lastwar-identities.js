// WFGG_LASTWAR_IDENTITIES_V2
// All writes go to env.LAB_DB, never to the production WfGg database.
// The WfGg user is validated upstream through /api/me before these functions run.

const PROVIDER = 'lastwar';
const STATUS_PENDING = 'PENDING';

function fail(message, status = 400) {
  const error = new Error(message);
  error.status = status;
  throw error;
}

function clean(value, max, field, required = false) {
  const text = String(value ?? '').trim();
  if (required && !text) fail(`${field}_REQUIRED`, 400);
  if (text.length > max) fail(`${field}_TOO_LONG`, 400);
  return text || null;
}

function shape(row) {
  return {
    id: row.id,
    provider: row.provider,
    player_uid: row.provider_subject,
    server_id: row.server_id || null,
    alliance_id: row.alliance_subject || null,
    status: row.status,
    verification_source: row.verification_source || null,
    verified_at: row.verified_at || null,
    last_verified_at: row.last_verified_at || null,
    created_at: row.created_at,
    updated_at: row.updated_at
  };
}

export function lastWarProviderCapability() {
  return {
    provider: PROVIDER,
    prepared: true,
    login_enabled: false,
    verification_enabled: false,
    claim_enabled: true,
    reason: 'OFFICIAL_VERIFICATION_NOT_CONFIGURED'
  };
}

export async function listExternalIdentities(request, env, sessionContext) {
  const ctx = await sessionContext(request, env);
  const rows = await env.LAB_DB.prepare(`
    SELECT id,wfgg_user_id,provider,provider_subject,server_id,alliance_subject,status,
           verification_source,verified_at,last_verified_at,created_at,updated_at
    FROM external_identities
    WHERE wfgg_user_id=?
    ORDER BY provider, created_at
  `).bind(ctx.id).all();

  return {
    identities: (rows.results || []).map(shape),
    providers: [lastWarProviderCapability()]
  };
}

export async function claimLastWarIdentity(request, env, sessionContext, audit, now, id) {
  const ctx = await sessionContext(request, env);
  const body = await request.json();

  const playerUid = clean(body.player_uid, 80, 'LASTWAR_PLAYER_UID', true);
  const serverId = clean(body.server_id, 40, 'LASTWAR_SERVER_ID', true);
  const allianceId = clean(body.alliance_id, 80, 'LASTWAR_ALLIANCE_ID');
  const ts = now();

  const existing = await env.LAB_DB.prepare(`
    SELECT id,wfgg_user_id,status
    FROM external_identities
    WHERE provider=? AND provider_subject=? AND server_id=?
    LIMIT 1
  `).bind(PROVIDER, playerUid, serverId).first();

  if (existing && existing.wfgg_user_id !== ctx.id) {
    fail('LASTWAR_IDENTITY_ALREADY_CLAIMED', 409);
  }

  const identityId = existing?.id || id('extid');

  if (existing) {
    await env.LAB_DB.prepare(`
      UPDATE external_identities
      SET alliance_subject=?, status=?, verification_source=NULL,
          verified_at=NULL, last_verified_at=NULL, metadata_json=NULL, updated_at=?
      WHERE id=? AND wfgg_user_id=?
    `).bind(allianceId, STATUS_PENDING, ts, identityId, ctx.id).run();
  } else {
    await env.LAB_DB.prepare(`
      INSERT INTO external_identities(
        id,wfgg_user_id,provider,provider_subject,server_id,alliance_subject,status,
        verification_source,verified_at,last_verified_at,metadata_json,created_at,updated_at
      ) VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,?,?)
    `).bind(
      identityId, ctx.id, PROVIDER, playerUid, serverId, allianceId,
      STATUS_PENDING, ts, ts
    ).run();
  }

  await audit(env, ctx.id, 'LASTWAR_IDENTITY_CLAIM', 'external_identity', identityId, {
    provider: PROVIDER,
    player_uid: playerUid,
    server_id: serverId,
    alliance_id: allianceId,
    status: STATUS_PENDING
  });

  const row = await env.LAB_DB.prepare(`
    SELECT id,wfgg_user_id,provider,provider_subject,server_id,alliance_subject,status,
           verification_source,verified_at,last_verified_at,created_at,updated_at
    FROM external_identities WHERE id=? AND wfgg_user_id=?
  `).bind(identityId, ctx.id).first();

  return {
    identity: shape(row),
    warning: 'UNVERIFIED_CLAIM_CANNOT_AUTHENTICATE'
  };
}

export async function revokeLastWarIdentity(request, env, sessionContext, audit, now, identityId) {
  const ctx = await sessionContext(request, env);
  const row = await env.LAB_DB.prepare(`
    SELECT id,wfgg_user_id,provider,status FROM external_identities
    WHERE id=? AND wfgg_user_id=? AND provider=?
  `).bind(identityId, ctx.id, PROVIDER).first();

  if (!row) fail('LASTWAR_IDENTITY_NOT_FOUND', 404);

  await env.LAB_DB.prepare(`
    UPDATE external_identities
    SET status='REVOKED', verification_source=NULL, verified_at=NULL,
        last_verified_at=NULL, updated_at=?
    WHERE id=? AND wfgg_user_id=?
  `).bind(now(), identityId, ctx.id).run();

  await audit(env, ctx.id, 'LASTWAR_IDENTITY_REVOKE', 'external_identity', identityId, {
    provider: PROVIDER
  });

  return { ok: true };
}
