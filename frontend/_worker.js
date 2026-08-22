const UPSTREAMS = {
  guides: {
    prefix: '/guides',
    origin: 'https://wfgg-guides.pages.dev'
  },
  train: {
    prefix: '/train',
    origin: 'https://wfgg-train-app.pages.dev'
  }
};

const SIMULATOR_FILES = {
  fr: 'simulateur.html',
  it: 'simulatore.html',
  en: 'simulator.html',
  es: 'simulador.html'
};

const SUPPORTED_LANGS = new Set(['fr', 'it', 'en', 'es']);

function safeLang(value) {
  const lang = String(value || '').toLowerCase().split('-')[0];
  return SUPPORTED_LANGS.has(lang) ? lang : 'fr';
}

function redirectSlash(request, pathname) {
  const url = new URL(request.url);
  url.pathname = pathname;
  return Response.redirect(url.toString(), 308);
}

function upstreamRequest(request, targetUrl) {
  return new Request(targetUrl.toString(), {
    method: request.method,
    headers: request.headers,
    body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
    redirect: 'manual'
  });
}

function rewriteLocation(location, route, requestUrl) {
  if (!location) return location;

  const upstreamOrigin = route.origin;
  const portalOrigin = requestUrl.origin;

  try {
    const absolute = new URL(location, upstreamOrigin);

    if (absolute.origin === upstreamOrigin) {
      return `${portalOrigin}${route.prefix}${absolute.pathname}${absolute.search}${absolute.hash}`;
    }
  } catch {}

  return location;
}

class RootAttributeRewriter {
  constructor(prefix, upstreamOrigin) {
    this.prefix = prefix;
    this.upstreamOrigin = upstreamOrigin;
  }

  element(element) {
    for (const attr of ['href', 'src', 'action', 'poster']) {
      const value = element.getAttribute(attr);
      if (!value) continue;

      if (value.startsWith('/') && !value.startsWith('//')) {
        element.setAttribute(attr, `${this.prefix}${value}`);
        continue;
      }

      if (value.startsWith(this.upstreamOrigin)) {
        const u = new URL(value);
        element.setAttribute(attr, `${this.prefix}${u.pathname}${u.search}${u.hash}`);
      }
    }
  }
}

class PortalLegacyLinkRewriter {
  element(element) {
    const href = element.getAttribute('href');
    if (!href) return;

    if (/^https:\/\/wfgg-guides\.pages\.dev/i.test(href)) {
      const u = new URL(href);
      element.setAttribute('href', `/guides${u.pathname}${u.search}${u.hash}`);
    } else if (/^https:\/\/wfgg-train-app\.pages\.dev/i.test(href)) {
      const u = new URL(href);
      element.setAttribute('href', `/train${u.pathname}${u.search}${u.hash}`);
    }
  }
}

async function proxyRoute(request, route, upstreamPath, options = {}) {
  const incoming = new URL(request.url);
  const target = new URL(route.origin);

  target.pathname = upstreamPath;
  target.search = incoming.search;

  const upstream = await fetch(upstreamRequest(request, target));
  const headers = new Headers(upstream.headers);

  const location = headers.get('Location');
  if (location) {
    headers.set('Location', rewriteLocation(location, route, incoming));
  }

  headers.set('X-WfGg-Route', options.routeName || route.prefix.slice(1));

  let response = new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers
  });

  const contentType = headers.get('Content-Type') || '';
  if (!contentType.toLowerCase().includes('text/html')) {
    return response;
  }

  let rewriter = new HTMLRewriter()
    .on('[href], [src], [action], [poster]',
      new RootAttributeRewriter(route.prefix, route.origin))
    .on('a[href]', new PortalLegacyLinkRewriter());

  if (options.baseHref) {
    const baseHref = options.baseHref;
    rewriter = rewriter.on('head', {
      element(element) {
        element.prepend(`<base href="${baseHref}">`, { html: true });
      }
    });
  }

  return rewriter.transform(response);
}

async function routeGuides(request) {
  const url = new URL(request.url);
  const route = UPSTREAMS.guides;

  if (url.pathname === '/guides') {
    return redirectSlash(request, '/guides/');
  }

  const suffix = url.pathname.slice(route.prefix.length) || '/';
  return proxyRoute(request, route, suffix, { routeName: 'guides' });
}

async function routeTrain(request) {
  const url = new URL(request.url);
  const route = UPSTREAMS.train;

  if (url.pathname === '/train') {
    return redirectSlash(request, '/train/');
  }

  const suffix = url.pathname.slice(route.prefix.length) || '/';
  return proxyRoute(request, route, suffix, { routeName: 'train' });
}

async function routeSimulator(request) {
  const url = new URL(request.url);

  if (url.pathname === '/simulateur') {
    return redirectSlash(request, '/simulateur/');
  }

  if (url.pathname !== '/simulateur/') {
    return new Response('Not found', { status: 404 });
  }

  const lang = safeLang(url.searchParams.get('lang'));
  const filename = SIMULATOR_FILES[lang];
  const upstreamPath = `/interseason/${lang}/${filename}`;

  return proxyRoute(
    request,
    UPSTREAMS.guides,
    upstreamPath,
    {
      routeName: 'simulateur',
      baseHref: `/guides/interseason/${lang}/`
    }
  );
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    try {
      if (url.pathname === '/guides' || url.pathname.startsWith('/guides/')) {
        return await routeGuides(request);
      }

      if (url.pathname === '/train' || url.pathname.startsWith('/train/')) {
        return await routeTrain(request);
      }

      if (url.pathname === '/simulateur' || url.pathname.startsWith('/simulateur/')) {
        return await routeSimulator(request);
      }

      return env.ASSETS.fetch(request);
    } catch (error) {
      console.error('WFGG_UNIFIED_ROUTE_ERROR', url.pathname, error);
      return new Response('WfGg route temporarily unavailable', {
        status: 502,
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-store'
        }
      });
    }
  }
};
