#!/usr/bin/env python3
from pathlib import Path

UI = Path('/tmp/wfgg-radar/public/live-radar.html')

def replace_once(text, old, new, label):
    n=text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old,new,1)

ui=UI.read_text(encoding='utf-8')
if 'WFGG_RADAR_LIVE_PROFILE_RESOLUTION_UI_V622' in ui:
    print('RADAR_V622_LIVE_PROFILE_UI=ALREADY_PRESENT')
    raise SystemExit(0)

marker_anchor='/* WFGG_RADAR_RICH_PROFILE_UI_V6191 */\n'
insert=r'''/* WFGG_RADAR_LIVE_PROFILE_RESOLUTION_UI_V622 */
/* Local identity resolution stays fast; once an UID is known, the displayed
   player is refreshed live with get.user.info.multi through @profile:<uid>.
   The profile-only Connector path does not start a MAP sweep. */
let liveProfileRefreshSeqV622=0;
let liveProfileRefreshUIDV622='';
function applyPlayerCoreV622(p){
  if(!p)return;
  const name=pick(p,'pseudo','name','player_name','playerName');
  const server=pick(p,'server_id','serverId','server');
  const alliance=pick(p,'alliance_tag','allianceTag','alliance_name','allianceName','alliance');
  const hq=pick(p,'hq_level','hqLevel','level','baseLevel');
  const power=pick(p,'power','combatPower','strength');
  const x=pick(p,'x','mapX','pos_x'),y=pick(p,'y','mapY','pos_y');
  const uid=pick(p,'game_uid','gameUid','uid','playerId');
  if(name!=null)$('rname').textContent=String(name);
  if(server!=null)$('rserver').textContent=fmt(server);
  if(alliance!=null)$('ralliance').textContent=fmt(alliance);
  if(hq!=null)$('rhq').textContent=fmt(hq);
  if(power!=null)$('rpower').textContent=fmt(power);
  if(x!=null&&y!=null)$('rpos').textContent=`${x} / ${y}`;
  if(uid!=null)$('ruid').textContent=fmt(uid);
  locate(p);
}
async function refreshResolvedProfileV622(uid,{manual=false}={}){
  uid=String(uid||'').trim();
  if(!/^\d{6,64}$/.test(uid))return null;
  const seq=++liveProfileRefreshSeqV622;
  liveProfileRefreshUIDV622=uid;
  const button=$('refreshProfile');
  if(button)button.disabled=true;
  if($('profileNote'))$('profileNote').textContent=manual
    ?'Actualisation READ-ONLY via get.user.info.multi…'
    :'Donnée locale affichée · actualisation Last War en temps réel…';
  if(manual)setStatus('ACTUALISATION PROFIL',uid);
  try{
    const d=await runCollectorSearch('@profile:'+uid);
    const p=playerFrom(d);
    if(seq!==liveProfileRefreshSeqV622||uid!==String(currentProfileUID||''))return p||null;
    if(p){
      applyPlayerCoreV622(p);
      applyRichProfile(p);
    }
    await loadCachedRichProfile(uid);
    if(seq!==liveProfileRefreshSeqV622||uid!==String(currentProfileUID||''))return p||null;
    $('rprofilesource').textContent='get.user.info.multi · LIVE';
    $('rsource').textContent='LIVE PROFILE';
    $('rraw').textContent='UID '+uid+' · get.user.info.multi · READ-ONLY · aucun scan MAP';
    $('profileNote').textContent='Profil Last War actualisé en temps réel. Aucun scan cartographique lancé.';
    setStatus('PROFIL ACTUALISÉ',$('rname').textContent,'ok');
    return p||null;
  }catch(err){
    if(seq!==liveProfileRefreshSeqV622||uid!==String(currentProfileUID||''))return null;
    if(isLastWarAuthError(err)){
      showReauthRequired(err.message);
    }else{
      $('profileNote').textContent='Dernière donnée Collector affichée · actualisation live indisponible : '+String(err.message||err);
      if(manual)setStatus('PROFIL NON ACTUALISÉ',String(err.message||err),'error');
    }
    return null;
  }finally{
    if(seq===liveProfileRefreshSeqV622&&button)button.disabled=!currentProfileUID;
  }
}
function scheduleResolvedProfileRefreshV622(uid){
  uid=String(uid||'').trim();
  if(!/^\d{6,64}$/.test(uid))return;
  queueMicrotask(()=>refreshResolvedProfileV622(uid,{manual:false}));
}
'''
ui=replace_once(ui,marker_anchor,marker_anchor+insert,'V622 rich profile marker')

old_refresh="async function refreshCurrentProfile(){const uid=String(currentProfileUID||'').trim();if(!uid)return;const b=$('refreshProfile');b.disabled=true;$('profileNote').textContent='Actualisation READ-ONLY via get.user.info.multi…';setStatus('ACTUALISATION PROFIL',uid);try{const d=await runCollectorSearch('@profile:'+uid);const p=playerFrom(d);if(p)applyRichProfile(p);await loadCachedRichProfile(uid);$('rprofilesource').textContent='get.user.info.multi';$('profileNote').textContent='Profil observé et mis en cache localement. Aucun scan cartographique lancé.';setStatus('PROFIL ACTUALISÉ',$('rname').textContent,'ok')}catch(err){if(isLastWarAuthError(err)){showReauthRequired(err.message)}else{$('profileNote').textContent='Actualisation profil impossible : '+String(err.message||err);setStatus('PROFIL NON ACTUALISÉ',String(err.message||err),'error')}}finally{b.disabled=false}}"
new_refresh="async function refreshCurrentProfile(){const uid=String(currentProfileUID||'').trim();if(!uid)return;await refreshResolvedProfileV622(uid,{manual:true})}"
ui=replace_once(ui,old_refresh,new_refresh,'V622 manual refresh reuse')

old_note="$('profileNote').textContent='Recherche normale = cache local. Actualisation profil explicite et READ-ONLY.';"
new_note="$('profileNote').textContent=currentProfileUID?'Donnée Collector affichée · actualisation Last War en temps réel…':'Aucun UID connu : actualisation live impossible.';"
ui=replace_once(ui,old_note,new_note,'V622 profile note')

uid_anchor="currentProfileUID=uid?String(uid):'';"
uid_replacement="currentProfileUID=uid?String(uid):'';if(currentProfileUID){scheduleResolvedProfileRefreshV622(currentProfileUID);}"
ui=replace_once(ui,uid_anchor,uid_replacement,'V622 auto refresh hook')

UI.write_text(ui,encoding='utf-8')
print('RADAR_V622_LIVE_PROFILE_RESOLUTION_UI=READY')
print('RADAR_V622_PIPELINE=LOCAL_UID_THEN_LIVE_PROFILE')
print('RADAR_V622_LASTWAR_COMMAND=get.user.info.multi')
print('RADAR_V622_MAP_SCAN_FOR_PROFILE=NO')
