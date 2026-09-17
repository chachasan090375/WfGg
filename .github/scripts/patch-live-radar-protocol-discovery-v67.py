#!/usr/bin/env python3
from pathlib import Path

P = Path('/tmp/wfgg-radar/public/live-radar.html')
if not P.is_file():
    raise SystemExit('RADAR_V67_LIVE_UI_MISSING')
text = P.read_text(encoding='utf-8')
if 'WFGG_RADAR_PROTOCOL_DISCOVERY_UI_V67' in text:
    print('RADAR_V67_UI=ALREADY_PRESENT')
    raise SystemExit(0)

old = "meta.textContent=failed?`${done}/${job.regions||9} régions OK · ${failed} isolée(s) · première R${first?.region||'?'} ${first?.cause||first?.code||'ERREUR'} · ${fmt(p.decoded||job.playersSeen||0)} décodés`:`${fmt(p.regions||job.regions||0)}/9 régions · ${fmt(p.decoded||job.playersSeen||0)} décodés · ${fmt(p.uniqueUIDs||0)} UID uniques · ${fmt(p.accepted||job.enriched||0)} intégrés`"
new = "/* WFGG_RADAR_PROTOCOL_DISCOVERY_UI_V67 */const rd=Array.isArray(job.regionDiagnostics)?job.regionDiagnostics:[];const sums=rd.reduce((a,d)=>{a.req+=Number(d.requests||0);a.pkt+=Number(d.packets||0);a.city+=Number(d.playerCities||0);a.dec+=Number(d.playersDecoded||0);a.match+=Number(d.queryMatches||0);a.err+=Number(d.decodeErrors||0);return a},{req:0,pkt:0,city:0,dec:0,match:0,err:0});const proto=`PROTO V6.7 · ${rd.length||0} origines · ${fmt(sums.req)} req · ${fmt(sums.pkt)} paquets · ${fmt(sums.city)} villes · ${fmt(sums.dec)} décodés`;meta.textContent=failed?`${done}/${job.regions||9} régions OK · ${failed} isolée(s) · première R${first?.region||'?'} ${first?.cause||first?.code||'ERREUR'} · ${proto}`:`${fmt(p.regions||job.regions||0)}/9 régions · ${fmt(p.decoded||job.playersSeen||0)} intégrables · ${proto}`"
if old not in text:
    raise SystemExit('RADAR_V67_UI_FEDERATED_ANCHOR_MISSING')
text = text.replace(old, new, 1)

old2 = "if(p)showPlayer(p,d,q);else{screen.classList.remove('found');steps(4);setStatus('AUCUNE CIBLE',`« ${q} » non trouvé`,'error');$('rname').textContent=q;$('rserver').textContent=$('ralliance').textContent=$('rhq').textContent=$('rpower').textContent=$('rpos').textContent=$('ruid').textContent='—';$('rsource').textContent='COLLECTOR V4';$('rraw').textContent=`Cycle ${d.job?.cycleId||'—'} terminé · aucun joueur correspondant`;result.classList.add('show');tone(180,.14,.02)}"
new2 = "if(p)showPlayer(p,d,q);else if(/^@federated:(?:APS)?\\d+/i.test(q)){screen.classList.remove('found');result.classList.remove('show');steps(4);/* le panneau fédéré est le résultat, pas une fiche joueur */}else{screen.classList.remove('found');steps(4);setStatus('AUCUNE CIBLE',`« ${q} » non trouvé`,'error');$('rname').textContent=q;$('rserver').textContent=$('ralliance').textContent=$('rhq').textContent=$('rpower').textContent=$('rpos').textContent=$('ruid').textContent='—';$('rsource').textContent='COLLECTOR V4';$('rraw').textContent=`Cycle ${d.job?.cycleId||'—'} terminé · aucun joueur correspondant`;result.classList.add('show');tone(180,.14,.02)}"
if old2 not in text:
    raise SystemExit('RADAR_V67_UI_RESULT_ANCHOR_MISSING')
text = text.replace(old2, new2, 1)
P.write_text(text, encoding='utf-8')
print('RADAR_V67_UI=PATCHED')
print('RADAR_V67_FALSE_PLAYER_NOT_FOUND=SUPPRESSED')
