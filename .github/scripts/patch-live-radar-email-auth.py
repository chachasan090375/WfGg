#!/usr/bin/env python3
from pathlib import Path
import re

p = Path('/tmp/wfgg-radar/public/live-radar.html')
s = p.read_text(encoding='utf-8')

# The async UI patch historically targeted an older <i>-based steps markup while
# the production page uses <span> and aria-hidden. Make the live Collector state
# visible regardless of which base markup is reconstructed.
progress_marker = 'WFGG_RADAR_PROGRESS_TEXT_V2'
if 'id="progressText"' not in s:
    step_anchors = [
        '<div class="steps" aria-hidden="true"><span class="step" id="s1"></span><span class="step" id="s2"></span><span class="step" id="s3"></span><span class="step" id="s4"></span></div>',
        '<div class="steps"><i id="s1" class="step"></i><i id="s2" class="step"></i><i id="s3" class="step"></i><i id="s4" class="step"></i></div>',
    ]
    for step_anchor in step_anchors:
        if step_anchor in s:
            progress = f'<div id="progressText" class="progress-text" data-ui="{progress_marker}">RADAR PRÊT</div>'
            s = s.replace(step_anchor, progress + step_anchor, 1)
            break
if 'id="progressText"' not in s:
    raise SystemExit('RADAR_PROGRESS_TEXT_ANCHOR_MISSING')

marker = 'WFGG_LASTWAR_EMAIL_AUTH_V1'
if marker in s:
    p.write_text(s, encoding='utf-8')
    print('RADAR_PROGRESS_TEXT=VISIBLE')
    print('RADAR_LIVE_EMAIL_AUTH=ALREADY_PRESENT')
    raise SystemExit(0)

old_html = '''    <section id="login" class="login">
      <p>Session Radar requise. Le token Last War est envoyé à l’API pour ouvrir la session et n’est pas mémorisé par cette page.</p>
      <div class="tokenrow"><input id="token" class="token" type="password" placeholder="Token Last War" autocomplete="off"><button id="auth" class="authbtn" type="button">CONNECTER</button></div>
    </section>'''
new_html = '''    <section id="login" class="login" data-auth="WFGG_LASTWAR_EMAIL_AUTH_V1" data-identity-memory="WFGG_LASTWAR_IDENTITY_MEMORY_V1">
      <p id="authIntro">Connexion Last War : indique ton ID joueur et l’adresse e-mail liée au compte. Last War t’enverra un code à 6 chiffres.</p>
      <div id="authStartPanel" class="auth-fields">
        <input id="gameUid" name="lastwar-game-uid" class="token" inputmode="numeric" maxlength="64" placeholder="ID joueur Last War" autocomplete="username">
        <input id="gameEmail" name="email" class="token" type="email" inputmode="email" maxlength="320" placeholder="Adresse e-mail Last War" autocomplete="email">
        <label class="remember-row"><input id="rememberIdentity" type="checkbox"><span>Mémoriser l’ID et l’e-mail sur cet appareil</span></label>
        <button id="authSend" class="authbtn authwide" type="button">RECEVOIR LE CODE</button>
      </div>
      <div id="authCodePanel" class="auth-fields auth-hidden">
        <input id="gameCode" class="token code" inputmode="numeric" pattern="[0-9]*" maxlength="6" placeholder="Code à 6 chiffres" autocomplete="one-time-code">
        <div class="auth-actions">
          <button id="authFinish" class="authbtn" type="button">CONNECTER</button>
          <button id="authRestart" class="authbtn secondary" type="button">RECOMMENCER</button>
        </div>
      </div>
      <div id="authMsg" class="authmsg">Aucun jeton n’est demandé au joueur.</div>
    </section>'''
if old_html not in s:
    raise SystemExit('RADAR_EMAIL_AUTH_HTML_ANCHOR_MISSING')
s = s.replace(old_html, new_html, 1)

css_anchor = '.login.show{display:block}'
css_extra = '''.login.show{display:block}.auth-fields{display:grid;gap:8px}.authwide{min-height:44px}.auth-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.authbtn.secondary{background:#292613;color:#d8c987;border-color:#6f6235}.auth-hidden{display:none!important}.authmsg{margin-top:9px;min-height:18px;font-size:10px;color:#9d9167}.authmsg.ok{color:#b8ff8a}.authmsg.error{color:#ff8d78}.token.code{text-align:center;letter-spacing:.32em;font-size:18px;font-weight:900}.remember-row{display:flex;align-items:center;gap:9px;padding:4px 2px;color:#b7c6a5;font-size:10px;line-height:1.35;cursor:pointer}.remember-row input{width:17px;height:17px;accent-color:#91b84f;flex:0 0 auto}'''
if css_anchor not in s:
    raise SystemExit('RADAR_EMAIL_AUTH_CSS_ANCHOR_MISSING')
s = s.replace(css_anchor, css_extra, 1)

pattern = re.compile(r"\$\('auth'\)\.onclick=async\(\)=>\{.*?\};\n(?=\$\('searchForm'\))", re.S)
new_js = r'''let emailChallengeId='';
const LASTWAR_IDENTITY_MEMORY_KEY='wfgg_radar_lastwar_identity_v1';
function authMessage(text,kind=''){const el=$('authMsg');el.textContent=text;el.className='authmsg'+(kind?' '+kind:'')}
function authStage(stage){$('authStartPanel').classList.toggle('auth-hidden',stage!=='start');$('authCodePanel').classList.toggle('auth-hidden',stage!=='code')}
function resetEmailAuth(){emailChallengeId='';$('gameCode').value='';authStage('start');authMessage('Aucun jeton n’est demandé au joueur.')}
function loadRememberedLastWarIdentity(){try{const raw=localStorage.getItem(LASTWAR_IDENTITY_MEMORY_KEY);if(!raw)return;const d=JSON.parse(raw);const uid=String(d?.gameUid||'').trim(),email=String(d?.email||'').trim();if(uid)$('gameUid').value=uid;if(email)$('gameEmail').value=email;if(uid||email)$('rememberIdentity').checked=true}catch(_){}}
function persistLastWarIdentity(){try{if(!$('rememberIdentity').checked){localStorage.removeItem(LASTWAR_IDENTITY_MEMORY_KEY);return}const gameUid=$('gameUid').value.trim(),email=$('gameEmail').value.trim();if(gameUid&&email)localStorage.setItem(LASTWAR_IDENTITY_MEMORY_KEY,JSON.stringify({gameUid,email}))}catch(_){}}
$('rememberIdentity').addEventListener('change',()=>{if(!$('rememberIdentity').checked){try{localStorage.removeItem(LASTWAR_IDENTITY_MEMORY_KEY)}catch(_){}}else persistLastWarIdentity()});
$('authSend').onclick=async()=>{const uid=$('gameUid').value.trim(),email=$('gameEmail').value.trim();if(!/^\d{6,64}$/.test(uid)){authMessage('ID joueur invalide.','error');return}if(!email||!email.includes('@')){authMessage('Adresse e-mail invalide.','error');return}const b=$('authSend');b.disabled=true;authMessage('Demande du code à Last War…');try{const d=await api('/api/auth/lastwar/start',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({gameUid:uid,email})});emailChallengeId=String(d.challengeId||'');if(!emailChallengeId)throw new Error('CHALLENGE_LASTWAR_INVALIDE');persistLastWarIdentity();authStage('code');authMessage('Code envoyé par Last War. Saisis les 6 chiffres reçus.','ok');$('gameCode').focus()}catch(e){authMessage(e.message||'Impossible d’envoyer le code.','error')}finally{b.disabled=false}};
$('authFinish').onclick=async()=>{const code=$('gameCode').value.trim();if(!emailChallengeId){resetEmailAuth();return}if(!/^\d{6}$/.test(code)){authMessage('Le code doit contenir 6 chiffres.','error');return}const b=$('authFinish');b.disabled=true;authMessage('Validation auprès de Last War…');try{const d=await api('/api/auth/lastwar/finish',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({challengeId:emailChallengeId,code})});emailChallengeId='';$('gameCode').value='';persistLastWarIdentity();if(!$('rememberIdentity').checked){$('gameUid').value='';$('gameEmail').value=''}login.classList.remove('show');$('session').textContent=`SESSION: ${d.user?.pseudo||'OK'} · ${d.user?.role||''}`;authStage('start');authMessage('Connexion Last War validée.','ok');tone(900,.07,.02)}catch(e){authMessage(e.message||'Code refusé par Last War.','error')}finally{b.disabled=false}};
$('authRestart').onclick=()=>resetEmailAuth();
loadRememberedLastWarIdentity();
'''
s2, n = pattern.subn(lambda _m: new_js, s, count=1)
if n != 1:
    raise SystemExit('RADAR_EMAIL_AUTH_JS_ANCHOR_MISSING')
s = s2

# Guard against accidentally keeping the old manual-token path in the live page.
if '/api/auth/game-token' in s or 'id="token"' in s or "$('auth')" in s:
    raise SystemExit('RADAR_EMAIL_AUTH_OLD_TOKEN_PATH_STILL_PRESENT')
if '/api/auth/lastwar/start' not in s or '/api/auth/lastwar/finish' not in s:
    raise SystemExit('RADAR_EMAIL_AUTH_NEW_PATH_MISSING')
if 'WFGG_LASTWAR_IDENTITY_MEMORY_V1' not in s or 'LASTWAR_IDENTITY_MEMORY_KEY' not in s:
    raise SystemExit('RADAR_EMAIL_AUTH_IDENTITY_MEMORY_MISSING')
if progress_marker not in s:
    raise SystemExit('RADAR_PROGRESS_TEXT_MARKER_MISSING')
p.write_text(s, encoding='utf-8')
print('RADAR_PROGRESS_TEXT=VISIBLE')
print('RADAR_LIVE_EMAIL_AUTH=PATCHED')
print('RADAR_LASTWAR_IDENTITY_MEMORY=ENABLED')