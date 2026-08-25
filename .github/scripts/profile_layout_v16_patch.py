from pathlib import Path
import re

p=Path('frontend/portal-v070.js')
s=p.read_text(encoding='utf-8')

s=s.replace("settingsTab:'profile',sessions:[],trainRotationSummary:null,trainRotationLoading:false", "settingsTab:'profile',profileSubpage:'main',sessions:[],trainRotationSummary:null,trainRotationLoading:false",1)
s=s.replace("members:[],sessions:[],trainRotationSummary:null,trainRotationLoading:false});}", "members:[],sessions:[],profileSubpage:'main',trainRotationSummary:null,trainRotationLoading:false});}",1)
s=s.replace("function openSettings(tab='profile'){$('profileMenu').classList.add('hidden');state.settingsTab=isAdmin()||tab==='profile'?tab:'profile';$('settingsOverlay').classList.remove('hidden');renderSettings()}", "function openSettings(tab='profile'){$('profileMenu').classList.add('hidden');state.settingsTab=isAdmin()||tab==='profile'?tab:'profile';if(state.settingsTab==='profile')state.profileSubpage='main';$('settingsOverlay').classList.remove('hidden');renderSettings()}",1)

old_home="""function renderHomeTrainRotationCard(){
  const grid=document.querySelector('.module-grid');if(!grid)return;
  let card=$('homeTrainRotationCard');
  if(!card){card=document.createElement('section');card.id='homeTrainRotationCard';card.className='glass-card settings-card-block';grid.parentNode.insertBefore(card,grid);}
  const x=trainRotationLabels(),r=state.trainRotationSummary;
  if(!r){card.innerHTML=`<div class=\"section-heading\"><h3>🚂 ${esc(x.title)}</h3></div><span class=\"muted\">…</span>`;return;}
  const driverLabel=r.driverRole==='A'?x.driverA:x.driverB;
  card.innerHTML=`<div class=\"section-heading\"><h3>🚂 ${esc(x.title)}</h3></div><div class=\"readonly-grid\"><div><small>${esc(driverLabel)} · ${esc(x.total)}</small><strong>${r.driver||0}</strong><small>${esc(x.last)} : ${esc(trainDateLabel(r.driverLast))}<br>${esc(x.next)} : ${esc(trainDateLabel(r.driverNext))}</small></div><div><small>⭐ ${esc(x.vip)} · ${esc(x.total)}</small><strong>${r.vip||0}</strong><small>${esc(x.last)} : ${esc(trainDateLabel(r.vipLast))}<br>${esc(x.next)} : ${esc(trainDateLabel(r.vipNext))}</small></div></div>`;
}
async function loadHomeTrainRotation(){
  if(!state.user||state.trainRotationLoading)return;
  state.trainRotationLoading=true;renderHomeTrainRotationCard();
  try{const snap=await trainAdminApi('/api/snapshot',{method:'GET'});state.trainRotationSummary=trainRotationForUser(snap,snap.me||{});}catch(_){state.trainRotationSummary=null;}finally{state.trainRotationLoading=false;renderHomeTrainRotationCard();}
}
"""
new_profile="""function renderProfileTrainRotationCard(){
  const host=$('profileTrainRotationHost');if(!host)return;
  const x=trainRotationLabels(),r=state.trainRotationSummary;
  if(!r){host.innerHTML=`<div class=\"section-heading\"><h3>🚂 ${esc(x.title)}</h3></div><span class=\"muted\">…</span>`;return;}
  const driverLabel=r.driverRole==='A'?x.driverA:x.driverB;
  host.innerHTML=`<div class=\"section-heading\"><h3>🚂 ${esc(x.title)}</h3></div><div class=\"readonly-grid\"><div><small>${esc(driverLabel)} · ${esc(x.total)}</small><strong>${r.driver||0}</strong><small>${esc(x.last)} : ${esc(trainDateLabel(r.driverLast))}<br>${esc(x.next)} : ${esc(trainDateLabel(r.driverNext))}</small></div><div><small>⭐ ${esc(x.vip)} · ${esc(x.total)}</small><strong>${r.vip||0}</strong><small>${esc(x.last)} : ${esc(trainDateLabel(r.vipLast))}<br>${esc(x.next)} : ${esc(trainDateLabel(r.vipNext))}</small></div></div>`;
}
async function loadProfileTrainRotation(){
  if(!state.user||state.trainRotationLoading)return;
  state.trainRotationLoading=true;renderProfileTrainRotationCard();
  try{const snap=await trainAdminApi('/api/snapshot',{method:'GET'});state.trainRotationSummary=trainRotationForUser(snap,snap.me||{});}catch(_){state.trainRotationSummary=null;}finally{state.trainRotationLoading=false;renderProfileTrainRotationCard();}
}
"""
if old_home not in s: raise SystemExit('home rotation block not found')
s=s.replace(old_home,new_profile,1)
s=s.replace("  renderHomeTrainRotationCard();\n  if(!state.trainRotationLoading)loadHomeTrainRotation();", "  $('homeTrainRotationCard')?.remove();",1)

profile_labels="""
function profileLayoutLabels(){
  const all={
    fr:{history:'Historique des connexions',historyDesc:'Consulter les connexions et sessions connues de ce profil.',openHistory:'Voir l’historique',back:'← Mon profil',refresh:'Actualiser',revoke:'Fermer les autres sessions',current:'Session actuelle',session:'Session',unknown:'Appareil inconnu',empty:'Aucune session.'},
    it:{history:'Cronologia accessi',historyDesc:'Consulta gli accessi e le sessioni conosciute di questo profilo.',openHistory:'Vedi cronologia',back:'← Il mio profilo',refresh:'Aggiorna',revoke:'Chiudi le altre sessioni',current:'Sessione attuale',session:'Sessione',unknown:'Dispositivo sconosciuto',empty:'Nessuna sessione.'},
    en:{history:'Sign-in history',historyDesc:'View the known sign-ins and sessions for this profile.',openHistory:'View history',back:'← My profile',refresh:'Refresh',revoke:'Close other sessions',current:'Current session',session:'Session',unknown:'Unknown device',empty:'No sessions.'},
    es:{history:'Historial de conexiones',historyDesc:'Consulta las conexiones y sesiones conocidas de este perfil.',openHistory:'Ver historial',back:'← Mi perfil',refresh:'Actualizar',revoke:'Cerrar las otras sesiones',current:'Sesión actual',session:'Sesión',unknown:'Dispositivo desconocido',empty:'No hay sesiones.'}
  };
  return all[state.lang]||all.fr;
}
"""
marker="function profileSettingsHtml(){"
if marker not in s: raise SystemExit('profileSettingsHtml missing')
s=s.replace(marker,profile_labels+"\n"+marker,1)

pattern=r"function profileSettingsHtml\(\)\{.*?\}\nfunction allianceSettingsHtml"
m=re.search(pattern,s,flags=re.S)
if not m: raise SystemExit('profileSettingsHtml block not found')
new_func="""function profileSettingsHtml(){
  const name=state.user?.display_name||state.user?.player_name||'',px=profileLayoutLabels();
  if(state.profileSubpage==='sessions')return `<div class=\"settings-section\"><div class=\"settings-card-block\"><button id=\"backProfileSettings\" class=\"secondary-button\" type=\"button\">${esc(px.back)}</button><div class=\"section-heading\" style=\"margin-top:16px\"><div><h3>🕘 ${esc(px.history)}</h3><p class=\"muted\">${esc(px.historyDesc)}</p></div><button id=\"refreshSessions\" class=\"secondary-button\" type=\"button\">${esc(px.refresh)}</button></div><div id=\"sessionList\" class=\"session-list\"><span class=\"muted\">…</span></div><div class=\"setting-actions\"><button class=\"secondary-button\" type=\"button\" data-action=\"revoke-others\">${esc(px.revoke)}</button></div></div></div>`;
  return `<div class=\"settings-section\"><form id=\"profileForm\" class=\"settings-form\"><div class=\"settings-card-block\"><div class=\"avatar-editor\"><span id=\"settingsAvatar\" class=\"avatar large\"></span><div><label class=\"secondary-button file-button\">📷 Changer la photo<input id=\"avatarInput\" class=\"hidden\" type=\"file\" accept=\"image/jpeg,image/png,image/webp\"></label><small class=\"muted\">JPG, PNG ou WebP · 2 Mo max · carré 1:1</small></div></div><label class=\"field-label\">Pseudo affiché</label><input id=\"displayName\" maxlength=\"40\" value=\"${esc(name)}\"><label class=\"field-label\">Langue</label><select id=\"languageSelect\"><option value=\"fr\">Français</option><option value=\"it\">Italiano</option><option value=\"en\">English</option><option value=\"es\">Español</option></select>${readonly()}<button class=\"primary-button\" type=\"submit\">${esc(t('settings.save'))}</button><div id=\"profileMessage\" class=\"hidden\"></div></div></form><div id=\"profileTrainRotationHost\" class=\"settings-card-block\"><div class=\"section-heading\"><h3>🚂 ${esc(trainRotationLabels().title)}</h3></div><span class=\"muted\">…</span></div><div class=\"settings-card-block\"><h3>🔐 ${esc(t('settings.security'))}</h3><form id=\"codeForm\" class=\"settings-form\"><label class=\"field-label\">Code actuel</label><input id=\"currentCode\" type=\"password\" inputmode=\"numeric\" maxlength=\"6\" placeholder=\"••••••\"><label class=\"field-label\">Nouveau code</label><input id=\"newCode\" type=\"password\" inputmode=\"numeric\" maxlength=\"6\" placeholder=\"••••••\"><button class=\"secondary-button\" type=\"submit\">Changer mon code</button><div id=\"codeMessage\" class=\"hidden\"></div></form><div class=\"setting-actions\" style=\"margin-top:16px\"><button id=\"openSessionHistory\" class=\"secondary-button\" type=\"button\">🕘 ${esc(px.openHistory)}</button></div></div></div>`;
}
function allianceSettingsHtml"""
s=s[:m.start()]+new_func+s[m.end():]

old_bind="function bindSettingsForms(){paintAvatar($('settingsAvatar'),state.user);if($('languageSelect'))$('languageSelect').value=state.user?.language||state.lang;$('profileForm')?.addEventListener('submit',saveProfile);$('avatarInput')?.addEventListener('change',uploadAvatar);$('codeForm')?.addEventListener('submit',changeOwnCode);$('refreshSessions')?.addEventListener('click',loadSessions);$('allianceForm')?.addEventListener('submit',saveAlliance);$('applicationForm')?.addEventListener('submit',saveApplication);$('openMembersButton')?.addEventListener('click',openMembers);$('refreshPlayerStats')?.addEventListener('click',loadPlayerStatistics);if(state.settingsTab==='profile')loadSessions();if(state.settingsTab==='statistics')loadPlayerStatistics();}"
new_bind="function bindSettingsForms(){paintAvatar($('settingsAvatar'),state.user);if($('languageSelect'))$('languageSelect').value=state.user?.language||state.lang;$('profileForm')?.addEventListener('submit',saveProfile);$('avatarInput')?.addEventListener('change',uploadAvatar);$('codeForm')?.addEventListener('submit',changeOwnCode);$('openSessionHistory')?.addEventListener('click',()=>{state.profileSubpage='sessions';renderSettingsContent()});$('backProfileSettings')?.addEventListener('click',()=>{state.profileSubpage='main';renderSettingsContent()});$('refreshSessions')?.addEventListener('click',loadSessions);$('allianceForm')?.addEventListener('submit',saveAlliance);$('applicationForm')?.addEventListener('submit',saveApplication);$('openMembersButton')?.addEventListener('click',openMembers);$('refreshPlayerStats')?.addEventListener('click',loadPlayerStatistics);if(state.settingsTab==='profile'&&state.profileSubpage==='sessions')loadSessions();if(state.settingsTab==='profile'&&state.profileSubpage==='main'&&!state.trainRotationLoading)loadProfileTrainRotation();if(state.settingsTab==='statistics')loadPlayerStatistics();}"
if old_bind not in s: raise SystemExit('bindSettingsForms block not found')
s=s.replace(old_bind,new_bind,1)

old_load="async function loadSessions(){const el=$('sessionList');if(!el)return;try{const d=await api('/api/me/sessions');state.sessions=d.sessions||[];el.innerHTML=state.sessions.map(s=>`<div class=\"session-row\"><div><strong>${s.current?'Session actuelle':'Session'}</strong><br><small>${esc(s.user_agent||'Appareil inconnu')}</small></div><small>${new Date(s.last_seen_at).toLocaleString(state.lang)}</small></div>`).join('')||'<span class=\"muted\">Aucune session.</span>'}catch(err){el.innerHTML=`<span class=\"error-text\">${esc(err.message)}</span>`}}"
new_load="async function loadSessions(){const el=$('sessionList');if(!el)return;const px=profileLayoutLabels();try{const d=await api('/api/me/sessions');state.sessions=d.sessions||[];el.innerHTML=state.sessions.map(s=>`<div class=\"session-row\"><div><strong>${esc(s.current?px.current:px.session)}</strong><br><small>${esc(s.user_agent||px.unknown)}</small></div><small>${new Date(s.last_seen_at).toLocaleString(state.lang)}</small></div>`).join('')||`<span class=\"muted\">${esc(px.empty)}</span>`}catch(err){el.innerHTML=`<span class=\"error-text\">${esc(err.message)}</span>`}}"
if old_load not in s: raise SystemExit('loadSessions block not found')
s=s.replace(old_load,new_load,1)

p.write_text(s,encoding='utf-8')
print('WFGG_PROFILE_LAYOUT_V16=PATCHED')
