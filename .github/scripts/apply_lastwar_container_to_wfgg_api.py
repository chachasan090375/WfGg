from pathlib import Path

ROOT = Path('.')


def replace_once(path: Path, old: str, new: str):
    text = path.read_text(encoding='utf-8')
    if new in text:
        return False
    if text.count(old) != 1:
        raise SystemExit(f'{path}: expected one anchor, found {text.count(old)}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')
    return True


# 1) Export the Cloudflare Container class from the worker entrypoint and import the two routers.
index = ROOT / 'worker/src/index.js'
replace_once(
    index,
    "const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8' };",
    "import { routeLastWarConnector } from './lastwar-connector.js';\n"
    "import { routeLastWarIdentity, routeLastWarCloudSync } from './lastwar-identity.js';\n"
    "export { LastWarUserContainer } from './lastwar-container.js';\n\n"
    "const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8' };"
)

route_anchor = """      if (url.pathname === '/api/health' && request.method === 'GET') {
        response = json({ ok: true, service: 'wfgg-api', version: '0.4.2', admin_gate: 'R4_R5_ONLY' });
"""
route_replacement = """      const lastWarDeps = {
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
"""
replace_once(index, route_anchor, route_replacement)

# 2) The portal calls its own /api proxy. Never call a detached Last War Worker from the browser.
connect = ROOT / 'frontend/lastwar-connect-v2.js'
replace_once(
    connect,
    "const CONNECTOR_API=(window.WFGG_PORTAL_CONFIG?.LASTWAR_CONNECTOR_API||'https://wfgg-lastwar-connector.workers.dev').replace(/\\/+$/,'');",
    "const CONNECTOR_API=(window.WFGG_PORTAL_CONFIG?.LASTWAR_CONNECTOR_API||'').replace(/\\/+$/,'');"
)

replace_once(
    connect,
    "async function refresh(){setBusy(true,t('refresh'));try{await loadStatus();setBusy(false);render()}catch{setBusy(false);setMessage(t('service'),'error')}}",
    "async function refresh(){setBusy(true,t('refresh'));try{await connector('/api/lastwar/cloud-sync',{method:'POST',body:'{}'});await loadStatus();setBusy(false);render()}catch(e){setBusy(false);setMessage(friendlyError(e),'error')}}"
)

# 3) On this preview branch, same-origin /api must target the branch worker, not production.
page_worker = ROOT / 'frontend/_worker.js'
replace_once(
    page_worker,
    "origin: 'https://wfgg-api.chachasan090375.workers.dev'",
    "origin: 'https://connector-readonly-v1-wfgg-api.chachasan090375.workers.dev'"
)

# 4) Cache-bust the mobile script so Android Chrome cannot keep the detached-worker version.
html = ROOT / 'frontend/index.html'
replace_once(
    html,
    '<script src="lastwar-connect-v2.js?v=012-uid-broker"></script>',
    '<script src="lastwar-connect-v2.js?v=013-container-direct"></script>'
)

print('WfGg API Last War container integration applied')
