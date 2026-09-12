#!/usr/bin/env python3
from pathlib import Path

p = Path('/tmp/wfgg-radar/src/worker.js')
s = p.read_text(encoding='utf-8')
marker = 'AUTO_CARTOGRAPHER_WORKER_V633'

if marker not in s:
    export_anchor = 'export default {\n'
    if s.count(export_anchor) != 1:
        raise SystemExit(f'AUTO_CARTOGRAPHER_V633_EXPORT_ANCHOR_EXPECTED_1_GOT_{s.count(export_anchor)}')

    helper = r'''// AUTO_CARTOGRAPHER_WORKER_V633
// Scheduled, credential-vault-backed observer. It never brute-forces server IDs:
// the VPS receives the same legitimate account credential already stored by Radar,
// performs one lightweight current-world probe, and maps 9 regions only after two
// consecutive confirmed world-context changes.
async function runAutoCartographerV633(env) {
  if (!env?.DB) return { status: 'skipped', reason: 'DB_UNAVAILABLE' };

  const users = await listUsers(env);
  const owners = users.filter(user => user?.role === ROLES.OWNER && Number(user?.active) === 1);
  if (!owners.length) return { status: 'skipped', reason: 'OWNER_UNAVAILABLE' };

  const results = [];
  for (const user of owners.slice(0, 2)) {
    const record = await getCredential(env, user.game_uid);
    if (!record) {
      results.push({ gameUid: String(user.game_uid), status: 'credential-missing' });
      continue;
    }

    const vaultKey = requireSecret(env.RADAR_TOKEN_VAULT_KEY, 'RADAR_TOKEN_VAULT_KEY');
    const token = await decryptGameToken(
      { ciphertext: record.ciphertext, iv: record.iv, keyVersion: record.key_version },
      vaultKey,
      user.game_uid
    );
    const transport = new RemoteLastWarTransport({
      baseUrl: env.RADAR_CONNECTOR_URL,
      sharedKey: env.RADAR_CONNECTOR_SHARED_KEY,
      timeoutMs: 70000
    });

    try {
      const tick = await transport.cartographerTick(token);
      const status = String(tick?.status || 'unknown');
      const fingerprint = String(tick?.fingerprint || '');
      await audit(env, user.game_uid, 'radar.autocartographer.tick', fingerprint || user.game_uid, {
        status,
        fingerprint: fingerprint || null,
        confirmations: Number(tick?.confirmations || 0) || 0
      });
      results.push({ gameUid: String(user.game_uid), status, fingerprint: fingerprint || null });
    } catch (error) {
      const code = String(error?.message || 'AUTO_CARTOGRAPHER_TICK_FAILED');
      await audit(env, user.game_uid, 'radar.autocartographer.error', user.game_uid, { error: code });
      results.push({ gameUid: String(user.game_uid), status: 'error', error: code });
    } finally {
      await transport.close().catch(() => {});
    }
  }

  return { status: 'ok', results };
}

'''
    s = s.replace(export_anchor, helper + export_anchor, 1)

    old = r'''  async scheduled(_event, env, ctx) {
    const run = async () => {
      const orchestrator = new RadarAgentOrchestrator({ appVersion: APP_VERSION });
      await orchestrator.bootstrap(env);
      return orchestrator.cycle(env, { activeVersion: APP_VERSION });
    };
    if (ctx?.waitUntil) ctx.waitUntil(run().catch((error) => console.error('RADAR_AGENT_CYCLE_FAILED', error?.message || error)));
    else await run();
  }
'''
    new = r'''  async scheduled(_event, env, ctx) {
    const run = async () => {
      const orchestrator = new RadarAgentOrchestrator({ appVersion: APP_VERSION });
      await orchestrator.bootstrap(env);
      const cycle = await orchestrator.cycle(env, { activeVersion: APP_VERSION });
      const cartography = await runAutoCartographerV633(env);
      console.log('AUTO_CARTOGRAPHER_WORKER_V633', JSON.stringify(cartography));
      return { cycle, cartography };
    };
    if (ctx?.waitUntil) ctx.waitUntil(run().catch((error) => console.error('RADAR_AGENT_CYCLE_FAILED', error?.message || error)));
    else await run();
  }
'''
    if s.count(old) != 1:
        raise SystemExit(f'AUTO_CARTOGRAPHER_V633_SCHEDULED_ANCHOR_EXPECTED_1_GOT_{s.count(old)}')
    s = s.replace(old, new, 1)
    p.write_text(s, encoding='utf-8')
    print('AUTO_CARTOGRAPHER_WORKER_V633=PATCHED')
else:
    print('AUTO_CARTOGRAPHER_WORKER_V633=ALREADY_PRESENT')

print('AUTO_CARTOGRAPHER_WORKER_V633_MODE=VAULT_SCHEDULED')
print('AUTO_CARTOGRAPHER_WORKER_V633_BRUTE_FORCE=NO')
