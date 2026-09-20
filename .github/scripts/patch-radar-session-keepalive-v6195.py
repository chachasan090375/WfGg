#!/usr/bin/env python3
from pathlib import Path

WORKER = Path('/tmp/wfgg-radar/src/worker.js')
UI = Path('/tmp/wfgg-radar/public/live-radar.html')

worker = WORKER.read_text(encoding='utf-8')
if 'WFGG_RADAR_SESSION_KEEPALIVE_V6195' not in worker:
    require_anchor = """async function requireSession(request, env) {
  const session = await currentSession(request, env);
  if (!session) throw Object.assign(new Error('RADAR_SESSION_REQUIRED'), { status: 401 });
  return session;
}

"""
    if worker.count(require_anchor) != 1:
        raise SystemExit(f'V6195_REQUIRE_SESSION_ANCHOR_COUNT={worker.count(require_anchor)}')
    helper = require_anchor + """// WFGG_RADAR_SESSION_KEEPALIVE_V6195
function radarSessionTtlV6195(env) {
  return Math.max(900, Math.min(Number(env.RADAR_SESSION_TTL || 43200), 43200));
}

async function renewRadarSessionV6195(request, env) {
  const current = await requireSession(request, env);
  const sessionKey = requireSecret(env.RADAR_SESSION_KEY, 'RADAR_SESSION_KEY');
  const ttl = radarSessionTtlV6195(env);
  const renewed = await createSession({
    gameUid: current.gameUid,
    pseudo: current.pseudo,
    serverId: current.serverId || null,
    role: current.role
  }, sessionKey, ttl);
  return json({
    ok: true,
    renewed: true,
    expiresIn: ttl,
    user: {
      gameUid: current.gameUid,
      pseudo: current.pseudo,
      serverId: current.serverId || null,
      role: current.role
    }
  }, 200, { 'set-cookie': sessionCookie(renewed, ttl) });
}

"""
    worker = worker.replace(require_anchor, helper, 1)

    old_ttl = "const ttl = Math.max(900, Math.min(Number(env.RADAR_SESSION_TTL || 3600), 43200));"
    if worker.count(old_ttl) < 1:
        raise SystemExit(f'V6195_AUTH_TTL_ANCHOR_COUNT={worker.count(old_ttl)}')
    ttl_anchor_count = worker.count(old_ttl)
    worker = worker.replace(old_ttl, "const ttl = radarSessionTtlV6195(env);")
    print(f'RADAR_V6195_SESSION_TTL_ISSUERS_PATCHED={ttl_anchor_count}')

    route_anchor = """      if (url.pathname === '/api/auth/game-token' && request.method === 'POST') return await authenticateGameToken(request, env);

      if (url.pathname === '/api/me' && request.method === 'GET') {
"""
    if worker.count(route_anchor) != 1:
        raise SystemExit(f'V6195_ROUTE_ANCHOR_COUNT={worker.count(route_anchor)}')
    route = """      if (url.pathname === '/api/auth/game-token' && request.method === 'POST') return await authenticateGameToken(request, env);

      if (url.pathname === '/api/auth/session/refresh' && request.method === 'POST') {
        return await renewRadarSessionV6195(request, env);
      }

      if (url.pathname === '/api/me' && request.method === 'GET') {
"""
    worker = worker.replace(route_anchor, route, 1)
    WORKER.write_text(worker, encoding='utf-8')
    print('RADAR_V6195_SESSION_KEEPALIVE_WORKER=PATCHED')
else:
    print('RADAR_V6195_SESSION_KEEPALIVE_WORKER=ALREADY_PRESENT')

text = UI.read_text(encoding='utf-8')
if 'WFGG_RADAR_SESSION_KEEPALIVE_UI_V6195' not in text:
    session_anchor = """async function session(){try{const d=await api('/api/me');onAuthSessionReady(d.user);login.classList.remove('show');setAuthState('AUTH LAST WAR · SESSION ACTIVE');return true}catch(e){$('accountBar')?.classList.remove('show');$('session').textContent='SESSION: NON CONNECTÉE';setAuthState('AUTH LAST WAR · DÉCONNECTÉE','warn');if(e.status===401)login.classList.add('show');return false}}
"""
    if text.count(session_anchor) != 1:
        raise SystemExit(f'V6195_UI_SESSION_ANCHOR_COUNT={text.count(session_anchor)}')
    keepalive = session_anchor + r"""/* WFGG_RADAR_SESSION_KEEPALIVE_UI_V6195 */
const RADAR_SESSION_KEEPALIVE_INTERVAL_MS_V6195=3*60*60*1000;
let radarSessionKeepaliveTimerV6195=null;
let radarSessionLastRenewedAtV6195=0;
function stopRadarSessionKeepaliveV6195(){
  if(radarSessionKeepaliveTimerV6195){
    clearTimeout(radarSessionKeepaliveTimerV6195);
    radarSessionKeepaliveTimerV6195=null;
  }
}
function scheduleRadarSessionKeepaliveV6195(delay=RADAR_SESSION_KEEPALIVE_INTERVAL_MS_V6195){
  stopRadarSessionKeepaliveV6195();
  radarSessionKeepaliveTimerV6195=setTimeout(()=>renewRadarSessionV6195(true),delay);
}
async function renewRadarSessionV6195(silent=true){
  try{
    const d=await api('/api/auth/session/refresh',{method:'POST'});
    radarSessionLastRenewedAtV6195=Date.now();
    if(d?.user)onAuthSessionReady(d.user);
    scheduleRadarSessionKeepaliveV6195();
    if(!silent)setStatus('SESSION RADAR RENOUVELÉE','Session glissante 12 h','ok');
    return true;
  }catch(err){
    stopRadarSessionKeepaliveV6195();
    if(err.status===401){
      $('accountBar')?.classList.remove('show');
      $('session').textContent='SESSION: EXPIRÉE';
      setAuthState('SESSION RADAR · EXPIRÉE','warn');
      login.classList.add('show');
      if(!silent)setStatus('SESSION RADAR EXPIRÉE','Reconnecte-toi une fois pour reprendre une session de 12 h','error');
      return false;
    }
    scheduleRadarSessionKeepaliveV6195(15*60*1000);
    return false;
  }
}
document.addEventListener('visibilitychange',()=>{
  if(document.visibilityState!=='visible')return;
  const age=Date.now()-Number(radarSessionLastRenewedAtV6195||0);
  if(age>=RADAR_SESSION_KEEPALIVE_INTERVAL_MS_V6195)renewRadarSessionV6195(true);
});
"""
    text = text.replace(session_anchor, keepalive, 1)

    auth_ready_old = """function onAuthSessionReady(user){$('accountBar')?.classList.add('show');$('authExpired')?.classList.remove('show');$('session').textContent=`SESSION: ${user?.pseudo||'OK'} · ${user?.role||''}`;setAuthState('AUTH LAST WAR · VALIDÉE')}"""
    auth_ready_new = """function onAuthSessionReady(user){$('accountBar')?.classList.add('show');$('authExpired')?.classList.remove('show');$('session').textContent=`SESSION: ${user?.pseudo||'OK'} · ${user?.role||''} · AUTO 12H`;setAuthState('AUTH LAST WAR · VALIDÉE');radarSessionLastRenewedAtV6195=Date.now();scheduleRadarSessionKeepaliveV6195()}"""
    if text.count(auth_ready_old) != 1:
        raise SystemExit(f'V6195_AUTH_READY_ANCHOR_COUNT={text.count(auth_ready_old)}')
    text = text.replace(auth_ready_old, auth_ready_new, 1)

    logout_old = """await api('/api/auth/logout',{method:'POST'});$('accountBar')?.classList.remove('show');"""
    logout_new = """await api('/api/auth/logout',{method:'POST'});stopRadarSessionKeepaliveV6195();radarSessionLastRenewedAtV6195=0;$('accountBar')?.classList.remove('show');"""
    if text.count(logout_old) != 1:
        raise SystemExit(f'V6195_LOGOUT_ANCHOR_COUNT={text.count(logout_old)}')
    text = text.replace(logout_old, logout_new, 1)

    bootstrap_old = "health();session();"
    bootstrap_new = "health();session().then(ok=>{if(ok)renewRadarSessionV6195(true)});"
    if text.count(bootstrap_old) != 1:
        raise SystemExit(f'V6195_BOOTSTRAP_ANCHOR_COUNT={text.count(bootstrap_old)}')
    text = text.replace(bootstrap_old, bootstrap_new, 1)

    UI.write_text(text, encoding='utf-8')
    print('RADAR_V6195_SESSION_KEEPALIVE_UI=PATCHED')
else:
    print('RADAR_V6195_SESSION_KEEPALIVE_UI=ALREADY_PRESENT')

print('RADAR_V6195_SESSION_KEEPALIVE=READY')
