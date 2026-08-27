import { Container } from '@cloudflare/containers';
import { env } from 'cloudflare:workers';

export class LastWarUserContainer extends Container {
  defaultPort = 8080;
  sleepAfter = '12m';
  enableInternet = true;
  envVars = {
    WFGG_UPSTREAM_REVISION: env.LASTWAR_BROKER_REVISION || ''
  };

  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === '/ping') return this.containerFetch(request);

    const sealedState = await this.ctx.storage.get('sealed_state');
    const headers = new Headers(request.headers);
    headers.set('X-WfGg-Container-Auth', '1');
    if (sealedState) headers.set('X-WfGg-Sealed-State', String(sealedState));

    const proxied = new Request(request.url, {
      method: request.method,
      headers,
      body: request.method === 'GET' || request.method === 'HEAD'
        ? undefined
        : await request.arrayBuffer()
    });

    const response = await this.containerFetch(proxied);
    const contentType = response.headers.get('Content-Type') || '';
    if (!contentType.includes('application/json')) return response;

    let data;
    try {
      data = await response.clone().json();
    } catch (_) {
      return response;
    }

    if (data && typeof data === 'object' && !Array.isArray(data)) {
      if (typeof data._wfgg_sealed_state === 'string' && data._wfgg_sealed_state.length <= 16_384) {
        await this.ctx.storage.put('sealed_state', data._wfgg_sealed_state);
      }
      for (const key of Object.keys(data)) {
        if (key.startsWith('_wfgg_')) delete data[key];
      }
    }

    const outHeaders = new Headers(response.headers);
    outHeaders.set('Content-Type', 'application/json; charset=utf-8');
    outHeaders.set('Cache-Control', 'no-store');
    outHeaders.set('X-Content-Type-Options', 'nosniff');
    return new Response(JSON.stringify(data), {
      status: response.status,
      headers: outHeaders
    });
  }
}
