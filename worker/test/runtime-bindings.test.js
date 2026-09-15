import { describe, expect, it } from 'vitest';
import { env, exports } from 'cloudflare:workers';

describe('wfgg-api runtime foundation', () => {
  it('exposes a working D1 binding', async () => {
    const row = await env.DB.prepare('SELECT 1 AS ok').first();
    expect(Number(row?.ok)).toBe(1);
  });

  it('exposes an isolated R2 binding', async () => {
    const key = '__wfgg_test_missing_object__';
    const object = await env.AVATARS.head(key);
    expect(object).toBeNull();
  });

  it('handles an unknown route without an internal server error', async () => {
    const response = await exports.default.fetch(
      'https://wfgg.test/__wfgg_test_unknown_route__'
    );
    expect(response.status).toBeGreaterThanOrEqual(400);
    expect(response.status).toBeLessThan(500);
  });
});
