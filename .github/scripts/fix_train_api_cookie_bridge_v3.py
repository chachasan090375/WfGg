from pathlib import Path

path = Path('frontend/_worker.js')
text = path.read_text(encoding='utf-8')

marker = '/* WFGG_PORTAL_TRAIN_SAME_ORIGIN_API_V2'
if marker not in text:
    raise SystemExit('missing Train same-origin bridge marker')

before, after = text.split(marker, 1)
after2 = after.replace("credentials:'omit'", "credentials:'same-origin'", 2)
if after2 == after:
    raise SystemExit('Train fetch credentials patch not applied')
text = before + marker + after2

old = """      if (url.pathname === '/api' || url.pathname.startsWith('/api/')) {
        const referer = request.headers.get('Referer') || '';
        const hasPortalTrainToken =
          request.headers.has('X-WfGg-Portal-Token');

        let fromTrainPage = false;

        try {
          const refUrl = new URL(referer);

          fromTrainPage =
            refUrl.origin === url.origin &&
            (
              refUrl.pathname === '/train' ||
              refUrl.pathname.startsWith('/train/')
            );
        } catch {}

        const apiRoute =
          (fromTrainPage || hasPortalTrainToken)
            ? UPSTREAMS.trainApi
            : UPSTREAMS.portalApi;

        return await proxyRoute(
          request,
          apiRoute,
          url.pathname,
          {
            routeName:
              apiRoute === UPSTREAMS.trainApi
                ? 'train-api'
                : 'portal-api'
          }
        );
      }
"""

new = """      if (url.pathname === '/api' || url.pathname.startsWith('/api/')) {
        const referer = request.headers.get('Referer') || '';
        const hasPortalTrainToken =
          request.headers.has('X-WfGg-Portal-Token');
        const cookiePortalTrainToken = portalSessionCookie(request);

        let fromTrainPage = false;

        try {
          const refUrl = new URL(referer);

          fromTrainPage =
            refUrl.origin === url.origin &&
            (
              refUrl.pathname === '/train' ||
              refUrl.pathname.startsWith('/train/')
            );
        } catch {}

        const apiRoute =
          (fromTrainPage || hasPortalTrainToken)
            ? UPSTREAMS.trainApi
            : UPSTREAMS.portalApi;

        /* WFGG_TRAIN_API_COOKIE_AUTH_V5
           Une page Train déjà autorisée par le cookie HttpOnly ne dépend plus
           du timing d'un script navigateur pour transmettre son identité au
           backend Train. Le Worker recopie le jeton du cookie vers l'en-tête
           interne X-WfGg-Portal-Token; le backend continue de le revalider
           auprès du Portail et reste l'autorité d'authentification. */
        let apiRequest = request;
        if (apiRoute === UPSTREAMS.trainApi && cookiePortalTrainToken) {
          const headers = new Headers(request.headers);
          headers.set('X-WfGg-Portal-Token', cookiePortalTrainToken);
          apiRequest = new Request(request, { headers });
        }

        return await proxyRoute(
          apiRequest,
          apiRoute,
          url.pathname,
          {
            routeName:
              apiRoute === UPSTREAMS.trainApi
                ? 'train-api'
                : 'portal-api'
          }
        );
      }
"""

if old not in text:
    raise SystemExit('API context block not found')
text = text.replace(old, new, 1)

if text.count('WFGG_TRAIN_API_COOKIE_AUTH_V5') != 1:
    raise SystemExit('unexpected cookie auth marker count')

path.write_text(text, encoding='utf-8')
print('WFGG_TRAIN_API_COOKIE_AUTH_V5=PATCHED')
