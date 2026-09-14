#!/usr/bin/env python3
from pathlib import Path

p = Path('/tmp/wfgg-radar/public/live-radar.html')
s = p.read_text(encoding='utf-8')
marker = 'WFGG_RADAR_ACCOUNT_CONTROLS_V1'
if marker in s:
    print('RADAR_ACCOUNT_CONTROLS=ALREADY_PRESENT')
    raise SystemExit(0)

# CSS
css = r'''
/* WFGG_RADAR_ACCOUNT_CONTROLS_V1 */
.accountbar{margin:14px 5px 0;display:none;align-items:center;justify-content:space-between;gap:10px;padding:10px 11px;border:1px solid #33432d;border-radius:14px;background:#0b1009;box-shadow:inset 0 1px #ffffff08}.accountbar.show{display:flex}.account-session{min-width:0;color:#8e9b86;font-size:9px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.account-actions{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}.accountbtn{border:1px solid #506442;background:#182114;color:#dff5c9;border-radius:9px;padding:8px 10px;font:800 9px ui-monospace,monospace;letter-spacing:.04em}.accountbtn.reauth{border-color:#7b7a3c;color:#f0ed9b}.accountbtn.logout{border-color:#674034;color:#ffb29f;background:#21120f}.accountbtn:disabled{opacity:.55}.auth-state{color:#74826d}.auth-state.warn{color:#ffd56d}.auth-state.bad{color:#ff8d78;font-weight:900}.auth-expired{display:none;margin:10px 5px 0;padding:10px 12px;border:1px solid #7d3a30;border-radius:12px;background:#24100d;color:#ff9b89;font-size:10px;font-weight:900;letter-spacing:.04em}.auth-expired.show{display:block}
@media(max-width:520px){.accountbar{align-items:flex-start;flex-direction:column}.account-actions{width:100%;display:grid;grid-template-columns:1fr 1fr}.accountbtn{min-height:38px}}
'''
if '</style>' not in s:
    raise SystemExit('RADAR_ACCOUNT_STYLE_ANCHOR_MISSING')
s = s.replace('</style>', css + '</style>', 1)

# Account controls replace the old footer session label, while keeping the collector status footer.
old_footer = '<div class="foot"><span id="session">SESSION: …</span><span>COLLECTOR V4 · LIVE</span></div>'
new_footer = '''<div id="authExpired" class="auth-expired">AUTH LAST WAR EXPIRÉE · RÉAUTHENTIFICATION REQUISE</div>
  <div id="accountBar" class="accountbar">
    <span id="session" class="account-session">SESSION: …</span>
    <div class="account-actions">
      <button id="reauthLastWar" class="accountbtn reauth" type="button">RECONNECTER LAST WAR</button>
      <button id="logoutRadar" class="accountbtn logout" type="button">DÉCONNEXION</button>
    </div>
  </div>
  <div class="foot"><span id="authState" class="auth-state">AUTH LAST WAR · À VÉRIFIER</span><span>COLLECTOR V4 · LIVE</span></div>'''
if old_footer not in s:
    raise SystemExit('RADAR_ACCOUNT_FOOTER_ANCHOR_MISSING')
s = s.replace(old_footer, new_footer, 1)

# Helpers and buttons are inserted after the e-mail auth reset handler added by the previous patcher.
anchor = "$('authRestart').onclick=()=>resetEmailAuth();"
js = r'''
function setAuthState(text,kind=''){const e=$('authState');if(!e)return;e.textContent=text;e.className='auth-state'+(kind?' '+kind:'')}
function onAuthSessionReady(user){$('accountBar')?.classList.add('show');$('authExpired')?.classList.remove('show');$('session').textContent=`SESSION: ${user?.pseudo||'OK'} · ${user?.role||''}`;setAuthState('AUTH LAST WAR · VALIDÉE')}
function isLastWarAuthError(err){const m=String(err?.message||err||'').toUpperCase();return m.includes('LASTWAR_AUTH_REJECTED')||m.includes('LASTWAR_AUTH_EXPIRED')||m.includes('AUTH_REJECTED')}
function showReauthRequired(detail=''){stopScan();$('accountBar')?.classList.add('show');$('authExpired')?.classList.add('show');setAuthState('AUTH LAST WAR · EXPIRÉE','bad');resetEmailAuth();$('authIntro').textContent='La connexion Last War a expiré. Indique ton ID joueur et ton e-mail puis saisis le nouveau code reçu.';login.classList.add('show');setStatus('AUTH LAST WAR EXPIRÉE',detail||'Réauthentification requise','error');setTimeout(()=>login.scrollIntoView({behavior:'smooth',block:'center'}),60)}
$('reauthLastWar').onclick=()=>{resetEmailAuth();$('authIntro').textContent='Réauthentification Last War : indique ton ID joueur et ton e-mail pour recevoir un nouveau code.';$('authExpired')?.classList.remove('show');setAuthState('AUTH LAST WAR · RÉAUTHENTIFICATION','warn');login.classList.add('show');setTimeout(()=>login.scrollIntoView({behavior:'smooth',block:'center'}),60)};
$('logoutRadar').onclick=async()=>{const b=$('logoutRadar');b.disabled=true;try{await api('/api/auth/logout',{method:'POST'});$('accountBar')?.classList.remove('show');$('authExpired')?.classList.remove('show');$('session').textContent='SESSION: NON CONNECTÉE';setAuthState('AUTH LAST WAR · DÉCONNECTÉE','warn');result.classList.remove('show');screen.classList.remove('found','scanning');resetEmailAuth();$('authIntro').textContent='Connexion Last War : indique ton ID joueur et l’adresse e-mail liée au compte. Last War t’enverra un code à 6 chiffres.';login.classList.add('show');setStatus('SESSION FERMÉE','Reconnecte-toi pour utiliser le Radar');tone(260,.07,.018)}catch(e){setStatus('DÉCONNEXION IMPOSSIBLE',e.message,'error')}finally{b.disabled=false}};
'''
if anchor not in s:
    raise SystemExit('RADAR_ACCOUNT_AUTH_JS_ANCHOR_MISSING')
s = s.replace(anchor, anchor + js, 1)

old_session = "async function session(){try{const d=await api('/api/me');$('session').textContent=`SESSION: ${d.user?.pseudo||'OK'} · ${d.user?.role||''}`;login.classList.remove('show');return true}catch(e){$('session').textContent='SESSION: NON CONNECTÉE';if(e.status===401)login.classList.add('show');return false}}"
new_session = "async function session(){try{const d=await api('/api/me');onAuthSessionReady(d.user);login.classList.remove('show');setAuthState('AUTH LAST WAR · SESSION ACTIVE');return true}catch(e){$('accountBar')?.classList.remove('show');$('session').textContent='SESSION: NON CONNECTÉE';setAuthState('AUTH LAST WAR · DÉCONNECTÉE','warn');if(e.status===401)login.classList.add('show');return false}}"
if old_session not in s:
    raise SystemExit('RADAR_ACCOUNT_SESSION_ANCHOR_MISSING')
s = s.replace(old_session, new_session, 1)

old_finish = "login.classList.remove('show');$('session').textContent=`SESSION: ${d.user?.pseudo||'OK'} · ${d.user?.role||''}`;authStage('start');authMessage('Connexion Last War validée.','ok');tone(900,.07,.02)"
new_finish = "login.classList.remove('show');onAuthSessionReady(d.user);authStage('start');authMessage('Connexion Last War validée.','ok');tone(900,.07,.02)"
if old_finish not in s:
    raise SystemExit('RADAR_ACCOUNT_AUTH_SUCCESS_ANCHOR_MISSING')
s = s.replace(old_finish, new_finish, 1)

old_catch = "if(err.status===401){login.classList.add('show');setStatus('SESSION REQUISE','Connecte le Radar puis relance la recherche','error')}else setStatus('ERREUR RADAR',err.message,'error')"
new_catch = "if(err.status===401){login.classList.add('show');setStatus('SESSION REQUISE','Connecte le Radar puis relance la recherche','error')}else if(isLastWarAuthError(err)){showReauthRequired(err.message)}else setStatus('ERREUR RADAR',err.message,'error')"
if old_catch not in s:
    raise SystemExit('RADAR_ACCOUNT_SEARCH_CATCH_ANCHOR_MISSING')
s = s.replace(old_catch, new_catch, 1)

p.write_text(s, encoding='utf-8')
print('RADAR_ACCOUNT_CONTROLS=PATCHED')
