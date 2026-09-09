// WFGG_LASTWAR_DO_COMPAT_V1
// Compatibility export only.
// The experimental Last War authentication remains LAB-only and is not re-enabled here.
// This class intentionally performs no writes so existing Durable Object storage is preserved
// until the LAB architecture is intentionally resumed or migrated.

export class LastWarUserContainer {
  constructor(state, env) {
    this.state = state;
    this.env = env;
  }

  async fetch() {
    return new Response(JSON.stringify({
      ok: false,
      error: 'LASTWAR_LAB_FROZEN',
      detail: 'Compatibility Durable Object preserved; Last War LAB is not active.'
    }), {
      status: 410,
      headers: {
        'content-type': 'application/json; charset=utf-8',
        'cache-control': 'no-store'
      }
    });
  }

  async alarm() {
    // Intentionally no-op: preserve storage without reviving experimental LAB behavior.
  }
}
