const TRAIN_API = 'https://wfgg-train.chachasan090375.workers.dev';
const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' };

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

async function responseJson(response) {
  try { return await response.clone().json(); } catch (_) { return null; }
}

function requestFor(request, pathname, method = 'GET', body = null) {
  const url = new URL(request.url);
  url.pathname = pathname;
  url.search = '';
  const headers = new Headers(request.headers);
  if (body !== null) headers.set('Content-Type', 'application/json');
  return new Request(url.toString(), {
    method,
    headers,
    body: body === null ? undefined : JSON.stringify(body),
    redirect: 'manual'
  });
}

function bearerToken(request) {
  const auth = request.headers.get('Authorization') || '';
  return auth.startsWith('Bearer ') ? auth.slice(7).trim() : '';
}

function randomCode() {
  const bytes = new Uint32Array(1);
  crypto.getRandomValues(bytes);
  return String(bytes[0] % 1000000).padStart(6, '0');
}

function sameName(a, b) {
  return String(a || '').trim().localeCompare(String(b || '').trim(), undefined, { sensitivity: 'accent' }) === 0;
}

async function rollbackPortalUser(env, actorId, userId, reason) {
  const ts = new Date().toISOString();
  await env.DB.batch([
    env.DB.prepare('DELETE FROM sessions WHERE user_id=?').bind(userId),
    env.DB.prepare('DELETE FROM system_roles WHERE user_id=?').bind(userId),
    env.DB.prepare('DELETE FROM memberships WHERE user_id=?').bind(userId),
    env.DB.prepare('DELETE FROM users WHERE id=?').bind(userId),
    env.DB.prepare(
      'INSERT INTO audit_log(actor_user_id,action,target_type,target_id,details_json,created_at) VALUES(?,?,?,?,?,?)'
    ).bind(actorId || null, 'MEMBER_ONBOARDING_ROLLBACK', 'user', userId, JSON.stringify({ reason }), ts)
  ]);
}

export async function onboardMember(core, request, env, executionContext) {
  const meResponse = await core.fetch(requestFor(request, '/api/me'), env, executionContext);
  const me = await responseJson(meResponse);
  if (!meResponse.ok) return json({ error: me?.error || `HTTP_${meResponse.status}` }, meResponse.status);
  if (!me?.permissions?.can_admin_members || !['R4', 'R5'].includes(String(me?.membership?.rank || ''))) {
    return json({ error: 'FORBIDDEN' }, 403);
  }

  let body;
  try { body = await request.json(); } catch (_) { return json({ error: 'INVALID_JSON' }, 400); }
  const playerName = String(body?.player_name || '').trim();
  const rank = String(body?.rank || '').trim().toUpperCase();
  const officerTitle = body?.officer_title == null ? null : String(body.officer_title).trim().toUpperCase();
  if (!playerName || playerName.length > 40) return json({ error: 'INVALID_PLAYER_NAME' }, 400);
  if (!['R1', 'R2', 'R3', 'R4'].includes(rank)) return json({ error: 'INVALID_RANK' }, 400);

  const membersResponse = await core.fetch(requestFor(request, '/api/admin/members'), env, executionContext);
  const membersData = await responseJson(membersResponse);
  if (!membersResponse.ok) return json({ error: membersData?.error || `HTTP_${membersResponse.status}` }, membersResponse.status);
  const duplicate = (membersData?.members || []).find((member) =>
    sameName(member?.player_name, playerName) || sameName(member?.display_name, playerName)
  );
  if (duplicate) return json({ error: 'PLAYER_ALREADY_EXISTS' }, 409);

  let portal = null;
  let code = null;
  for (let attempt = 0; attempt < 10; attempt += 1) {
    code = randomCode();
    const createResponse = await core.fetch(requestFor(request, '/api/admin/members', 'POST', {
      player_name: playerName,
      rank,
      officer_title: officerTitle,
      code
    }), env, executionContext);
    const createData = await responseJson(createResponse);
    if (createResponse.ok) {
      portal = createData;
      break;
    }
    if (createResponse.status === 409 && /CODE|EXISTS/i.test(String(createData?.error || ''))) continue;
    return json({ error: createData?.error || `HTTP_${createResponse.status}` }, createResponse.status);
  }
  if (!portal?.id || !code) return json({ error: 'UNABLE_TO_GENERATE_MEMBER_ACCESS' }, 409);

  const token = bearerToken(request);
  if (!token) {
    await rollbackPortalUser(env, me?.user?.id, portal.id, 'PORTAL_TOKEN_MISSING');
    return json({ error: 'UNAUTHORIZED' }, 401);
  }

  let trainResponse;
  let trainData;
  try {
    trainResponse = await fetch(`${TRAIN_API}/api/admin/members`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-WfGg-Portal-Token': token,
        'Cache-Control': 'no-store'
      },
      body: JSON.stringify({ pseudo: playerName, rank, active: true })
    });
    trainData = await responseJson(trainResponse);
  } catch (error) {
    await rollbackPortalUser(env, me?.user?.id, portal.id, `TRAIN_NETWORK:${String(error?.message || error)}`);
    return json({ error: 'TRAIN_ONBOARDING_UNAVAILABLE' }, 502);
  }

  if (!trainResponse.ok) {
    await rollbackPortalUser(env, me?.user?.id, portal.id, `TRAIN_HTTP_${trainResponse.status}:${String(trainData?.error || '')}`);
    return json({
      error: 'TRAIN_ONBOARDING_FAILED',
      train_error: trainData?.error || `HTTP_${trainResponse.status}`
    }, trainResponse.status >= 500 ? 502 : 409);
  }

  return json({
    ok: true,
    id: portal.id,
    player_name: playerName,
    rank,
    code,
    train: {
      id: trainData?.id || null,
      effectiveFrom: trainData?.effectiveFrom || null,
      integrations: Array.isArray(trainData?.integrations) ? trainData.integrations : []
    }
  }, 201);
}
