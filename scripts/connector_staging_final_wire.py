from pathlib import Path

STAGING_ORIGIN = "https://wfgg-api-staging.chachasan090375.workers.dev"
OLD_ORIGIN = "https://connector-readonly-v1-wfgg-api.chachasan090375.workers.dev"


def patch_pages_proxy() -> None:
    path = Path("frontend/_worker.js")
    text = path.read_text(encoding="utf-8")

    if STAGING_ORIGIN in text:
        print("frontend/_worker.js: staging origin already wired")
        return

    count = text.count(OLD_ORIGIN)
    if count != 1:
        raise SystemExit(f"frontend/_worker.js: expected one old portalApi origin, found {count}")

    path.write_text(text.replace(OLD_ORIGIN, STAGING_ORIGIN, 1), encoding="utf-8")
    print("frontend/_worker.js: portalApi wired to wfgg-api-staging")


def patch_broker_health() -> None:
    path = Path("worker/src/lastwar-identity.js")
    text = path.read_text(encoding="utf-8")

    health_marker = "url.pathname === '/api/lastwar/health'"
    if health_marker in text:
        print("worker/src/lastwar-identity.js: broker health route already present")
        return

    old = """export async function routeLastWarIdentity(request, env, url, deps) {
  if (!url.pathname.startsWith('/api/lastwar/identity/')) return null;

  const { sessionContext, json, fail, audit, now, sha256Text } = deps;
"""

    new = """export async function routeLastWarIdentity(request, env, url, deps) {
  const { sessionContext, json, fail, audit, now, sha256Text } = deps;

  if (url.pathname === '/api/lastwar/health') {
    if (request.method !== 'GET') return json({ error: 'METHOD_NOT_ALLOWED' }, 405);
    if (!env.LASTWAR_USER) return json({ ok: false, error: 'LASTWAR_BROKER_NOT_CONFIGURED' }, 503);

    try {
      const instance = getContainer(env.LASTWAR_USER, 'wfgg-lastwar-health-v1');
      const response = await instance.fetch(new Request('https://container.internal/ping', {
        method: 'GET',
        headers: { 'Cache-Control': 'no-store' }
      }));

      let data = {};
      try { data = await response.json(); } catch (_) {}

      if (!response.ok || data?.ok !== true || data?.service !== 'wfgg-lastwar-go-broker') {
        return json({ ok: false, error: 'LASTWAR_BROKER_HEALTH_FAILED' }, 503);
      }

      return json({
        ok: true,
        service: 'wfgg-lastwar-connector',
        broker: 'wfgg-lastwar-go-broker',
        mode: data.mode === 'read-only' ? 'read-only' : 'unknown',
        revision: BROKER_REVISION.slice(0, 8),
        container: true
      });
    } catch (_) {
      return json({ ok: false, error: 'LASTWAR_BROKER_UNAVAILABLE' }, 503);
    }
  }

  if (!url.pathname.startsWith('/api/lastwar/identity/')) return null;
"""

    count = text.count(old)
    if count != 1:
        raise SystemExit(f"worker/src/lastwar-identity.js: expected one route marker, found {count}")

    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("worker/src/lastwar-identity.js: runtime broker health route added")


if __name__ == "__main__":
    patch_pages_proxy()
    patch_broker_health()
