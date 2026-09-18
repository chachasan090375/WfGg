#!/usr/bin/env python3
from pathlib import Path

WORKER = Path('/tmp/wfgg-radar/src/worker.js')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, got {count}')
    return text.replace(old, new, 1)


text = WORKER.read_text(encoding='utf-8')
if 'WFGG_RADAR_RICH_PROFILE_WORKER_V6191' in text:
    print('RADAR_V6191_WORKER=ALREADY_PRESENT')
    raise SystemExit(0)

# Local-only cached rich profile endpoint. Normal search remains Last-War-free.
anchor = "      if (url.pathname === '/api/radar/search/start' && request.method === 'POST') {\n"
route = r'''      // WFGG_RADAR_RICH_PROFILE_WORKER_V6191
      if (url.pathname === '/api/radar/profile/rich' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const gameUid = String(url.searchParams.get('uid') || '').trim();
        if (!/^\d{6,64}$/.test(gameUid)) throw Object.assign(new Error('PROFILE_UID_REQUIRED'), { status: 400 });
        const row = await env.DB.prepare(
          'SELECT subject_uid AS gameUid, army_power AS armyPower, army_kill AS armyKill, svip_level AS svipLevel, country, avatar_ref AS avatarRef, observed_at AS observedAt, source_command AS sourceCommand FROM radar_profile_rich WHERE subject_uid = ? LIMIT 1'
        ).bind(gameUid).first();
        return json({ ok: true, readonly: true, profile: row || null });
      }

'''
text = replace_once(text, anchor, route + anchor, 'rich profile local route')

# When the existing async Collector bridge finishes an explicit @profile:<uid>
# job, persist only the observed rich fields in D1. No credential material is
# logged or stored here.
old = "          return json({ ok: true, job });\n"
new = r'''          if (job.status === 'SUCCESS' && /^@profile:\d{6,64}$/i.test(String(job.query || '')) && job.player) {
            const gameUid = String(job.player.gameUid || job.player.game_uid || '').trim();
            if (gameUid) {
              const intOrNull = value => (value === null || value === undefined || value === '')
                ? null
                : (Number.isFinite(Number(value)) ? Math.trunc(Number(value)) : null);
              const armyPower = intOrNull(job.player.armyPower);
              const armyKill = intOrNull(job.player.armyKill);
              const svipLevel = intOrNull(job.player.svipLevel);
              const country = String(job.player.country || '').trim() || null;
              const avatarRef = String(job.player.avatarRef || '').trim() || null;
              const observedAt = String(job.player.observedAt || new Date().toISOString());
              await env.DB.prepare(
                'INSERT INTO radar_profile_rich(subject_uid,army_power,army_kill,svip_level,country,avatar_ref,observed_at,source_command) VALUES(?,?,?,?,?,?,?,?) ' +
                'ON CONFLICT(subject_uid) DO UPDATE SET ' +
                'army_power=COALESCE(excluded.army_power,radar_profile_rich.army_power), ' +
                'army_kill=COALESCE(excluded.army_kill,radar_profile_rich.army_kill), ' +
                'svip_level=COALESCE(excluded.svip_level,radar_profile_rich.svip_level), ' +
                'country=COALESCE(excluded.country,radar_profile_rich.country), ' +
                'avatar_ref=COALESCE(excluded.avatar_ref,radar_profile_rich.avatar_ref), ' +
                'observed_at=excluded.observed_at, source_command=excluded.source_command'
              ).bind(gameUid, armyPower, armyKill, svipLevel, country, avatarRef, observedAt, 'get.user.info.multi').run();
              await audit(env, session.gameUid, 'radar.profile.refresh', gameUid, {
                command: 'get.user.info.multi',
                readonly: true,
                richObserved: Boolean(armyPower !== null || armyKill !== null || svipLevel !== null || country || avatarRef)
              });
            }
          }
          return json({ ok: true, job });
'''
text = replace_once(text, old, new, 'profile job D1 persistence')

WORKER.write_text(text, encoding='utf-8')
print('RADAR_RICH_PROFILE_WORKER_V6191=READY')
