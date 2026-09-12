#!/usr/bin/env python3
from pathlib import Path
import re

p = Path('/tmp/wfgg-radar/public/live-radar.html')
s = p.read_text(encoding='utf-8')
marker = 'WFGG_LASTWAR_EMAIL_AUTH_V1'
if marker in s:
    print('RADAR_LIVE_EMAIL_AUTH=ALREADY_PRESENT')
    raise SystemExit(0)

old_html = '''    <section id="login" class="login">
      <p>Session Radar requise. Le token Last War est envoyé à l’API pour ouvrir la session et n’est pas mémorisé par cette page.</p>
      <div class="tokenrow"><input id="token" class="token" type="password" placeholder="Token Last War" autocomplete="off"><button id="auth" class="authbtn" type="button">CONNECTER</button></div>
    </section>'''
new_html = '''    <section id="login" class="login" data-auth="WFGG_LASTWAR_EMAIL_AUTH_V1">
      <p id="authIntro">Connexion Last War : indique ton ID joueur et l’adresse e-mail liée au compte. Last War t’enverra un code à 6 chiffres.</p>
      <div id="authStartPanel" class="auth-fields">
        <input id="gameUid" class="token" inputmode="numeric" maxlength="64" placeholder="ID joueur Last War" autocomplete="off">
        <input id="gameEmail" class="token" type="email" inputmode="email" maxlength="320" placeholder="Adresse e-mail Last War" autocomplete="email">
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
css_extra = '''.login.show{display:block}.auth-fields{display:grid;gap:8px}.authwide{min-height:44px}.auth-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.authbtn.secondary{background:#292613;color:#d8c987;border-color:#6f6235}.auth-hidden{display:none!important}.authmsg{margin-top:9px;min-height:18px;font-size:10px;color:#9d9167}.authmsg.ok{color:#b8ff8a}.authmsg.error{color:#ff8d78}.token.code{text-align:center;letter-spacing:.32em;font-size:18px;font-weight:900}'''
if css_anchor not in s:
    raise SystemExit('RADAR_EMAIL_AUTH_CSS_ANCHOR_MISSING')
s = s.replace(css_anchor, css_extra, 1)

pattern = re.compile(r"\$\('auth'\)\.onclick=async\(\)=>\{.*?\};\n(?=\$\('searchForm'\))", re.S)
new_js = r'''let emailChallengeId='';
function authMessage(text,kind=''){const el=$('authMsg');el.textContent=text;el.className='authmsg'+(kind?' '+kind:'')}
function authStage(stage){$('authStartPanel').classList.toggle('auth-hidden',stage!=='start');$('authCodePanel').classList.toggle('auth-hidden',stage!=='code')}
function resetEmailAuth(){emailChallengeId='';$('gameCode').value='';authStage('start');authMessage('Aucun jeton n’est demandé au joueur.')}
$('authSend').onclick=async()=>{const uid=$('gameUid').value.trim(),email=$('gameEmail').value.trim();if(!/^\d{6,64}$/.test(uid)){authMessage('ID joueur invalide.','error');return}if(!email||!email.includes('@')){authMessage('Adresse e-mail invalide.','error');return}const b=$('authSend');b.disabled=true;authMessage('Demande du code à Last War…');try{const d=await api('/api/auth/lastwar/start',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({gameUid:uid,email})});emailChallengeId=String(d.challengeId||'');if(!emailChallengeId)throw new Error('CHALLENGE_LASTWAR_INVALIDE');authStage('code');authMessage('Code envoyé par Last War. Saisis les 6 chiffres reçus.','ok');$('gameCode').focus()}catch(e){authMessage(e.message||'Impossible d’envoyer le code.','error')}finally{b.disabled=false}};
$('authFinish').onclick=async()=>{const code=$('gameCode').value.trim();if(!emailChallengeId){resetEmailAuth();return}if(!/^\d{6}$/.test(code)){authMessage('Le code doit contenir 6 chiffres.','error');return}const b=$('authFinish');b.disabled=true;authMessage('Validation auprès de Last War…');try{const d=await api('/api/auth/lastwar/finish',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({challengeId:emailChallengeId,code})});emailChallengeId='';$('gameCode').value='';$('gameEmail').value='';login.classList.remove('show');$('session').textContent=`SESSION: ${d.user?.pseudo||'OK'} · ${d.user?.role||''}`;authStage('start');authMessage('Connexion Last War validée.','ok');tone(900,.07,.02)}catch(e){authMessage(e.message||'Code refusé par Last War.','error')}finally{b.disabled=false}};
$('authRestart').onclick=()=>resetEmailAuth();
'''
s2, n = pattern.subn(new_js, s, count=1)
if n != 1:
    raise SystemExit('RADAR_EMAIL_AUTH_JS_ANCHOR_MISSING')
s = s2

# Guard against accidentally keeping the old manual-token path in the live page.
if '/api/auth/game-token' in s or 'id="token"' in s or "$('auth')" in s:
    raise SystemExit('RADAR_EMAIL_AUTH_OLD_TOKEN_PATH_STILL_PRESENT')
if '/api/auth/lastwar/start' not in s or '/api/auth/lastwar/finish' not in s:
    raise SystemExit('RADAR_EMAIL_AUTH_NEW_PATH_MISSING')
p.write_text(s, encoding='utf-8')
print('RADAR_LIVE_EMAIL_AUTH=PATCHED')
