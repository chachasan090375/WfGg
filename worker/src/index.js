const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8' };
const ALLOWED_LANGS = new Set(['fr', 'it', 'en', 'es']);
const ALLOWED_RANKS = new Set(['R1', 'R2', 'R3', 'R4', 'R5']);
const ADMIN_RANKS = new Set(['R4', 'R5']);
const SESSION_DAYS = 365;
const LOGIN_WINDOW_MS = 15 * 60 * 1000;
const LOGIN_BLOCK_MS = 15 * 60 * 1000;
const LOGIN_MAX_FAILURES = 5;

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
      let response;

      if (url.pathname === '/api/health' && request.method === 'GET') {
        response = json({ ok: true, service: 'wfgg-api', version: '0.2.0' });
      } else if (url.pathname === '/api/bootstrap' && request.method === 'POST') {
        response = await bootstrap(request, env);
      } else if (url.pathname === '/api/auth' && request.method === 'POST') {
        response = await authenticate(request, env);
      } else if (url.pathname === '/api/me' && request.method === 'GET') {
        response = await me(request, env);
      } else if (url.pathname === '/api/logout' && request.method === 'POST') {
        response = await logout(request, env);
      } else if (url.pathname === '/api/profile' && request.method === 'PATCH') {
        response = await updateProfile(request, env);
      } else if (url.pathname === '/api/profile/avatar' && request.method === 'POST') {
        response = await uploadAvatar(request, env);
      } else if (url.pathname === '/api/alliance' && request.method === 'PATCH') {
        response = await updateAlliance(request, env);
      } else if (url.pathname === '/api/admin/members' && request.method === 'GET') {
        response = await listMembers(request, env);
      } else if (url.pathname === '/api/admin/members' && request.method === 'POST') {
        response = await createMember(request, env);
      } else if (/^\/api\/admin\/members\/[^/]+$/.test(url.pathname) && request.method === 'PATCH') {
        response = await updateMember(request, env, decodeURIComponent(url.pathname.split('/').pop()));
      } else if (/^\/api\/admin\/members\/[^/]+\/code$/.test(url.pathname) && request.method === 'POST') {
        response = await resetMemberCode(request, env, decodeURIComponent(url.pathname.split('/')[4]));
      } else if (url.pathname.startsWith('/avatars/') && request.method === 'GET') {
        response = await serveAvatar(url.pathname.slice('/avatars/'.length), env);
      } else {
        response = json({ error: 'NOT_FOUND' }, 404);
      }

      return cors(response, request, env);
    } catch (err) {
      console.error(err);
      return cors(json({ error: err?.message || 'INTERNAL_ERROR' }, err?.status || 500), request, env);
    }
  }
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

function allowedOrigins(env) {
  return String(env.PORTAL_ORIGINS || 'https://wfgg.pages.dev')
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
  response.headers.set('Access-Control-Allow-Headers', 'Authorization, Content-Type, X-Bootstrap-Secret');
  response.headers.set('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS');
  response.headers.set('Cache-Control', 'no-store');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  return response;
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

function normalizeCode(code) {
  const normalized = String(code || '').replace(/\D/g, '');
  if (!/^\d{6}$/.test(normalized)) fail('INVALID_CODE', 400);
  return normalized;
}

function normalizeRank(rank) {
  const normalized = String(rank || 'R3').toUpperCase();
  if (!ALLOWED_RANKS.has(normalized)) fail('INVALID_RANK', 400);
  return normalized;
}

function toBase64Url(bytes) {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

async function sha256Text(value) {
  const bytes = new TextEncoder().encode(value);
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

async function codeKey(env, code) {
  return hmacHex(env.APP_SECRET, `wfgg-auth-code:v2:${normalizeCode(code)}`);
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

async function authClientKey(request, env) {
  const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
  return hmacHex(env.APP_SECRET, `wfgg-login-client:v1:${ip}`);
}

async function assertLoginAllowed(env, clientKey) {
  const row = await env.DB.prepare(
    'SELECT failures,window_started_at,blocked_until FROM auth_attempts WHERE client_key=?'
  ).bind(clientKey).first();

  if (!row) return;

  if (row.blocked_until && new Date(row.blocked_until).getTime() > Date.now()) {
    fail('TOO_MANY_ATTEMPTS', 429);
  }

  if (new Date(row.window_started_at).getTime() < Date.now() - LOGIN_WINDOW_MS) {
    await env.DB.prepare('DELETE FROM auth_attempts WHERE client_key=?').bind(clientKey).run();
  }
}

async function recordLoginFailure(env, clientKey) {
  const existing = await env.DB.prepare(
    'SELECT failures,window_started_at FROM auth_attempts WHERE client_key=?'
  ).bind(clientKey).first();

  const ts = now();
  if (!existing || new Date(existing.window_started_at).getTime() < Date.now() - LOGIN_WINDOW_MS) {
    await env.DB.prepare(
      'INSERT OR REPLACE INTO auth_attempts(client_key,failures,window_started_at,blocked_until) VALUES(?,?,?,NULL)'
    ).bind(clientKey, 1, ts).run();
    return;
  }

  const failures = Number(existing.failures || 0) + 1;
  const blockedUntil = failures >= LOGIN_MAX_FAILURES
    ? new Date(Date.now() + LOGIN_BLOCK_MS).toISOString()
    : null;

  await env.DB.prepare(
    'UPDATE auth_attempts SET failures=?,blocked_until=? WHERE client_key=?'
  ).bind(failures, blockedUntil, clientKey).run();
}

async function clearLoginFailures(env, clientKey) {
  await env.DB.prepare('DELETE FROM auth_attempts WHERE client_key=?').bind(clientKey).run();
}

async function bootstrap(request, env) {
  if (!env.BOOTSTRAP_SECRET || request.headers.get('X-Bootstrap-Secret') !== env.BOOTSTRAP_SECRET) {
    fail('FORBIDDEN', 403);
  }

  const count = await env.DB.prepare('SELECT COUNT(*) AS n FROM users').first();
  if ((count?.n || 0) > 0) fail('ALREADY_BOOTSTRAPPED', 409);

  const body = await request.json();
  const allianceId = id('alliance');
  const userId = id('user');
  const ts = now();
  const playerName = String(body.player_name || '').trim();
  const allianceName = String(body.alliance_name || 'WfGg').trim();
  const server = String(body.server || '').trim().slice(0, 30) || null;
  const language = ALLOWED_LANGS.has(body.language) ? body.language : 'fr';

  if (!playerName || playerName.length > 40) fail('PLAYER_NAME_REQUIRED');
  if (!allianceName || allianceName.length > 50) fail('ALLIANCE_NAME_REQUIRED');

  const key = await codeKey(env, body.code);

  await env.DB.batch([
    env.DB.prepare(
      'INSERT INTO alliances(id,name,server,created_at,updated_at) VALUES(?,?,?,?,?)'
    ).bind(allianceId, allianceName, server, ts, ts),
    env.DB.prepare(
      'INSERT INTO users(id,player_name,display_name,language,auth_code_key,active,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?)'
    ).bind(userId, playerName, playerName, language, key, ts, ts),
    env.DB.prepare(
      'INSERT INTO memberships(user_id,alliance_id,rank,created_at,updated_at) VALUES(?,?,?,?,?)'
    ).bind(userId, allianceId, 'R5', ts, ts)
  ]);

  await audit(env, userId, 'BOOTSTRAP', 'alliance', allianceId, { rank: 'R5' });
  return json({ ok: true, user_id: userId, alliance_id: allianceId }, 201);
}

async function authenticate(request, env) {
  const clientKey = await authClientKey(request, env);
  await assertLoginAllowed(env, clientKey);

  const { code } = await request.json();
  const key = await codeKey(env, code);
  const row = await env.DB.prepare(`
    SELECT
      u.*,
      m.alliance_id,
      m.rank,
      a.name AS alliance_name,
      a.server AS alliance_server,
      a.logo_url AS alliance_logo_url
    FROM users u
    JOIN memberships m ON m.user_id = u.id
    JOIN alliances a ON a.id = m.alliance_id
    WHERE u.auth_code_key = ? AND u.active = 1
    LIMIT 1
  `).bind(key).first();

  if (!row) {
    await recordLoginFailure(env, clientKey);
    fail('UNAUTHORIZED', 401);
  }

  await clearLoginFailures(env, clientKey);

  const raw = new Uint8Array(32);
  crypto.getRandomValues(raw);
  const sessionToken = toBase64Url(raw);
  const tokenHash = await sha256Text(sessionToken);
  const ts = now();
  const expires = new Date(Date.now() + SESSION_DAYS * 86400000).toISOString();

  await env.DB.batch([
    env.DB.prepare(
      'INSERT INTO sessions(token_hash,user_id,created_at,expires_at,last_seen_at,user_agent) VALUES(?,?,?,?,?,?)'
    ).bind(
      tokenHash,
      row.id,
      ts,
      expires,
      ts,
      request.headers.get('User-Agent')?.slice(0, 300) || null
    ),
    env.DB.prepare(`
      UPDATE users
      SET first_login_at = COALESCE(first_login_at, ?), last_login_at = ?, updated_at = ?
      WHERE id = ?
    `).bind(ts, ts, ts, row.id)
  ]);

  await audit(env, row.id, 'LOGIN', 'user', row.id);
  return json({ ...shapeContext(row), session_token: sessionToken });
}

async function sessionContext(request, env) {
  const auth = request.headers.get('Authorization') || '';
  if (!auth.startsWith('Bearer ')) fail('UNAUTHORIZED', 401);

  const token = auth.slice(7).trim();
  if (!token) fail('UNAUTHORIZED', 401);

  const hash = await sha256Text(token);
  const row = await env.DB.prepare(`
    SELECT
      s.token_hash,
      s.expires_at,
      u.*,
      m.alliance_id,
      m.rank,
      a.name AS alliance_name,
      a.server AS alliance_server,
      a.logo_url AS alliance_logo_url
    FROM sessions s
    JOIN users u ON u.id = s.user_id
    JOIN memberships m ON m.user_id = u.id
    JOIN alliances a ON a.id = m.alliance_id
    WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1
    LIMIT 1
  `).bind(hash, now()).first();

  if (!row) fail('UNAUTHORIZED', 401);

  env.DB.prepare('UPDATE sessions SET last_seen_at=? WHERE token_hash=?')
    .bind(now(), hash)
    .run()
    .catch(() => {});

  row.session_hash = hash;
  return row;
}

function shapeContext(row) {
  return {
    user: {
      id: row.id,
      player_name: row.player_name,
      display_name: row.display_name,
      language: row.language,
      avatar_url: row.avatar_url,
      profile_completed: Boolean(row.profile_completed_at)
    },
    membership: {
      alliance_id: row.alliance_id,
      rank: row.rank
    },
    alliance: {
      id: row.alliance_id,
      name: row.alliance_name,
      server: row.alliance_server,
      logo_url: row.alliance_logo_url
    }
  };
}

async function me(request, env) {
  return json(shapeContext(await sessionContext(request, env)));
}

async function logout(request, env) {
  const ctx = await sessionContext(request, env);
  await env.DB.prepare('DELETE FROM sessions WHERE token_hash=?').bind(ctx.session_hash).run();
  await audit(env, ctx.id, 'LOGOUT', 'user', ctx.id);
  return json({ ok: true });
}

async function updateProfile(request, env) {
  const ctx = await sessionContext(request, env);
  const body = await request.json();
  const displayName = String(body.display_name || '').trim();
  const language = String(body.language || ctx.language);

  if (!displayName || displayName.length > 40) fail('INVALID_DISPLAY_NAME');
  if (!ALLOWED_LANGS.has(language)) fail('INVALID_LANGUAGE');

  const ts = now();
  await env.DB.prepare(`
    UPDATE users
    SET display_name=?, language=?, profile_completed_at=COALESCE(profile_completed_at, ?), updated_at=?
    WHERE id=?
  `).bind(displayName, language, ts, ts, ctx.id).run();

  await audit(env, ctx.id, 'PROFILE_UPDATE', 'user', ctx.id, {
    display_name: displayName,
    language
  });

  return me(request, env);
}

async function uploadAvatar(request, env) {
  const ctx = await sessionContext(request, env);
  if (!env.AVATARS) fail('AVATAR_STORAGE_NOT_CONFIGURED', 503);

  const form = await request.formData();
  const file = form.get('avatar');
  if (!(file instanceof File)) fail('AVATAR_REQUIRED');
  if (file.size > 2 * 1024 * 1024) fail('AVATAR_TOO_LARGE', 413);

  const allowed = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp'
  };
  const ext = allowed[file.type];
  if (!ext) fail('AVATAR_TYPE_NOT_ALLOWED', 415);

  const key = `${ctx.id}/${crypto.randomUUID()}.${ext}`;
  await env.AVATARS.put(key, await file.arrayBuffer(), {
    httpMetadata: {
      contentType: file.type,
      cacheControl: 'public, max-age=86400'
    }
  });

  const url = new URL(request.url);
  const avatarUrl = `${url.origin}/avatars/${key}`;
  await env.DB.prepare('UPDATE users SET avatar_url=?,updated_at=? WHERE id=?')
    .bind(avatarUrl, now(), ctx.id)
    .run();

  await audit(env, ctx.id, 'AVATAR_UPDATE', 'user', ctx.id);
  return me(request, env);
}

async function serveAvatar(key, env) {
  if (!env.AVATARS || !key || key.includes('..')) return new Response('Not found', { status: 404 });
  const object = await env.AVATARS.get(key);
  if (!object) return new Response('Not found', { status: 404 });

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set('etag', object.httpEtag);
  headers.set('Cache-Control', 'public, max-age=86400');
  headers.set('X-Content-Type-Options', 'nosniff');
  return new Response(object.body, { headers });
}

function requireAllianceAdmin(ctx) {
  if (!ADMIN_RANKS.has(ctx.rank)) fail('FORBIDDEN', 403);
}

function requireR5(ctx) {
  if (ctx.rank !== 'R5') fail('R5_REQUIRED', 403);
}

async function updateAlliance(request, env) {
  const ctx = await sessionContext(request, env);
  requireAllianceAdmin(ctx);

  const body = await request.json();
  const name = String(body.name || '').trim();
  const server = String(body.server || '').trim().slice(0, 30) || null;
  const logoUrl = body.logo_url ? String(body.logo_url).trim().slice(0, 500) : null;

  if (!name || name.length > 50) fail('INVALID_ALLIANCE_NAME');

  await env.DB.prepare(
    'UPDATE alliances SET name=?,server=?,logo_url=?,updated_at=? WHERE id=?'
  ).bind(name, server, logoUrl, now(), ctx.alliance_id).run();

  await audit(env, ctx.id, 'ALLIANCE_UPDATE', 'alliance', ctx.alliance_id, {
    name,
    server,
    logo_url: logoUrl
  });

  const alliance = await env.DB.prepare(
    'SELECT id,name,server,logo_url FROM alliances WHERE id=?'
  ).bind(ctx.alliance_id).first();

  return json({ alliance });
}

async function listMembers(request, env) {
  const ctx = await sessionContext(request, env);
  requireAllianceAdmin(ctx);

  const rows = await env.DB.prepare(`
    SELECT
      u.id,
      u.player_name,
      u.display_name,
      u.language,
      u.avatar_url,
      u.active,
      u.last_login_at,
      u.profile_completed_at,
      m.rank
    FROM users u
    JOIN memberships m ON m.user_id = u.id
    WHERE m.alliance_id = ?
    ORDER BY
      CASE m.rank WHEN 'R5' THEN 0 WHEN 'R4' THEN 1 WHEN 'R3' THEN 2 WHEN 'R2' THEN 3 ELSE 4 END,
      u.display_name COLLATE NOCASE
  `).bind(ctx.alliance_id).all();

  return json({ members: rows.results || [] });
}

async function createMember(request, env) {
  const ctx = await sessionContext(request, env);
  requireAllianceAdmin(ctx);

  const body = await request.json();
  const playerName = String(body.player_name || '').trim();
  const rank = normalizeRank(body.rank);

  if (!playerName || playerName.length > 40) fail('INVALID_PLAYER_NAME');
  if (rank === 'R5') requireR5(ctx);

  const key = await codeKey(env, body.code);
  const userId = id('user');
  const ts = now();

  try {
    await env.DB.batch([
      env.DB.prepare(`
        INSERT INTO users(id,player_name,display_name,language,auth_code_key,active,created_at,updated_at)
        VALUES(?,?,?,?,?,1,?,?)
      `).bind(userId, playerName, playerName, 'fr', key, ts, ts),
      env.DB.prepare(`
        INSERT INTO memberships(user_id,alliance_id,rank,created_at,updated_at)
        VALUES(?,?,?,?,?)
      `).bind(userId, ctx.alliance_id, rank, ts, ts)
    ]);
  } catch (err) {
    console.error(err);
    fail('PLAYER_OR_CODE_ALREADY_EXISTS', 409);
  }

  await audit(env, ctx.id, 'MEMBER_CREATE', 'user', userId, { rank });
  return json({ ok: true, id: userId }, 201);
}

async function getTargetMembership(env, allianceId, userId) {
  return env.DB.prepare(`
    SELECT u.id,u.active,m.rank
    FROM users u
    JOIN memberships m ON m.user_id=u.id
    WHERE u.id=? AND m.alliance_id=?
  `).bind(userId, allianceId).first();
}

async function activeR5Count(env, allianceId) {
  const row = await env.DB.prepare(`
    SELECT COUNT(*) AS n
    FROM users u
    JOIN memberships m ON m.user_id=u.id
    WHERE m.alliance_id=? AND m.rank='R5' AND u.active=1
  `).bind(allianceId).first();
  return Number(row?.n || 0);
}

async function updateMember(request, env, userId) {
  const ctx = await sessionContext(request, env);
  requireAllianceAdmin(ctx);

  const target = await getTargetMembership(env, ctx.alliance_id, userId);
  if (!target) fail('MEMBER_NOT_FOUND', 404);

  const body = await request.json();

  if (Object.prototype.hasOwnProperty.call(body, 'rank')) {
    const nextRank = normalizeRank(body.rank);

    if (nextRank === 'R5' || target.rank === 'R5') requireR5(ctx);
    if (userId === ctx.id && target.rank === 'R5' && nextRank !== 'R5') {
      fail('CANNOT_DEMOTE_SELF_R5', 409);
    }
    if (target.rank === 'R5' && nextRank !== 'R5' && target.active && await activeR5Count(env, ctx.alliance_id) <= 1) {
      fail('ALLIANCE_REQUIRES_ACTIVE_R5', 409);
    }

    await env.DB.prepare(
      'UPDATE memberships SET rank=?,updated_at=? WHERE user_id=? AND alliance_id=?'
    ).bind(nextRank, now(), userId, ctx.alliance_id).run();

    await env.DB.prepare('DELETE FROM sessions WHERE user_id=?').bind(userId).run();
    await audit(env, ctx.id, 'MEMBER_RANK_UPDATE', 'user', userId, { rank: nextRank });
  }

  if (Object.prototype.hasOwnProperty.call(body, 'active')) {
    if (target.rank === 'R5') requireR5(ctx);
    if (userId === ctx.id) fail('CANNOT_DISABLE_SELF', 409);

    const active = body.active ? 1 : 0;
    if (!active && target.rank === 'R5' && await activeR5Count(env, ctx.alliance_id) <= 1) {
      fail('ALLIANCE_REQUIRES_ACTIVE_R5', 409);
    }

    await env.DB.prepare('UPDATE users SET active=?,updated_at=? WHERE id=?')
      .bind(active, now(), userId)
      .run();

    if (!active) {
      await env.DB.prepare('DELETE FROM sessions WHERE user_id=?').bind(userId).run();
    }

    await audit(env, ctx.id, 'MEMBER_ACTIVE_UPDATE', 'user', userId, { active: Boolean(active) });
  }

  return json({ ok: true });
}

async function resetMemberCode(request, env, userId) {
  const ctx = await sessionContext(request, env);
  requireAllianceAdmin(ctx);

  const target = await getTargetMembership(env, ctx.alliance_id, userId);
  if (!target) fail('MEMBER_NOT_FOUND', 404);
  if (target.rank === 'R5' && ctx.rank !== 'R5') fail('R5_REQUIRED', 403);

  const { code } = await request.json();
  const key = await codeKey(env, code);

  try {
    await env.DB.prepare('UPDATE users SET auth_code_key=?,updated_at=? WHERE id=?')
      .bind(key, now(), userId)
      .run();
  } catch (err) {
    console.error(err);
    fail('CODE_ALREADY_EXISTS', 409);
  }

  await env.DB.prepare('DELETE FROM sessions WHERE user_id=?').bind(userId).run();
  await audit(env, ctx.id, 'MEMBER_CODE_RESET', 'user', userId);
  return json({ ok: true });
}
