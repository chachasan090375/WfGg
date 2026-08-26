import base from './_worker_base.js';

const RESEARCH_PATH = '/__wfgg_research/datatable1295';
const VERSION_HOSTS = [
  'https://lastwar-serverlist-cf.lastwarapp.net',
  'https://lastwar-serverlist-us-aws-ali.lastwargame.com',
  'https://lastwar-serverlist-us-gcp-ali.lastwargame.com'
];

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Robots-Tag': 'noindex, nofollow'
    }
  });
}

async function probeVersionHost(origin, variant) {
  const endpoint = new URL('/gameservice/getlsu3dversion.php', origin);
  const params = {
    packageName: 'com.fun.lastwar.gp',
    platform: variant.platform || 'Android',
    appVersion: '1.0.359',
    gm: '0',
    server: variant.server || '',
    uid: '',
    deviceId: variant.deviceId || '',
    table_env: variant.table_env || '',
    buildId: '1864',
    returnJson: '1',
    unityVersion: '440'
  };
  for (const [k, v] of Object.entries(params)) endpoint.searchParams.set(k, v);

  try {
    const response = await fetch(endpoint.toString(), {
      method: 'GET',
      headers: {
        'Accept': 'application/json,text/plain,*/*',
        'User-Agent': 'WfGg-public-datatable-audit/1.0'
      },
      cf: { cacheTtl: 0, cacheEverything: false }
    });
    const text = await response.text();
    let data = null;
    try { data = JSON.parse(text); } catch {}

    if (!data || typeof data !== 'object') {
      return {
        origin,
        variant,
        status: response.status,
        json: false,
        bodyPreview: text.slice(0, 240)
      };
    }

    const safe = {
      origin,
      variant,
      status: response.status,
      keys: Object.keys(data).filter(k => !['resMsg', 'uid', 'deviceId', 'token', 'session'].includes(k)).sort()
    };
    for (const key of [
      'code', 'msg', 'updateType', 'hotUpdateMsg', 'table_version',
      'tableVersion', 'tableVersionInfo', 'lwfile2', 'downloadurl',
      'firstLaunchForceUpdateMsg', 'warmup'
    ]) {
      if (Object.prototype.hasOwnProperty.call(data, key)) safe[key] = data[key];
    }
    return safe;
  } catch (error) {
    return { origin, variant, error: String(error && error.message || error) };
  }
}

async function researchDataTable1295(request) {
  if (request.method !== 'GET') return json({ error: 'GET only' }, 405);

  const variants = [
    { id: 'anonymous', platform: 'Android', table_env: '' },
    { id: 'prod', platform: 'Android', table_env: 'prod' },
    { id: 'release', platform: 'Android', table_env: 'release' },
    { id: 'formal', platform: 'Android', table_env: 'formal' },
    { id: 'env-1295', platform: 'Android', table_env: '1295' },
    { id: 'dummy-device', platform: 'Android', table_env: '', deviceId: 'wfgg-public-research-1864' },
    { id: 'dummy-device-prod', platform: 'Android', table_env: 'prod', deviceId: 'wfgg-public-research-1864' },
    { id: 'platform-lower', platform: 'android', table_env: '' }
  ];

  const probes = [];
  for (const origin of VERSION_HOSTS) {
    for (const variant of variants) probes.push(await probeVersionHost(origin, variant));
  }

  const tableVersionHits = probes.filter(row => row.table_version || row.tableVersion || row.tableVersionInfo);
  const descriptors = [...new Set(probes.map(row => row.hotUpdateMsg).filter(Boolean))];

  return json({
    target: {
      packageName: 'com.fun.lastwar.gp',
      appVersion: '1.0.359',
      buildId: 1864,
      expectedDataTableDescriptor: 'DataTable,1295,294,1768181284'
    },
    tableVersionHits,
    descriptors,
    probes,
    note: 'Public bootstrap metadata only. resMsg/account/session identifiers are intentionally excluded.'
  });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === RESEARCH_PATH) return researchDataTable1295(request);
    return base.fetch(request, env, ctx);
  }
};
