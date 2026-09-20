#!/usr/bin/env python3
from pathlib import Path

UI = Path('/tmp/wfgg-radar/public/live-radar.html')
text = UI.read_text(encoding='utf-8')

if 'WFGG_RADAR_AUTOPILOT_UI_V6194' in text:
    print('RADAR_V6194_AUTOPILOT_UI=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = '''  <div id="seedScoutNote" class="profile-note">Seed Scout V6.19.3 · 1 région par serveur · aucune écriture Collector.</div>
'''
if text.count(anchor) != 1:
    raise SystemExit(f'V6194_UI_PANEL_ANCHOR_COUNT={text.count(anchor)}')
addition = anchor + '''  <!-- WFGG_RADAR_AUTOPILOT_UI_V6194 -->
  <div class="federated-live show" id="autopilotPanel">
    <span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.4 · ARRÊTÉ</span>
    <span id="autopilotMeta" class="federated-meta">3 cycles 9/9 par grappe · Seed Scout automatique · fonctionne téléphone verrouillé.</span>
  </div>
  <div class="profile-actions">
    <button id="autopilotStart" class="profile-refresh" type="button">DÉMARRER L’AUTOPILOT</button>
    <button id="autopilotStop" class="profile-refresh" type="button" disabled>ARRÊTER L’AUTOPILOT</button>
  </div>
  <div id="autopilotNote" class="profile-note">READ-ONLY côté Last War · les cycles complets mettent à jour le Collector. Les cycles partiels ne comptent pas.</div>
'''
text = text.replace(anchor, addition, 1)

js_anchor = 'async function health(){'
if text.count(js_anchor) != 1:
    raise SystemExit(f'V6194_UI_JS_ANCHOR_COUNT={text.count(js_anchor)}')
js = r'''/* WFGG_RADAR_AUTOPILOT_UI_V6194 */
const WFGG_RADAR_AUTOPILOT_JOB_KEY='wfgg_radar_autopilot_job_v6194';
let autopilotPollTimer=null;
function savedAutopilotJobV6194(){try{return String(localStorage.getItem(WFGG_RADAR_AUTOPILOT_JOB_KEY)||'')}catch(_){return ''}}
function saveAutopilotJobV6194(id){try{if(id)localStorage.setItem(WFGG_RADAR_AUTOPILOT_JOB_KEY,String(id));else localStorage.removeItem(WFGG_RADAR_AUTOPILOT_JOB_KEY)}catch(_){}}
function currentFederatedSeedV6194(){const m=String($('q')?.value||'').trim().match(/^@federated:(?:APS)?(\d+)$/i);return m?m[1]:''}
function autopilotTerminalV6194(job){return ['SUCCESS','FAILED'].includes(String(job?.status||'').toUpperCase())}
function renderAutopilotV6194(payload){
  const job=payload?.job||payload||{},cycle=payload?.currentCycleJob||null,scout=payload?.currentScoutJob||null;
  const title=$('autopilotTitle'),meta=$('autopilotMeta'),note=$('autopilotNote'),start=$('autopilotStart'),stop=$('autopilotStop');
  const status=String(job.status||'—').toUpperCase(),phase=String(job.phase||'—').toUpperCase(),seed=String(job.currentSeed||'—');
  title.textContent=`AUTOPILOT V6.19.4 · ${status} · ${phase}`;
  let progress=`Grappe ${Number(job.confirmedClusters||0)+1}/${job.maxClusters||5} · seed ${seed} · cycles 9/9 ${job.validatedCycles||0}/${job.requiredFullCycles||3} · partiels ${job.partialCycles||0}`;
  if(cycle){
    progress+=` · cycle ${cycle.cycleId||'—'} · régions ${cycle.regionsCompleted||0}/9`;
    if(Number(cycle.regionsFailed||0)>0)progress+=` · isolées ${cycle.regionsFailed}`;
  }else if(scout){
    progress+=` · Seed Scout batch ${job.scoutBatch||1} · essai ${scout.candidateIndex||0}/${scout.candidates?.length||'?'}`;
  }
  meta.textContent=progress;
  if(job.lastCycle?.classification==='PARTIAL')note.textContent=`Dernier cycle partiel ${job.lastCycle.regionsCompleted||0}/9 : conservé mais NON compté. Relance automatique de ${job.currentCommand||'la même seed'}.`;
  else if(phase==='CLUSTER_CONFIRMED')note.textContent='Grappe confirmée sur 3 cycles complets · recherche automatique de la seed suivante.';
  else if(phase==='STOP_REQUESTED_AFTER_CURRENT_STEP')note.textContent='Arrêt demandé · le cycle/Seed Scout en cours se termine puis Autopilot s’arrête.';
  else if(status==='FAILED')note.textContent='Autopilot arrêté sur garde-fou : '+String(job.lastError||phase);
  else if(status==='SUCCESS')note.textContent='Autopilot terminé : '+phase;
  else note.textContent='Le traitement tourne sur le VPS : tu peux verrouiller le téléphone ou changer d’application.';
  const running=status==='RUNNING'||status==='QUEUED';
  start.disabled=running;
  stop.disabled=!running;
  if(autopilotTerminalV6194(job)){saveAutopilotJobV6194('');if(autopilotPollTimer){clearTimeout(autopilotPollTimer);autopilotPollTimer=null}}
}
async function pollAutopilotV6194(id){
  try{
    const d=await api('/api/radar/autopilot/status?id='+encodeURIComponent(id));
    renderAutopilotV6194(d);
    if(!autopilotTerminalV6194(d.job))autopilotPollTimer=setTimeout(()=>pollAutopilotV6194(id),2000);
  }catch(err){
    if(err.status===401){setStatus('AUTOPILOT · SESSION UI EXPIRÉE','Le traitement VPS peut continuer ; reconnecte-toi pour reprendre le suivi','error');return}
    if(err.status===404){saveAutopilotJobV6194('');renderAutopilotV6194({job:{status:'FAILED',phase:'JOB_NOT_FOUND',lastError:'AUTOPILOT_JOB_NOT_FOUND'}});return}
    autopilotPollTimer=setTimeout(()=>pollAutopilotV6194(id),5000);
  }
}
async function startAutopilotV6194(){
  const b=$('autopilotStart');b.disabled=true;
  try{
    const initialSeed=currentFederatedSeedV6194();
    const d=await api('/api/radar/autopilot/start',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({initialSeed,fullCyclesPerCluster:3,maxClusters:5})});
    const id=String(d.job?.id||'');if(!id)throw new Error('AUTOPILOT_JOB_START_INVALID');
    saveAutopilotJobV6194(id);renderAutopilotV6194(d);setStatus('AUTOPILOT DÉMARRÉ',initialSeed?`Seed ${initialSeed} · preuve fraîche 3×9/9`:'Seed Scout automatique','ok');
    pollAutopilotV6194(id);
  }catch(err){
    b.disabled=false;
    if(err.status===401){login.classList.add('show');setStatus('SESSION REQUISE','Connecte le Radar avant Autopilot','error')}
    else if(isLastWarAuthError(err)){showReauthRequired(err.message)}
    else setStatus('AUTOPILOT IMPOSSIBLE',String(err.message||err),'error');
  }
}
async function stopAutopilotV6194(){
  const id=savedAutopilotJobV6194();if(!id)return;
  const b=$('autopilotStop');b.disabled=true;
  try{
    const d=await api('/api/radar/autopilot/stop',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({id})});
    renderAutopilotV6194(d);setStatus('ARRÊT AUTOPILOT DEMANDÉ','Arrêt après l’étape en cours','ok');
  }catch(err){setStatus('ARRÊT AUTOPILOT IMPOSSIBLE',String(err.message||err),'error');b.disabled=false}
}
function resumeAutopilotV6194(){const id=savedAutopilotJobV6194();if(id)pollAutopilotV6194(id)}
'''
text = text.replace(js_anchor, js + js_anchor, 1)

hook_anchor = "$('seedScout').onclick=runSeedScoutV6193;\n"
if text.count(hook_anchor) != 1:
    raise SystemExit(f'V6194_UI_HOOK_ANCHOR_COUNT={text.count(hook_anchor)}')
text = text.replace(hook_anchor, hook_anchor + "$('autopilotStart').onclick=startAutopilotV6194;\n$('autopilotStop').onclick=stopAutopilotV6194;\n", 1)

tail_anchor = 'health();session();\n'
if text.count(tail_anchor) != 1:
    raise SystemExit(f'V6194_UI_RESUME_ANCHOR_COUNT={text.count(tail_anchor)}')
text = text.replace(tail_anchor, "health();session();resumeAutopilotV6194();\n", 1)

UI.write_text(text, encoding='utf-8')
print('RADAR_V6194_AUTOPILOT_UI=PATCHED')
