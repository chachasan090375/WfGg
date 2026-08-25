from pathlib import Path

path = Path('frontend/_worker.js')
source = path.read_text(encoding='utf-8')

old_signature = 'async function routeTrain(request) {'
new_signature = 'async function routeTrain(request, env) {'
if old_signature not in source:
    raise SystemExit('routeTrain signature not found')
source = source.replace(old_signature, new_signature, 1)

old_body = """  const suffix = url.pathname.slice(route.prefix.length) || '/';
  return proxyRoute(request, route, suffix, { routeName: 'train' });
}"""

new_body = """  const suffix = url.pathname.slice(route.prefix.length) || '/';

  /* WFGG_TRAIN_NATIVE_APP_V15_SHADOW
     Première étape de consolidation : sur la branche native v15, app.js est
     servi depuis une capture vérifiée du bridge v14 réellement déployé.
     Le fallback proxy reste actif si l'asset est absent, afin de ne jamais
     casser Train pendant la migration progressive.
  */
  if (suffix === '/app.js') {
    const assetUrl = new URL(request.url);
    assetUrl.pathname = '/train-native/app.v14.live.js';
    assetUrl.search = '';

    const assetRequest = new Request(assetUrl.toString(), {
      method: 'GET',
      headers: request.headers
    });
    const assetResponse = await env.ASSETS.fetch(assetRequest);

    if (assetResponse.ok) {
      const headers = new Headers(assetResponse.headers);
      headers.set('Cache-Control', 'no-store');
      headers.set('X-WfGg-Train-Frontend', 'native-v15-shadow');
      return new Response(assetResponse.body, {
        status: assetResponse.status,
        statusText: assetResponse.statusText,
        headers
      });
    }
  }

  return proxyRoute(request, route, suffix, { routeName: 'train' });
}"""

if old_body not in source:
    raise SystemExit('routeTrain body not found')
source = source.replace(old_body, new_body, 1)

old_call = '        return await routeTrain(request);'
new_call = '        return await routeTrain(request, env);'
if old_call not in source:
    raise SystemExit('routeTrain call not found')
source = source.replace(old_call, new_call, 1)

path.write_text(source, encoding='utf-8')
print('WFGG_TRAIN_NATIVE_APP_V15_SHADOW=PATCHED')
