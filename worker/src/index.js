import { routeLastWarConnector } from './lastwar-connector.js';
import { routeLastWarIdentity, routeLastWarCloudSync } from './lastwar-identity.js';
export { LastWarUserContainer } from './lastwar-container.js';

const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8' };
const ALLOWED_LANGS = new Set(['fr', 'it', 'en', 'es']);
const ALLOWED_RANKS = new Set(['R1', 'R2', 'R3', 'R4', 'R5']);
const ALLOWED_OFFICER_TITLES = new Set(['WARLORD', 'RECRUITER', 'MUSE', 'BUTLER']);
const ADMIN_RANKS = new Set(['R4', 'R5']);
const SYSTEM_OWNER = 'OWNER';
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

      const lastWarDeps = {
        sessionContext,
        json,
        fail,
        audit,
        now,
        sha256Text,
        hmacHex,
        toBase64Url,
        id
      };
      const identityResponse = await routeLastWarIdentity(request, env, url, lastWarDeps);
      const cloudSyncResponse = identityResponse
        ? null
        : await routeLastWarCloudSync(request, env, url, lastWarDeps);
      const connectorResponse = identityResponse || cloudSyncResponse
        ? null
        : await routeLastWarConnector(request, env, lastWarDeps);

      if (identityResponse) {
        response = identityResponse;
      } else if (cloudSyncResponse) {
        response = cloudSyncResponse;
      } else if (connectorResponse) {
        response = connectorResponse;
      } else if (url.pathname === '/api/health' && request.method === 'GET') {
        response = json({ ok: true, service: 'wfgg-api', version: '0.5.0-lastwar-container', admin_gate: 'R4_R5_ONLY', lastwar_container: Boolean(env.LASTWAR_USER) });
      } else if (url.pathname === '/api/bootstrap' && request.method === 'POST') {
        response = await bootstrap(request, env);
      } else if (url.pathname === '/api/auth' && request.method === 'POST') {
        response = await authenticate(request, env);
      } else if (url.pathname === '/api/me' && request.method === 'GET') {
        response = await me(request, env);
      } else if (url.pathname === '/api/train/context' && request.method === 'GET') {
        response = await trainContext(request, env);
      } else if (url.pathname === '/api/logout' && request.method === 'POST') {
        response = await logout(request, env);
      } else if (url.pathname === '/api/profile' && request.method === 'PATCH') {
        response = await updateProfile(request, env);
      } else if (url.pathname === '/api/profile/language' && request.method === 'PATCH') {
        response = await updateProfileLanguage(request, env);
      } else if (url.pathname === '/api/profile/avatar' && request.method === 'POST') {
        response = await uploadAvatar(request, env);
      } else if (url.pathname === '/api/me/code' && request.method === 'PATCH') {
        response = await updateOwnCode(request, env);
      } else if (url.pathname === '/api/me/sessions' && request.method === 'GET') {
        response = await listOwnSessions(request, env);
      } else if (url.pathname === '/api/me/sessions/others' && request.method === 'DELETE') {
        response = await revokeOtherSessions(request, env);
      } else if (url.pathname === '/api/portal/settings' && request.method === 'PATCH') {
        response = await updatePortalSettings(request, env);
      } else if (url.pathname === '/api/alliance' && request.method === 'PATCH') {
        response = await updateAlliance(request, env);
      } else if (url.pathname === '/api/admin/members' && request.method === 'GET') {
        response = await listMembers(request, env);
      } else if (url.pathname === '/api/admin/members' && request.method === 'POST') {
        response = await createMember(request, env);
      } else if (url.pathname === '/api/admin/leadership/transfer' && request.method === 'POST') {
        response = await transferLeadership(request, env);
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
  response.headers.set('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS');
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

function normalizeOfficerTitle(value) {
  if (value === null || value === undefined || String(value).trim() === '') return null;
  const normalized = String(value).trim().toUpperCase();
  if (!ALLOWED_OFFICER_TITLES.has(normalized)) fail('INVALID_OFFICER_TITLE', 400);
  return normalized;
}

function isOwner(ctx) {
  return ctx.system_role === SYSTEM_OWNER;
}

function canTransferLeadership(ctx) {
  return isOwner(ctx) || ADMIN_RANKS.has(ctx.rank);
}

function permissionsFor(ctx) {
  const admin = ADMIN_RANKS.has(ctx.rank);
  return {
    is_owner: isOwner(ctx),
    can_admin_members: admin,
    can_manage_alliance: admin,
    can_manage_portal_settings: admin,
    can_assign_r4_offices: admin,
    can_transfer_r5: admin
  };
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

function constantTimeEqual(a, b) {
  const left = String(a || '');
  const right = String(b || '');
  if (left.length !== right.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i += 1) {
    diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
  }
  return diff === 0;
}

async function verifyOwnCode(ctx, env, code) {
  const supplied = await codeKey(env, code);
  if (!constantTimeEqual(supplied, ctx.auth_code_key)) fail('REAUTH_REQUIRED', 403);
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
  const officerTitle = normalizeOfficerTitle(body.officer_title);

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
      'INSERT INTO memberships(user_id,alliance_id,rank,officer_title,created_at,updated_at) VALUES(?,?,?,?,?,?)'
    ).bind(userId, allianceId, 'R4', officerTitle, ts, ts),
    env.DB.prepare(
      'INSERT INTO system_roles(user_id,role,created_at) VALUES(?,?,?)'
    ).bind(userId, SYSTEM_OWNER, ts)
  ]);

  await audit(env, userId, 'BOOTSTRAP_OWNER', 'alliance', allianceId, {
    rank: 'R4',
    officer_title: officerTitle,
    system_role: SYSTEM_OWNER
  });

  return json({
    ok: true,
    user_id: userId,
    alliance_id: allianceId,
    rank: 'R4',
    officer_title: officerTitle,
    system_role: SYSTEM_OWNER
  }, 201);
}

const SESSION_SELECT = `
  SELECT
    u.*,
    m.alliance_id,
    m.rank,
    m.officer_title,
    sr.role AS system_role,
    a.name AS alliance_name,
    a.server AS alliance_server,
    a.logo_url AS alliance_logo_url,
    a.settings_json AS alliance_settings_json
  FROM users u
  JOIN memberships m ON m.user_id = u.id
  JOIN alliances a ON a.id = m.alliance_id
  LEFT JOIN system_roles sr ON sr.user_id = u.id
`;

async function authenticate(request, env) {
  const clientKey = await authClientKey(request, env);
  await assertLoginAllowed(env, clientKey);

  const { code } = await request.json();
  const key = await codeKey(env, code);
  const row = await env.DB.prepare(`
    ${SESSION_SELECT}
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
      m.officer_title,
      sr.role AS system_role,
      a.name AS alliance_name,
      a.server AS alliance_server,
      a.logo_url AS alliance_logo_url,
      a.settings_json AS alliance_settings_json
    FROM sessions s
    JOIN users u ON u.id = s.user_id
    JOIN memberships m ON m.user_id = u.id
    JOIN alliances a ON a.id = m.alliance_id
    LEFT JOIN system_roles sr ON sr.user_id = u.id
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

function parseSettingsJson(raw) {
  try {
    const parsed = JSON.parse(String(raw || '{}'));
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch (_) {
    return {};
  }
}

function portalSettingsFromRaw(raw) {
  const root = parseSettingsJson(raw);
  const p = root.portal && typeof root.portal === 'object' ? root.portal : {};
  return {
    welcome_text: String(p.welcome_text || '').slice(0, 180),
    guides_title: String(p.guides_title || '').slice(0, 40),
    guides_url: p.guides_url ? String(p.guides_url).slice(0, 500) : null,
    train_title: String(p.train_title || '').slice(0, 40),
    train_url: p.train_url ? String(p.train_url).slice(0, 500) : null
  };
}

function validateHttpsUrl(value, field) {
  const text = String(value || '').trim();
  if (!text) return null;
  if (text.length > 500) fail(`${field}_TOO_LONG`, 400);
  let url;
  try { url = new URL(text); } catch (_) { fail(`${field}_INVALID`, 400); }
  if (url.protocol !== 'https:') fail(`${field}_HTTPS_REQUIRED`, 400);
  return url.toString();
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
      rank: row.rank,
      officer_title: row.officer_title || null
    },
    system: {
      role: row.system_role || null
    },
    permissions: permissionsFor(row),
    alliance: {
      id: row.alliance_id,
      name: row.alliance_name,
      server: row.alliance_server,
      logo_url: row.alliance_logo_url
    },
    portal_settings: portalSettingsFromRaw(row.alliance_settings_json)
  };
}

async function me(request, env) {
  return json(shapeContext(await sessionContext(request, env)));
}

async function trainContext(request, env) {
  const ctx = await sessionContext(request, env);
  const current = shapeContext(ctx);

  const rows = await env.DB.prepare(`
    SELECT
      u.id,
      u.player_name,
      u.display_name,
      u.language,
      u.avatar_url,
      u.active,
      u.last_login_at,
      u.updated_at,
      m.rank,
      m.officer_title,
      sr.role AS system_role
    FROM users u
    JOIN memberships m ON m.user_id = u.id
    LEFT JOIN system_roles sr ON sr.user_id = u.id
    WHERE m.alliance_id = ?
    ORDER BY
      CASE m.rank
        WHEN 'R5' THEN 0
        WHEN 'R4' THEN 1
        WHEN 'R3' THEN 2
        WHEN 'R2' THEN 3
        ELSE 4
      END,
      u.display_name COLLATE NOCASE
  `).bind(ctx.alliance_id).all();

  return json({
    ok: true,
    source: 'wfgg-portal',
    me: {
      id: current.user.id,
      pseudo: current.user.display_name || current.user.player_name,
      player_name: current.user.player_name,
      display_name: current.user.display_name,
      language: current.user.language,
      avatar: current.user.avatar_url || null,
      rank: current.membership.rank,
      officer_title: current.membership.officer_title || null
    },
    alliance: current.alliance,
    roster: (rows.results || []).map((row) => ({
      id: row.id,
      pseudo: row.display_name || row.player_name,
      player_name: row.player_name,
      display_name: row.display_name,
      language: row.language,
      avatar: row.avatar_url || null,
      rank: row.rank,
      officer_title: row.officer_title || null,
      active: Boolean(row.active),
      last_login_at: row.last_login_at || null,
      updated_at: row.updated_at || null,
      system_role: row.system_role || null
    }))
  });
}

async function logout(request, env) {
  const ctx = await sessionContext(request, env);
  await env.DB.prepare('DELETE FROM sessions WHERE token_hash=?').bind(ctx.session_hash).run();
  await audit(env, ctx.id, 'LOGOUT', 'user', ctx.id);
  return json({ ok: true });
}

async function updateProfileLanguage(request, env) {
  const ctx = await sessionContext(request, env);
  const body = await request.json();
  const language = String(body.language || '').trim().toLowerCase();
  if (!ALLOWED_LANGS.has(language)) fail('INVALID_LANGUAGE');

  const ts = now();
  await env.DB.prepare('UPDATE users SET language=?, updated_at=? WHERE id=?')
    .bind(language, ts, ctx.id).run();

  await audit(env, ctx.id, 'LANGUAGE_UPDATE', 'user', ctx.id, { language });
  return me(request, env);
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

async function updateOwnCode(request, env) {
  const ctx = await sessionContext(request, env);
  const body = await request.json();
  await verifyOwnCode(ctx, env, body.current_code);
  const nextKey = await codeKey(env, body.new_code);
  try {
    await env.DB.prepare('UPDATE users SET auth_code_key=?,updated_at=? WHERE id=?')
      .bind(nextKey, now(), ctx.id).run();
  } catch (err) {
    console.error(err);
    fail('CODE_ALREADY_EXISTS', 409);
  }
  await env.DB.prepare('DELETE FROM sessions WHERE user_id=? AND token_hash<>?')
    .bind(ctx.id, ctx.session_hash).run();
  await audit(env, ctx.id, 'OWN_CODE_UPDATE', 'user', ctx.id);
  return json({ ok: true });
}

async function listOwnSessions(request, env) {
  const ctx = await sessionContext(request, env);
  const rows = await env.DB.prepare(`
    SELECT token_hash,created_at,expires_at,last_seen_at,user_agent
    FROM sessions WHERE user_id=? AND expires_at>? ORDER BY last_seen_at DESC
  `).bind(ctx.id, now()).all();
  return json({ sessions: (rows.results || []).map((row) => ({
    created_at: row.created_at,
    expires_at: row.expires_at,
    last_seen_at: row.last_seen_at,
    user_agent: row.user_agent,
    current: row.token_hash === ctx.session_hash
  })) });
}

async function revokeOtherSessions(request, env) {
  const ctx = await sessionContext(request, env);
  await env.DB.prepare('DELETE FROM sessions WHERE user_id=? AND token_hash<>?')
    .bind(ctx.id, ctx.session_hash).run();
  await audit(env, ctx.id, 'OTHER_SESSIONS_REVOKED', 'user', ctx.id);
  return json({ ok: true });
}

async function updatePortalSettings(request, env) {
  const ctx = await sessionContext(request, env);
  requireAllianceAdmin(ctx);
  const body = await request.json();
  const welcomeText = String(body.welcome_text || '').trim().slice(0, 180);
  const guidesTitle = String(body.guides_title || 'Guides').trim().slice(0, 40) || 'Guides';
  const trainTitle = String(body.train_title || 'Train').trim().slice(0, 40) || 'Train';
  const guidesUrl = validateHttpsUrl(body.guides_url, 'GUIDES_URL');
  const trainUrl = validateHttpsUrl(body.train_url, 'TRAIN_URL');
  const row = await env.DB.prepare('SELECT settings_json FROM alliances WHERE id=?').bind(ctx.alliance_id).first();
  const root = parseSettingsJson(row?.settings_json);
  root.portal = { welcome_text: welcomeText, guides_title: guidesTitle, guides_url: guidesUrl, train_title: trainTitle, train_url: trainUrl };
  await env.DB.prepare('UPDATE alliances SET settings_json=?,updated_at=? WHERE id=?')
    .bind(JSON.stringify(root), now(), ctx.alliance_id).run();
  await audit(env, ctx.id, 'PORTAL_SETTINGS_UPDATE', 'alliance', ctx.alliance_id, root.portal);
  return json({ portal_settings: root.portal });
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

function requireR5OrOwner(ctx) {
  requireAllianceAdmin(ctx);
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
      m.rank,
      m.officer_title,
      sr.role AS system_role
    FROM users u
    JOIN memberships m ON m.user_id = u.id
    LEFT JOIN system_roles sr ON sr.user_id = u.id
    WHERE m.alliance_id = ?
    ORDER BY
      CASE m.rank WHEN 'R5' THEN 0 WHEN 'R4' THEN 1 WHEN 'R3' THEN 2 WHEN 'R2' THEN 3 ELSE 4 END,
      CASE WHEN sr.role = 'OWNER' THEN 0 ELSE 1 END,
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
  const officerTitle = normalizeOfficerTitle(body.officer_title);

  if (!playerName || playerName.length > 40) fail('INVALID_PLAYER_NAME');
  if (rank === 'R5') fail('CREATE_AS_R4_THEN_TRANSFER_R5', 409);

  if (officerTitle) {
    requireR5OrOwner(ctx);
    if (rank !== 'R4') fail('OFFICER_REQUIRES_R4', 409);
  }


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
        INSERT INTO memberships(user_id,alliance_id,rank,officer_title,created_at,updated_at)
        VALUES(?,?,?,?,?,?)
      `).bind(userId, ctx.alliance_id, rank, officerTitle, ts, ts)
    ]);
  } catch (err) {
    console.error(err);
    if (String(err?.message || '').includes('idx_memberships_unique_officer_per_alliance')) {
      fail('OFFICER_TITLE_ALREADY_ASSIGNED', 409);
    }
    fail('PLAYER_OR_CODE_ALREADY_EXISTS', 409);
  }

  await audit(env, ctx.id, 'MEMBER_CREATE', 'user', userId, {
    rank,
    officer_title: officerTitle
  });

  return json({ ok: true, id: userId }, 201);
}

async function getTargetMembership(env, allianceId, userId) {
  return env.DB.prepare(`
    SELECT
      u.id,
      u.active,
      u.auth_code_key,
      m.rank,
      m.officer_title,
      sr.role AS system_role
    FROM users u
    JOIN memberships m ON m.user_id=u.id
    LEFT JOIN system_roles sr ON sr.user_id=u.id
    WHERE u.id=? AND m.alliance_id=?
  `).bind(userId, allianceId).first();
}

async function currentR5(env, allianceId) {
  return env.DB.prepare(`
    SELECT u.id, u.active
    FROM users u
    JOIN memberships m ON m.user_id=u.id
    WHERE m.alliance_id=? AND m.rank='R5'
    LIMIT 1
  `).bind(allianceId).first();
}

async function updateMember(request, env, userId) {
  const ctx = await sessionContext(request, env);
  requireAllianceAdmin(ctx);

  let target = await getTargetMembership(env, ctx.alliance_id, userId);
  if (!target) fail('MEMBER_NOT_FOUND', 404);

  if (target.system_role === SYSTEM_OWNER && !isOwner(ctx)) fail('OWNER_PROTECTED', 403);

  const body = await request.json();

  if (Object.prototype.hasOwnProperty.call(body, 'rank')) {
    const nextRank = normalizeRank(body.rank);

    if (nextRank === 'R5' || target.rank === 'R5') {
      fail('USE_LEADERSHIP_TRANSFER', 409);
    }

    if (target.officer_title && nextRank !== 'R4') {
      fail('CLEAR_OFFICER_TITLE_FIRST', 409);
    }

    await env.DB.prepare(
      'UPDATE memberships SET rank=?,updated_at=? WHERE user_id=? AND alliance_id=?'
    ).bind(nextRank, now(), userId, ctx.alliance_id).run();

    await env.DB.prepare('DELETE FROM sessions WHERE user_id=?').bind(userId).run();
    await audit(env, ctx.id, 'MEMBER_RANK_UPDATE', 'user', userId, { rank: nextRank });
    target = await getTargetMembership(env, ctx.alliance_id, userId);
  }

  if (Object.prototype.hasOwnProperty.call(body, 'officer_title')) {
    requireR5OrOwner(ctx);
    const officerTitle = normalizeOfficerTitle(body.officer_title);

    if (target.rank !== 'R4' && officerTitle) fail('OFFICER_REQUIRES_R4', 409);

    try {
      await env.DB.prepare(
        'UPDATE memberships SET officer_title=?,updated_at=? WHERE user_id=? AND alliance_id=?'
      ).bind(officerTitle, now(), userId, ctx.alliance_id).run();
    } catch (err) {
      console.error(err);
      fail('OFFICER_TITLE_ALREADY_ASSIGNED', 409);
    }

    await env.DB.prepare('DELETE FROM sessions WHERE user_id=?').bind(userId).run();
    await audit(env, ctx.id, 'MEMBER_OFFICER_UPDATE', 'user', userId, {
      officer_title: officerTitle
    });
    target = await getTargetMembership(env, ctx.alliance_id, userId);
  }

  if (Object.prototype.hasOwnProperty.call(body, 'active')) {
    if (target.rank === 'R5') fail('TRANSFER_R5_BEFORE_DISABLE', 409);
    if (target.rank === 'R4') requireR5OrOwner(ctx);
    if (userId === ctx.id) fail('CANNOT_DISABLE_SELF', 409);
    if (target.system_role === SYSTEM_OWNER) fail('OWNER_CANNOT_BE_DISABLED', 409);

    const active = body.active ? 1 : 0;
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

async function transferLeadership(request, env) {
  const ctx = await sessionContext(request, env);
  if (!canTransferLeadership(ctx)) fail('LEADERSHIP_TRANSFER_FORBIDDEN', 403);

  const body = await request.json();
  const targetUserId = String(body.target_user_id || '').trim();
  if (!targetUserId) fail('TARGET_USER_REQUIRED', 400);

  await verifyOwnCode(ctx, env, body.current_code);

  const target = await getTargetMembership(env, ctx.alliance_id, targetUserId);
  if (!target || !target.active) fail('TARGET_MEMBER_NOT_ACTIVE', 404);
  if (target.system_role === SYSTEM_OWNER && !isOwner(ctx)) fail('OWNER_PROTECTED', 403);
  if (target.rank !== 'R4') fail('R5_TARGET_MUST_BE_R4', 409);

  const oldR5 = await currentR5(env, ctx.alliance_id);
  const ts = now();

  const statements = [];

  if (oldR5 && oldR5.id !== targetUserId) {
    statements.push(
      env.DB.prepare(
        "UPDATE memberships SET rank='R4',officer_title=NULL,updated_at=? WHERE user_id=? AND alliance_id=?"
      ).bind(ts, oldR5.id, ctx.alliance_id)
    );
  }

  statements.push(
    env.DB.prepare(
      "UPDATE memberships SET rank='R5',officer_title=NULL,updated_at=? WHERE user_id=? AND alliance_id=?"
    ).bind(ts, targetUserId, ctx.alliance_id)
  );

  if (oldR5 && oldR5.id !== targetUserId) {
    statements.push(
      env.DB.prepare('DELETE FROM sessions WHERE user_id=?').bind(oldR5.id)
    );
  }

  statements.push(
    env.DB.prepare('DELETE FROM sessions WHERE user_id=?').bind(targetUserId)
  );

  await env.DB.batch(statements);

  await audit(env, ctx.id, 'LEADERSHIP_TRANSFER', 'user', targetUserId, {
    previous_r5_user_id: oldR5?.id || null,
    new_r5_user_id: targetUserId,
    actor_rank: ctx.rank,
    actor_officer_title: ctx.officer_title || null,
    actor_system_role: ctx.system_role || null
  });

  return json({
    ok: true,
    previous_r5_user_id: oldR5?.id || null,
    new_r5_user_id: targetUserId
  });
}

async function resetMemberCode(request, env, userId) {
  const ctx = await sessionContext(request, env);
  requireAllianceAdmin(ctx);

  const target = await getTargetMembership(env, ctx.alliance_id, userId);
  if (!target) fail('MEMBER_NOT_FOUND', 404);
  if (target.system_role === SYSTEM_OWNER && !isOwner(ctx)) fail('OWNER_PROTECTED', 403);
  if (target.rank === 'R5' || target.rank === 'R4') requireR5OrOwner(ctx);

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
