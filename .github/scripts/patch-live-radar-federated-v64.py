#!/usr/bin/env python3
from pathlib import Path

p = Path('/tmp/wfgg-radar/public/live-radar.html')
s = p.read_text(encoding='utf-8')
marker = 'WFGG_RADAR_FEDERATED_PROGRESS_V64'
if marker in s:
    print('RADAR_FEDERATED_PROGRESS=ALREADY_PRESENT')
    raise SystemExit(0)

css = r'''
/* WFGG_RADAR_FEDERATED_PROGRESS_V64 */
.federated-live{display:none;margin:10px 5px 0;padding:10px 12px;border:1px solid #42623a;border-radius:12px;background:#081108}.federated-live.show{display:block}.federated-live.error{border-color:#7d3a30;background:#1d0d0a}.federated-title{display:block;color:#c7f3a6;font:900 10px ui-monospace,monospace;letter-spacing:.05em}.federated-meta{display:block;margin-top:5px;color:#8fa787;font:10px ui-monospace,monospace}.federated-live.error .federated-title,.federated-live.error .federated-meta{color:#ff9b89}
'''
if '</style>' not in s:
    raise SystemExit('RADAR_FEDERATED_STYLE_ANCHOR_MISSING')
s = s.replace('</style>', css + '</style>', 1)

anchor = '<div id="authExpired" class="auth-expired">'
if anchor not in s:
    raise SystemExit('RADAR_FEDERATED_HTML_ANCHOR_MISSING')
panel = '''<div id="federatedLive" class="federated-live"><span id="federatedTitle" class="federated-title">COLLECTOR FÉDÉRÉ · EN ATTENTE</span><span id="federatedMeta" class="federated-meta">Aucun cycle actif.</span></div>\n  '''
s = s.replace(anchor, panel + anchor, 1)

old = "function renderJob(job){if(!job)return;const phase=String(job.phase||job.status||'').toUpperCase();if(phase==='QUEUED'||phase==='STARTING'){steps(1);setStatus('DÉMARRAGE DU CYCLE','Préparation du Collector…');return}if(phase==='WAITING_FOR_CYCLE'){steps(1);setStatus('CYCLE DÉJÀ EN COURS','La recherche rejoint l’actualisation active…');return}if(phase==='MAP'){steps(2);setStatus('ACTUALISATION DE LA CARTE',`Région ${job.region||0}/${job.regions||9} · ${fmt(job.playersSeen||0)} observations`);return}if(phase==='ENRICHING'){steps(3);setStatus('MISE À JOUR DES PROFILS',`${fmt(job.enriched||0)} / ${fmt(job.candidates||0)}`);return}if(phase==='FINALIZING'){steps(3);setStatus('FINALISATION','Validation de l’incrément…');return}if(phase==='DONE'||job.status==='SUCCESS'){steps(4);setStatus('CYCLE TERMINÉ','Base Collector actualisée','ok');return}if(phase==='FAILED'||job.status==='FAILED'){steps(4);setStatus('CYCLE INTERROMPU',job.error||'Erreur Collector','error')}}"
new = r'''function renderJob(job){if(!job)return;const phase=String(job.phase||job.status||'').toUpperCase();const box=$('federatedLive'),title=$('federatedTitle'),meta=$('federatedMeta');const q=String(job.query||$('q')?.value||'');const m=q.match(/^@federated:(?:APS)?(\d+)/i);if(m&&box){box.classList.add('show');box.classList.toggle('error',job.status==='FAILED');if(phase==='FEDERATED_MAP'){title.textContent=`COLLECTOR FÉDÉRÉ · SERVEUR ${m[1]} · RÉGION ${job.region||0}/${job.regions||9}`;meta.textContent=`${fmt(job.playersSeen||0)} joueurs décodés · ${fmt(job.enriched||0)} intégrés`}else if(job.status==='SUCCESS'){const p=job.player||{};title.textContent=`COLLECTOR FÉDÉRÉ · SERVEUR ${m[1]} · TERMINÉ`;meta.textContent=`${fmt(p.regions||job.regions||0)}/9 régions · ${fmt(p.decoded||job.playersSeen||0)} décodés · ${fmt(p.uniqueUIDs||0)} UID uniques · ${fmt(p.accepted||job.enriched||0)} intégrés`}else if(job.status==='FAILED'){title.textContent=`COLLECTOR FÉDÉRÉ · SERVEUR ${m[1]} · ÉCHEC`;meta.textContent=job.error||'Erreur Collector'}else{title.textContent=`COLLECTOR FÉDÉRÉ · SERVEUR ${m[1]}`;meta.textContent=`Phase ${phase||'—'} · région ${job.region||0}/${job.regions||9}`}}if(phase==='QUEUED'||phase==='STARTING'){steps(1);setStatus('DÉMARRAGE DU CYCLE','Préparation du Collector…');return}if(phase==='WAITING_FOR_CYCLE'){steps(1);setStatus('CYCLE DÉJÀ EN COURS','La recherche rejoint l’actualisation active…');return}if(phase==='FEDERATED_MAP'){steps(2);setStatus('COLLECTOR FÉDÉRÉ',`Serveur ${m?.[1]||'—'} · région ${job.region||0}/${job.regions||9} · ${fmt(job.playersSeen||0)} joueurs`);return}if(phase==='MAP'){steps(2);setStatus('ACTUALISATION DE LA CARTE',`Région ${job.region||0}/${job.regions||9} · ${fmt(job.playersSeen||0)} observations`);return}if(phase==='ENRICHING'){steps(3);setStatus('MISE À JOUR DES PROFILS',`${fmt(job.enriched||0)} / ${fmt(job.candidates||0)}`);return}if(phase==='FINALIZING'){steps(3);setStatus('FINALISATION','Validation de l’incrément…');return}if(phase==='DONE'||job.status==='SUCCESS'){steps(4);setStatus('CYCLE TERMINÉ','Base Collector actualisée','ok');return}if(phase==='FEDERATED_V63_FAILED'||phase==='FAILED'||job.status==='FAILED'){steps(4);setStatus('CYCLE INTERROMPU',job.error||'Erreur Collector','error')}}'''
if old not in s:
    raise SystemExit('RADAR_FEDERATED_RENDER_ANCHOR_MISSING')
s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
print('RADAR_FEDERATED_PROGRESS=PATCHED')
