#!/usr/bin/env python3
from pathlib import Path

p = Path('/tmp/wfgg-radar/public/live-radar.html')
s = p.read_text()

if '/api/radar/search/start' in s:
    print('RADAR_LIVE_ASYNC_PATCH=ALREADY_PRESENT')
    raise SystemExit(0)

s = s.replace(
    '.steps{display:flex;gap:6px;margin-top:12px}',
    '.progress-text{margin-top:9px;min-height:16px;text-align:center;color:#9fbc84;font-size:10px;letter-spacing:.05em}.steps{display:flex;gap:6px;margin-top:8px}',
    1,
)
s = s.replace(
    '<div class="steps"><i id="s1" class="step"></i><i id="s2" class="step"></i><i id="s3" class="step"></i><i id="s4" class="step"></i></div>',
    '<div id="progressText" class="progress-text">RADAR PRÊT</div><div class="steps"><i id="s1" class="step"></i><i id="s2" class="step"></i><i id="s3" class="step"></i><i id="s4" class="step"></i></div>',
    1,
)
s = s.replace('LIVE API /api/radar/search</span>', 'COLLECTOR V4 · LIVE</span>', 1)

old_status = "function setStatus(main,sub='',kind=''){$('statusMain').textContent=main;$('statusMain').className='status-main '+kind;$('statusSub').textContent=sub}"
new_status = "function setStatus(main,sub='',kind=''){$('statusMain').textContent=main;$('statusMain').className='status-main '+kind;$('statusSub').textContent=sub;const p=$('progressText');if(p){p.textContent=sub?main+' · '+sub:main;p.className='progress-text '+kind}}"
if old_status not in s:
    raise SystemExit('RADAR_LIVE_STATUS_ANCHOR_MISSING')
s = s.replace(old_status, new_status, 1)

old_start = "function startScan(q){screen.classList.remove('found');screen.classList.add('scanning');target.classList.remove('hit');result.classList.remove('show');go.disabled=true;steps(1);setStatus('SYNCHRONISATION RADAR',q);tone(420,.04,.018);let p=0;clearInterval(phaseTimer);const labels=[['LECTURE DE LA CARTE','Balayage des secteurs…'],['ANALYSE DES DELTAS','Comparaison de l’état connu…'],['ENRICHISSEMENT PROFIL','Consolidation des données…']];phaseTimer=setInterval(()=>{const x=labels[p++%labels.length];steps(Math.min(3,p+1));setStatus(x[0],x[1]);tone(520+p*60,.025,.012)},1100)}"
new_start = "function startScan(q){screen.classList.remove('found');screen.classList.add('scanning');target.classList.remove('hit');result.classList.remove('show');go.disabled=true;steps(1);setStatus('DÉMARRAGE DU CYCLE',q);tone(420,.04,.018);clearInterval(phaseTimer)}"
if old_start not in s:
    raise SystemExit('RADAR_LIVE_STARTSCAN_ANCHOR_MISSING')
s = s.replace(old_start, new_start, 1)

insert_after = "function stopScan(){clearInterval(phaseTimer);screen.classList.remove('scanning');go.disabled=false}"
addition = r'''
function sleep(ms){return new Promise(r=>setTimeout(r,ms))}
function renderJob(job){if(!job)return;const phase=String(job.phase||job.status||'').toUpperCase();if(phase==='QUEUED'||phase==='STARTING'){steps(1);setStatus('DÉMARRAGE DU CYCLE','Préparation du Collector…');return}if(phase==='WAITING_FOR_CYCLE'){steps(1);setStatus('CYCLE DÉJÀ EN COURS','La recherche rejoint l’actualisation active…');return}if(phase==='MAP'){steps(2);setStatus('ACTUALISATION DE LA CARTE',`Région ${job.region||0}/${job.regions||9} · ${fmt(job.playersSeen||0)} observations`);return}if(phase==='ENRICHING'){steps(3);setStatus('MISE À JOUR DES PROFILS',`${fmt(job.enriched||0)} / ${fmt(job.candidates||0)}`);return}if(phase==='FINALIZING'){steps(3);setStatus('FINALISATION','Validation de l’incrément…');return}if(phase==='DONE'||job.status==='SUCCESS'){steps(4);setStatus('CYCLE TERMINÉ','Base Collector actualisée','ok');return}if(phase==='FAILED'||job.status==='FAILED'){steps(4);setStatus('CYCLE INTERROMPU',job.error||'Erreur Collector','error')}}
async function runCollectorSearch(q){const started=await api('/api/radar/search/start',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({q})});let job=started.job;if(!job?.id)throw new Error('COLLECTOR_JOB_START_INVALID');for(;;){renderJob(job);if(job.status==='SUCCESS')return {job,player:job.player||null};if(job.status==='FAILED')throw new Error(job.error||'COLLECTOR_SEARCH_FAILED');await sleep(2000);const d=await api('/api/radar/search/status?id='+encodeURIComponent(job.id));job=d.job;if(!job)throw new Error('COLLECTOR_JOB_STATUS_INVALID')}}'''
if insert_after not in s:
    raise SystemExit('RADAR_LIVE_STOPSCAN_ANCHOR_MISSING')
s = s.replace(insert_after, insert_after + addition, 1)

old_player = "function playerFrom(data){if(!data)return null;const arr=Array.isArray(data.results)?data.results:Array.isArray(data.players)?data.players:[];return arr[0]||data.player||data.result||null}"
new_player = "function playerFrom(data){if(!data)return null;if(data.job?.player)return data.job.player;const arr=Array.isArray(data.results)?data.results:Array.isArray(data.players)?data.players:[];return arr[0]||data.player||data.result||null}"
if old_player not in s:
    raise SystemExit('RADAR_LIVE_PLAYERFROM_ANCHOR_MISSING')
s = s.replace(old_player, new_player, 1)

old_show_tail = "const live=data?.liveScan;$('rsource').textContent=live?.attempted?(live.status==='ok'?'LIVE SCAN':'CACHE + LIVE'):'RADAR CACHE';$('rraw').textContent=`Résultats: ${Array.isArray(data?.results)?data.results.length:1}${live?.status?' · live='+live.status:''}`;locate(p);result.classList.add('show');steps(4);setStatus('CIBLE LOCALISÉE',name,'ok');tone(980,.07,.03);setTimeout(()=>tone(1320,.09,.025),90)"
new_show_tail = "const job=data?.job;$('rsource').textContent=job?'COLLECTOR V4':'RADAR';$('rraw').textContent=job?`Cycle ${job.cycleId||'—'} · ${job.joined?'rejoint':'complet'} · ${fmt(job.playersSeen||0)} observations · ${fmt(job.enriched||0)} profils`:'Résultat Radar';locate(p);result.classList.add('show');steps(4);setStatus('CIBLE LOCALISÉE',name,'ok');tone(980,.07,.03);setTimeout(()=>tone(1320,.09,.025),90)"
if old_show_tail not in s:
    raise SystemExit('RADAR_LIVE_SHOWPLAYER_ANCHOR_MISSING')
s = s.replace(old_show_tail, new_show_tail, 1)

old_submit = "$('searchForm').onsubmit=async e=>{e.preventDefault();const q=$('q').value.trim();if(!q)return;startScan(q);try{const d=await api('/api/radar/search?q='+encodeURIComponent(q)+'&limit=50');const p=playerFrom(d);stopScan();if(p)showPlayer(p,d,q);else{screen.classList.remove('found');steps(4);setStatus('AUCUNE CIBLE',`« ${q} » non trouvé`,'error');$('rname').textContent=q;$('rserver').textContent=$('ralliance').textContent=$('rhq').textContent=$('rpower').textContent=$('rpos').textContent=$('ruid').textContent='—';$('rsource').textContent=d.liveScan?.attempted?'LIVE SCAN':'RADAR';$('rraw').textContent=d.liveScan?.error?`Live: ${d.liveScan.error}`:'Aucun résultat';result.classList.add('show');tone(180,.14,.02)}}catch(err){stopScan();screen.classList.remove('found');if(err.status===401){login.classList.add('show');setStatus('SESSION REQUISE','Connecte le Radar puis relance la recherche','error')}else setStatus('ERREUR RADAR',err.message,'error')}};"
new_submit = "$('searchForm').onsubmit=async e=>{e.preventDefault();const q=$('q').value.trim();if(!q)return;startScan(q);try{const d=await runCollectorSearch(q);const p=playerFrom(d);stopScan();if(p)showPlayer(p,d,q);else{screen.classList.remove('found');steps(4);setStatus('AUCUNE CIBLE',`« ${q} » non trouvé`,'error');$('rname').textContent=q;$('rserver').textContent=$('ralliance').textContent=$('rhq').textContent=$('rpower').textContent=$('rpos').textContent=$('ruid').textContent='—';$('rsource').textContent='COLLECTOR V4';$('rraw').textContent=`Cycle ${d.job?.cycleId||'—'} terminé · aucun joueur correspondant`;result.classList.add('show');tone(180,.14,.02)}}catch(err){stopScan();screen.classList.remove('found');if(err.status===401){login.classList.add('show');setStatus('SESSION REQUISE','Connecte le Radar puis relance la recherche','error')}else setStatus('ERREUR RADAR',err.message,'error')}};"
if old_submit not in s:
    raise SystemExit('RADAR_LIVE_SUBMIT_ANCHOR_MISSING')
s = s.replace(old_submit, new_submit, 1)

p.write_text(s)
print('RADAR_LIVE_ASYNC_PATCH=APPLIED')
