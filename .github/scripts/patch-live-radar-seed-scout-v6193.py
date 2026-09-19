#!/usr/bin/env python3
from pathlib import Path

UI = Path('/tmp/wfgg-radar/public/live-radar.html')
text = UI.read_text(encoding='utf-8')

if 'WFGG_RADAR_SEED_SCOUT_UI_V6193' in text:
    print('RADAR_V6193_SEED_SCOUT_UI=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = '  <div id="federatedLive" class="federated-live"><span id="federatedTitle" class="federated-title">COLLECTOR FÉDÉRÉ · EN ATTENTE</span><span id="federatedMeta" class="federated-meta">Aucun cycle actif.</span></div>\n'
if text.count(anchor) != 1:
    raise SystemExit(f'V6193_UI_PANEL_ANCHOR_COUNT={text.count(anchor)}')
addition = anchor + '''  <!-- WFGG_RADAR_SEED_SCOUT_UI_V6193 -->
  <div class="profile-actions"><button id="seedScout" class="profile-refresh" type="button">DÉCOUVRIR LA PROCHAINE GRAPPE</button></div>
  <div id="seedScoutNote" class="profile-note">Seed Scout V6.19.3 · 1 région par serveur · aucune écriture Collector.</div>
'''
text = text.replace(anchor, addition, 1)

js_anchor = 'async function health(){'
if text.count(js_anchor) != 1:
    raise SystemExit(f'V6193_UI_JS_ANCHOR_COUNT={text.count(js_anchor)}')
js = r'''/* WFGG_RADAR_SEED_SCOUT_UI_V6193 */
const WFGG_RADAR_SEED_SCOUT_OFFSET_KEY='wfgg_radar_seed_scout_offset_v6193';
function seedScoutOffsetV6193(){try{return Math.max(0,Number(sessionStorage.getItem(WFGG_RADAR_SEED_SCOUT_OFFSET_KEY)||0)||0)}catch(_){return 0}}
function saveSeedScoutOffsetV6193(value){try{sessionStorage.setItem(WFGG_RADAR_SEED_SCOUT_OFFSET_KEY,String(Math.max(0,Number(value)||0)))}catch(_){}}
async function runSeedScoutV6193(){
  const b=$('seedScout'),note=$('seedScoutNote'),box=$('federatedLive'),title=$('federatedTitle'),meta=$('federatedMeta');
  b.disabled=true;box?.classList.add('show');note.textContent='Seed Scout en cours · essais ciblés READ-ONLY…';setStatus('SEED SCOUT','Recherche de la prochaine seed sans créer de cycle…');
  try{
    const offset=seedScoutOffsetV6193();
    const started=await api('/api/radar/seed-scout/start',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({limit:8,region:4,minTargetPlayers:20,offset})});
    let job=started.job;if(!job?.id)throw new Error('SEED_SCOUT_JOB_START_INVALID');
    for(;;){
      const attempts=Array.isArray(job.attempts)?job.attempts:[],last=attempts.length?attempts[attempts.length-1]:null;
      title.textContent=¤SEED SCOUT V6.19.3 · ${String(job.phase||job.status||'').toUpperCase()}¤;
      meta.textContent=last?¤Essai ${job.candidateIndex||attempts.length}/${job.candidates?.length||'?'} · serveur ${last.candidateServer} · ${fmt(last.playersDecoded||0)} joueurs décodés · ${fmt(last.targetPlayers||0)} sur cible¤:¤Préparation · région ${(Number(job.region)||0)+1}/9¤;
      if(job.status==='SUCCESS'){
        const seed=job.recommendedSeed||null;
        if(seed?.command){
          saveSeedScoutOffsetV6193(0);
          $('q').value=String(seed.command);
          note.textContent=¤Seed trouvée : serveur ${seed.serverId} · ${fmt(seed.players||0)} joueurs sur 1 région. La commande ${seed.command} est prête ; appuie sur RECHERCHER pour lancer le scan 9/9.¤;
          setStatus('NOUVELLE SEED TROUVÉE',String(seed.command),'ok');tone(980,.07,.03);setTimeout(()=>tone(1320,.09,.025),90);
        }else{
          const next=Math.max(Number(job.nextOffset||0),seedScoutOffsetV6193()+attempts.length);
          saveSeedScoutOffsetV6193(next);
          note.textContent=¤Batch terminé sans seed · ${attempts.length} serveur(s) testés · prochain batch à partir de l’offset ${next} · aucun cycle Collector créé. Relance DÉCOUVRIR pour continuer.¤;
          setStatus('SEED SCOUT TERMINÉ',¤Aucune seed · prochain offset ${next}¤,'error');
        }
        return;
      }
      if(job.status==='FAILED')throw new Error(String(job.phase||'SEED_SCOUT_FAILED'));
      await sleep(2000);
      const d=await api('/api/radar/seed-scout/status?id='+encodeURIComponent(job.id));
      job=d.job;if(!job)throw new Error('SEED_SCOUT_JOB_STATUS_INVALID');
    }
  }catch(err){
    if(err.status===401){login.classList.add('show');setStatus('SESSION REQUISE','Connecte le Radar avant Seed Scout','error')}
    else if(isLastWarAuthError(err)){showReauthRequired(err.message)}
    else setStatus('SEED SCOUT IMPOSSIBLE',String(err.message||err),'error');
    note.textContent='Seed Scout interrompu : '+String(err.message||err);
  }finally{b.disabled=false}
}
'''.replace('¤', chr(96))
text = text.replace(js_anchor, js + js_anchor, 1)

hook_anchor = "$('logoutRadar').onclick=async()=>"
if text.count(hook_anchor) != 1:
    raise SystemExit(f'V6193_UI_HOOK_ANCHOR_COUNT={text.count(hook_anchor)}')
text = text.replace(hook_anchor, "$('seedScout').onclick=runSeedScoutV6193;\n" + hook_anchor, 1)

UI.write_text(text, encoding='utf-8')
print('RADAR_V6193_SEED_SCOUT_UI=PATCHED')
