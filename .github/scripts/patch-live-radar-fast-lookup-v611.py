#!/usr/bin/env python3
from pathlib import Path
import shutil

SRC = Path('radar-ui-live/live-radar.html')
TMP = Path('/tmp/wfgg-radar/public/live-radar.html')

if not SRC.is_file():
    raise SystemExit('RADAR_V611_LIVE_SOURCE_MISSING')

s = SRC.read_text(encoding='utf-8')
if 'WFGG_RADAR_FAST_LOOKUP_UI_V611' in s:
    print('RADAR_V611_UI=ALREADY_PRESENT')
    raise SystemExit(0)

old_start = "function startScan(q){screen.classList.remove('found');screen.classList.add('scanning');target.classList.remove('hit');result.classList.remove('show');go.disabled=true;steps(1);setStatus('DÉMARRAGE DU CYCLE',q);tone(420,.04,.018);clearInterval(phaseTimer)}"
new_start = "function startScan(q){screen.classList.remove('found');screen.classList.add('scanning');target.classList.remove('hit');result.classList.remove('show');go.disabled=true;steps(1);setStatus('RECHERCHE INDEXÉE',q);tone(420,.04,.018);clearInterval(phaseTimer)}"
if old_start not in s:
    raise SystemExit('RADAR_V611_STARTSCAN_ANCHOR_MISSING')
s = s.replace(old_start, new_start, 1)

old_tail = "const job=data?.job;$('rsource').textContent=job?'COLLECTOR V4':'RADAR';$('rraw').textContent=job?`Cycle ${job.cycleId||'—'} · ${job.joined?'rejoint':'complet'} · ${fmt(job.playersSeen||0)} observations · ${fmt(job.enriched||0)} profils`:'Résultat Radar';locate(p);result.classList.add('show');steps(4);setStatus('CIBLE LOCALISÉE',name,'ok');tone(980,.07,.03);setTimeout(()=>tone(1320,.09,.025),90)"
new_tail = "const fast=data?.fastLookup;const src=fast?.status==='d1-hit'?'CACHE LOCAL':fast?.status==='exact-hit'?'INDEX IDENTITÉ':fast?.status==='fuzzy-hit'?'INDEX COLLECTOR':'RADAR';$('rsource').textContent=src;$('rraw').textContent=fast?.elapsedMs!=null?`${fast.route||fast.status} · ${fast.elapsedMs} ms`:(fast?.route||'Résultat local');locate(p);result.classList.add('show');steps(4);setStatus('CIBLE LOCALISÉE',name,'ok');tone(980,.07,.03);setTimeout(()=>tone(1320,.09,.025),90)"
if old_tail not in s:
    raise SystemExit('RADAR_V611_SHOWPLAYER_ANCHOR_MISSING')
s = s.replace(old_tail, new_tail, 1)

old_submit = "$('searchForm').onsubmit=async e=>{e.preventDefault();const q=$('q').value.trim();if(!q)return;startScan(q);try{const d=await runCollectorSearch(q);const p=playerFrom(d);stopScan();if(p)showPlayer(p,d,q);else{screen.classList.remove('found');steps(4);setStatus('AUCUNE CIBLE',`« ${q} » non trouvé`,'error');$('rname').textContent=q;$('rserver').textContent=$('ralliance').textContent=$('rhq').textContent=$('rpower').textContent=$('rpos').textContent=$('ruid').textContent='—';$('rsource').textContent='COLLECTOR V4';$('rraw').textContent=`Cycle ${d.job?.cycleId||'—'} terminé · aucun joueur correspondant`;result.classList.add('show');tone(180,.14,.02)}}catch(err){stopScan();screen.classList.remove('found');if(err.status===401){login.classList.add('show');setStatus('SESSION REQUISE','Connecte le Radar puis relance la recherche','error')}else setStatus('ERREUR RADAR',err.message,'error')}};"
new_submit = "/* WFGG_RADAR_FAST_LOOKUP_UI_V611 */$('searchForm').onsubmit=async e=>{e.preventDefault();const q=$('q').value.trim();if(!q)return;startScan(q);setStatus('RECHERCHE INDEXÉE','Pseudo → UID → fiche locale');try{const d=await api('/api/radar/search?q='+encodeURIComponent(q)+'&limit=50');const p=playerFrom(d);stopScan();if(p)showPlayer(p,d,q);else{screen.classList.remove('found');steps(4);const fast=d?.fastLookup||{};const ambiguous=fast.status==='ambiguous';setStatus(ambiguous?'PSEUDO AMBIGU':'AUCUNE CIBLE',ambiguous?`${fast.candidateCount||0} correspondance(s) · précise le serveur ou l’UID`:`« ${q} » absent de l’index local`,'error');$('rname').textContent=q;$('rserver').textContent=$('ralliance').textContent=$('rhq').textContent=$('rpower').textContent=$('rpos').textContent=$('ruid').textContent='—';$('rsource').textContent=ambiguous?'INDEX IDENTITÉ':'INDEX LOCAL';$('rraw').textContent=fast.elapsedMs!=null?`${fast.route||fast.status} · ${fast.elapsedMs} ms`:(fast.route||'Aucun résultat');result.classList.add('show');tone(180,.14,.02)}}catch(err){stopScan();screen.classList.remove('found');if(err.status===401){login.classList.add('show');setStatus('SESSION REQUISE','Connecte le Radar puis relance la recherche','error')}else setStatus('ERREUR RADAR',err.message,'error')}};"
if old_submit not in s:
    raise SystemExit('RADAR_V611_SUBMIT_ANCHOR_MISSING')
s = s.replace(old_submit, new_submit, 1)

SRC.write_text(s, encoding='utf-8')
if TMP.parent.is_dir():
    shutil.copyfile(SRC, TMP)
print('RADAR_FAST_LOOKUP_UI_V611=READY')
