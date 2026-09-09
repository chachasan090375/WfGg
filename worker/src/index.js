import core from './core.js';

const SENTINEL_VERSION = 'sentinel-owner-v1';
const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' };
const TRAIN_API = 'https://wfgg-train.chachasan090375.workers.dev';

export default {
  async fetch(request, env, executionContext) {
    const url = new URL(request.url);
    if (url.pathname === '/api/sentinel/run' && request.method === 'GET') {
      return sentinelRun(request, env, executionContext);
    }
    const response = await core.fetch(request, env, executionContext);
    if (response.ok && shouldSyncTrainRoster(url.pathname, request.method)) {
      const task = notifyTrainRosterSync(request).catch((error) => {
        console.warn('WFGG_PORTAL_ROSTER_SYNC_NOTIFY', String(error?.message || error));
      });
      if (executionContext?.waitUntil) executionContext.waitUntil(task);
    }
    return response;
  }
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

function requestWithPath(request, pathname) {
  const url = new URL(request.url);
  url.pathname = pathname;
  url.search = '';
  return new Request(url.toString(), {
    method: 'GET',
    headers: request.headers,
    redirect: 'manual'
  });
}

async function coreJson(request, env, pathname) {
  const response = await core.fetch(requestWithPath(request, pathname), env);
  let data = null;
  try { data = await response.clone().json(); } catch (_) {}
  return { response, data };
}

function bearerToken(request) {
  const auth = request.headers.get('Authorization') || '';
  return auth.startsWith('Bearer ') ? auth.slice(7).trim() : '';
}


function shouldSyncTrainRoster(pathname, method) {
  if (pathname === '/api/admin/members' && (method === 'GET' || method === 'POST')) return true;
  if (/^\/api\/admin\/members\/[^/]+$/.test(pathname) && (method === 'PATCH' || method === 'DELETE')) return true;
  if (pathname === '/api/admin/leadership/transfer' && method === 'POST') return true;
  return false;
}

async function notifyTrainRosterSync(request) {
  const token = bearerToken(request);
  if (!token) return null;
  const response = await fetch(`${TRAIN_API}/api/portal-roster/sync`, {
    method: 'POST',
    headers: {
      'X-WfGg-Portal-Token': token,
      'Cache-Control': 'no-store'
    },
    redirect: 'manual'
  });
  if (!response.ok) {
    let detail = '';
    try { detail = await response.text(); } catch (_) {}
    throw new Error(`TRAIN_ROSTER_SYNC_${response.status}${detail ? ':' + detail.slice(0, 180) : ''}`);
  }
  return response;
}

function severityRank(level) {
  return ({ ok: 0, info: 1, warning: 2, error: 3 })[level] ?? 3;
}

function check(id, area, level, title, expected, observed, detail = '', probableCause = '') {
  return { id, area, level, title, expected, observed, detail, probableCause };
}

async function publicProbe(url, { headers = {}, text = false } = {}) {
  const started = Date.now();
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { 'Cache-Control': 'no-cache', ...headers },
      redirect: 'manual'
    });
    const body = text ? await response.text() : '';
    return {
      ok: response.ok,
      status: response.status,
      elapsedMs: Date.now() - started,
      body,
      headers: {
        contentType: response.headers.get('content-type') || '',
        route: response.headers.get('x-wfgg-route') || '',
        trainFrontend: response.headers.get('x-wfgg-train-frontend') || '',
        portalBridge: response.headers.get('x-wfgg-portal-bridge') || ''
      }
    };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      elapsedMs: Date.now() - started,
      body: '',
      error: String(error?.message || error)
    };
  }
}

function exactArray(value, expected) {
  if (!Array.isArray(value) || value.length !== expected.length) return false;
  return expected.every((item, index) => String(value[index]) === item);
}

function analyseSnapshot(snapshot, ownerId) {
  const checks = [];
  const roster = Array.isArray(snapshot?.roster) ? snapshot.roster : [];
  const schedule = Array.isArray(snapshot?.schedule) ? snapshot.schedule : [];
  const state = snapshot?.state && typeof snapshot.state === 'object' ? snapshot.state : {};
  const byId = new Map(roster.map((row) => [String(row?.id || ''), row]));

  checks.push(check(
    'snapshot-owner-roster',
    'Session & données',
    ownerId && byId.has(String(ownerId)) ? 'ok' : 'error',
    'Utilisateur courant présent dans le roster Train',
    'Le joueur OWNER doit être présent dans le snapshot',
    ownerId && byId.has(String(ownerId)) ? 'Présent' : 'Absent',
    '',
    ownerId && byId.has(String(ownerId)) ? '' : 'Snapshot incomplet ou liaison Portail → Train incohérente.'
  ));

  checks.push(check(
    'snapshot-schedule',
    'Planning',
    schedule.length ? 'ok' : 'error',
    'Planning serveur autoritatif disponible',
    'Un tableau schedule non vide',
    `${schedule.length} affectation(s) reçue(s)`,
    '',
    schedule.length ? '' : 'Le frontend ne peut pas s’appuyer sur le planning serveur.'
  ));

  const rotationRanks = state?.settings?.rotationRanks || {};
  const rulesKnown = rotationRanks && typeof rotationRanks === 'object';
  const rulesOk = rulesKnown
    && exactArray(rotationRanks.officer, ['R5', 'R4'])
    && exactArray(rotationRanks.r3driver, ['R3'])
    && exactArray(rotationRanks.vip, ['R3']);
  checks.push(check(
    'rotation-rank-contract',
    'Règles métier',
    !rulesKnown ? 'warning' : (rulesOk ? 'ok' : 'error'),
    'Contrat des trois cycles',
    'Conducteur A = R5/R4 · Conducteur B = R3 · VIP automatique = R3',
    rulesKnown ? JSON.stringify(rotationRanks) : 'Paramètres rotationRanks absents du snapshot',
    '',
    !rulesKnown ? 'Le snapshot ne permet pas de prouver le contrat.' : (rulesOk ? '' : 'Les rangs configurés divergent des règles métier figées.')
  ));

  const duplicateRoles = [];
  const orphanDrivers = [];
  const orphanVips = [];
  const invalidDriverRanks = [];
  let nonR3VipCount = 0;

  for (const row of schedule.slice(0, 240)) {
    const date = String(row?.date || '');
    const driverId = row?.driverId == null ? '' : String(row.driverId);
    const vipId = row?.vipId == null ? '' : String(row.vipId);
    if (driverId && vipId && driverId === vipId) duplicateRoles.push(date || '?');

    if (driverId) {
      const driver = byId.get(driverId);
      if (!driver) orphanDrivers.push(`${date}:${driverId}`);
      else if (!['R3', 'R4', 'R5'].includes(String(driver.rank || ''))) {
        invalidDriverRanks.push(`${date}:${driver.pseudo || driver.display_name || driverId}(${driver.rank || '?'})`);
      }
    }

    if (vipId) {
      const vip = byId.get(vipId);
      if (!vip) orphanVips.push(`${date}:${vipId}`);
      else if (String(vip.rank || '') !== 'R3') nonR3VipCount += 1;
    }
  }

  checks.push(check(
    'schedule-no-double-role',
    'Planning',
    duplicateRoles.length ? 'error' : 'ok',
    'Aucun Conducteur ne doit être VIP le même jour',
    '0 conflit',
    duplicateRoles.length ? duplicateRoles.slice(0, 8).join(', ') : '0 conflit',
    duplicateRoles.length ? 'Dates concernées ci-dessus.' : '',
    duplicateRoles.length ? 'Une affectation ou un override a créé deux rôles pour le même joueur.' : ''
  ));

  checks.push(check(
    'schedule-roster-references',
    'Planning',
    orphanDrivers.length || orphanVips.length ? 'error' : 'ok',
    'Toutes les affectations doivent référencer un joueur connu',
    '0 référence orpheline',
    `${orphanDrivers.length} conducteur(s) orphelin(s), ${orphanVips.length} VIP orphelin(s)`,
    [...orphanDrivers, ...orphanVips].slice(0, 8).join(' · '),
    orphanDrivers.length || orphanVips.length ? 'Un départ, une désactivation ou un ancien planning a laissé un identifiant non résolu.' : ''
  ));

  checks.push(check(
    'driver-rank-eligibility',
    'Règles métier',
    invalidDriverRanks.length ? 'error' : 'ok',
    'Éligibilité Conducteur',
    'Conducteur uniquement R3/R4/R5',
    invalidDriverRanks.length ? invalidDriverRanks.slice(0, 8).join(' · ') : 'Conforme',
    '',
    invalidDriverRanks.length ? 'Une affectation Conducteur se trouve hors des pools A/B.' : ''
  ));

  checks.push(check(
    'vip-exceptional-info',
    'Règles métier',
    nonR3VipCount ? 'info' : 'ok',
    'VIP R1/R2 hors cycle',
    'VIP automatique R3 ; R1/R2 uniquement en nomination exceptionnelle',
    nonR3VipCount ? `${nonR3VipCount} nomination(s) VIP hors R3 détectée(s)` : 'Aucune nomination hors R3 dans la fenêtre contrôlée',
    nonR3VipCount ? 'Présence admise : Sentinel ne la considère pas comme une erreur de cycle.' : '',
    ''
  ));

  const integrations = Array.isArray(state.rotationIntegrationStatus) ? state.rotationIntegrationStatus : [];
  const malformed = integrations.filter((entry) => {
    const pool = String(entry?.poolKey || '');
    const target = Number(entry?.targetCount);
    const completed = Number(entry?.completedCount);
    const remaining = Number(entry?.remainingCount);
    return !['officer', 'r3driver', 'vip'].includes(pool)
      || !Number.isFinite(target) || target < 0 || target > 2
      || !Number.isFinite(completed) || completed < 0
      || !Number.isFinite(remaining) || remaining < 0
      || completed + remaining < target;
  });
  checks.push(check(
    'integration-markers',
    'Intégrations',
    malformed.length ? 'error' : 'ok',
    'Marqueurs nouveaux arrivants / promotions / rétrogradations',
    'Compteurs structurés, pool connu, cible 0 à 2',
    malformed.length ? `${malformed.length} marqueur(s) incohérent(s)` : `${integrations.length} marqueur(s), structure conforme`,
    malformed.slice(0, 4).map((x) => JSON.stringify(x)).join(' · '),
    malformed.length ? 'Un quota d’intégration est mal formé ou ne correspond pas au modèle prévu.' : ''
  ));

  return checks;
}

async function sentinelRun(request, env) {
  const startedAt = new Date().toISOString();
  const meCall = await coreJson(request, env, '/api/me');
  if (!meCall.response.ok) {
    return json({ ok: false, error: meCall.data?.error || `HTTP_${meCall.response.status}` }, meCall.response.status);
  }
  if (meCall.data?.system?.role !== 'OWNER') {
    return json({ ok: false, error: 'SENTINEL_OWNER_ONLY' }, 403);
  }

  const ownerId = String(meCall.data?.user?.id || '');
  const checks = [check(
    'owner-access',
    'Sécurité',
    'ok',
    'Accès Sentinel',
    'Rôle système OWNER',
    'OWNER validé côté serveur',
    'Le panneau est volontairement inaccessible aux R4/R5 non-OWNER.'
  )];

  const contextCall = await coreJson(request, env, '/api/train/context');
  const contextRoster = Array.isArray(contextCall.data?.roster) ? contextCall.data.roster : [];
  checks.push(check(
    'portal-roster-context',
    'Portail',
    contextCall.response.ok && contextRoster.some((x) => String(x?.id || '') === ownerId) ? 'ok' : 'error',
    'Contexte Portail / roster',
    'HTTP 200 et OWNER présent',
    `HTTP ${contextCall.response.status} · ${contextRoster.length} joueur(s)`,
    '',
    contextCall.response.ok ? 'Le roster Portail ne contient pas le compte OWNER.' : 'La session ou la base Portail ne répond pas correctement.'
  ));

  const nonce = Date.now();
  const [portalRoot, trainPage, trainRuntime, trainHealth, pushSw] = await Promise.all([
    publicProbe(`https://wfgg.pages.dev/?sentinel=${nonce}`),
    publicProbe(`https://wfgg.pages.dev/train/?sentinel=${nonce}`, { text: true }),
    publicProbe(`https://wfgg.pages.dev/train/app.js?sentinel=${nonce}`, { text: true }),
    publicProbe(`https://wfgg-train.chachasan090375.workers.dev/api/health?sentinel=${nonce}`, { text: true }),
    publicProbe(`https://wfgg.pages.dev/train/wfgg-push-sw.js?sentinel=${nonce}`, { text: true })
  ]);

  checks.push(check(
    'portal-public', 'Infrastructure', portalRoot.status === 200 ? 'ok' : 'error',
    'Portail public', 'HTTP 200', `HTTP ${portalRoot.status || 0} · ${portalRoot.elapsedMs} ms`,
    '', portalRoot.status === 200 ? '' : 'Cloudflare Pages / Worker du Portail indisponible ou en erreur.'
  ));

  checks.push(check(
    'train-page-public', 'Infrastructure', trainPage.status === 200 ? 'ok' : 'error',
    'Train intégré', 'HTTP 200', `HTTP ${trainPage.status || 0} · route ${trainPage.headers?.route || '—'} · ${trainPage.elapsedMs} ms`,
    '', trainPage.status === 200 ? '' : 'Le proxy Portail → page Train est indisponible.'
  ));

  checks.push(check(
    'train-api-health', 'Infrastructure', trainHealth.status === 200 ? 'ok' : 'error',
    'Worker Train', 'HTTP 200', `HTTP ${trainHealth.status || 0} · ${trainHealth.elapsedMs} ms`,
    trainHealth.body.slice(0, 220), trainHealth.status === 200 ? '' : 'Le Worker Train lui-même ne répond pas correctement.'
  ));

  const runtimeMarkers = {
    integration: trainRuntime.body.includes('WFGG_ROSTER_INTEGRATION_UI_V1') || trainRuntime.body.includes('rotationIntegrationStatus'),
    serverSchedule: trainRuntime.body.includes('__serverSchedule'),
    vipR3: trainRuntime.body.includes("vip: ['R3']")
  };
  const runtimeOk = trainRuntime.status === 200 && Object.values(runtimeMarkers).every(Boolean);
  checks.push(check(
    'train-runtime-contract', 'Production', runtimeOk ? 'ok' : 'error',
    'Runtime Train réellement servi',
    'HTTP 200 + planning serveur + intégrations + VIP R3',
    `HTTP ${trainRuntime.status || 0} · frontend ${trainRuntime.headers?.trainFrontend || '—'} · marqueurs ${JSON.stringify(runtimeMarkers)}`,
    '', runtimeOk ? '' : 'La production publique ne correspond pas au contrat attendu, même si les sources GitHub sont correctes.'
  ));

  const swMarkers = pushSw.body.includes('showNotification') && pushSw.body.includes("addEventListener('push'") || pushSw.body.includes('addEventListener("push"');
  checks.push(check(
    'push-service-worker', 'Notifications', pushSw.status === 200 && swMarkers ? 'ok' : 'error',
    'Service Worker de notifications',
    'HTTP 200 + gestion push + showNotification',
    `HTTP ${pushSw.status || 0} · push=${pushSw.body.includes('push')} · showNotification=${pushSw.body.includes('showNotification')}`,
    '', pushSw.status === 200 && swMarkers ? '' : 'Le fichier de Service Worker servi au téléphone est absent ou incomplet.'
  ));

  const token = bearerToken(request);
  let snapshotProbe = { ok: false, status: 0, data: null, elapsedMs: 0, error: 'NO_TOKEN' };
  if (token) {
    const snapshotStarted = Date.now();
    try {
      const response = await fetch(`https://wfgg.pages.dev/api/snapshot?sentinel=${nonce}`, {
        method: 'GET',
        headers: {
          'X-WfGg-Portal-Token': token,
          'Accept': 'application/json',
          'Cache-Control': 'no-cache'
        },
        redirect: 'manual'
      });
      let data = null;
      try { data = await response.clone().json(); } catch (_) {}
      snapshotProbe = {
        ok: response.ok,
        status: response.status,
        data,
        elapsedMs: Date.now() - snapshotStarted,
        route: response.headers.get('x-wfgg-route') || '',
        bridge: response.headers.get('x-wfgg-portal-bridge') || '',
        error: data?.error || ''
      };
    } catch (error) {
      snapshotProbe = { ok: false, status: 0, data: null, elapsedMs: Date.now() - snapshotStarted, error: String(error?.message || error) };
    }
  }

  checks.push(check(
    'portal-train-snapshot-bridge', 'Liaisons', snapshotProbe.ok ? 'ok' : 'error',
    'Session Portail → snapshot Train',
    'HTTP 200 avec la session OWNER',
    `HTTP ${snapshotProbe.status || 0} · route ${snapshotProbe.route || '—'} · bridge ${snapshotProbe.bridge || '—'} · ${snapshotProbe.elapsedMs} ms`,
    snapshotProbe.error ? `Erreur : ${snapshotProbe.error}` : '',
    snapshotProbe.ok ? '' : 'Défaillance de liaison Portail → Train. C’est le contrôle prioritaire lorsqu’un écran affiche HTTP_503.'
  ));

  if (snapshotProbe.ok && snapshotProbe.data) {
    checks.push(...analyseSnapshot(snapshotProbe.data, ownerId));
  }

  const counts = { ok: 0, info: 0, warning: 0, error: 0 };
  for (const item of checks) counts[item.level] = (counts[item.level] || 0) + 1;
  const worst = checks.reduce((acc, item) => severityRank(item.level) > severityRank(acc) ? item.level : acc, 'ok');

  return json({
    ok: worst !== 'error',
    sentinel: SENTINEL_VERSION,
    mode: 'read-only',
    startedAt,
    finishedAt: new Date().toISOString(),
    owner: {
      id: ownerId,
      displayName: meCall.data?.user?.display_name || meCall.data?.user?.player_name || 'OWNER'
    },
    summary: { status: worst, counts, total: checks.length },
    checks,
    guarantees: {
      modifiesPlanning: false,
      modifiesRoster: false,
      modifiesRotations: false,
      automaticFixes: false
    }
  });
}
