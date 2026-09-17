#!/usr/bin/env python3
from pathlib import Path

P = Path('/tmp/wfgg-radar/public/live-radar.html')
if not P.is_file():
    raise SystemExit('RADAR_V68_LIVE_UI_MISSING')
text = P.read_text(encoding='utf-8')
if 'WFGG_RADAR_PROFILE_ISOLATION_UI_V68' in text:
    print('RADAR_V68_UI=ALREADY_PRESENT')
    raise SystemExit(0)

old = "const proto=`PROTO V6.7 · ${rd.length||0} origines · ${fmt(sums.req)} req · ${fmt(sums.pkt)} paquets · ${fmt(sums.city)} villes · ${fmt(sums.dec)} décodés`;meta.textContent=failed?`${done}/${job.regions||9} régions OK · ${failed} isolée(s) · première R${first?.region||'?'} ${first?.cause||first?.code||'ERREUR'} · ${proto}`:`${fmt(p.regions||job.regions||0)}/9 régions · ${fmt(p.decoded||job.playersSeen||0)} intégrables · ${proto}`"
new = "const proto=`PROTO V6.7 · ${rd.length||0} origines · ${fmt(sums.req)} req · ${fmt(sums.pkt)} paquets · ${fmt(sums.city)} villes · ${fmt(sums.dec)} décodés`;/* WFGG_RADAR_PROFILE_ISOLATION_UI_V68 */const ps=job.profileStats||{};const pf=Array.isArray(ps.failures)&&ps.failures.length?ps.failures[0]:null;const prof=`PROF V6.8 · ${String(ps.status||'—')} · ${fmt(ps.profilesResolved||0)}/${fmt(ps.requested||job.candidates||0)} résolus · ${fmt(ps.attempts||0)} essais · ${fmt(ps.batchesFailed||0)} lots KO${pf?` · ${pf.code}`:''}`;meta.textContent=failed?`${done}/${job.regions||9} régions OK · ${failed} isolée(s) · première R${first?.region||'?'} ${first?.cause||first?.code||'ERREUR'} · ${proto} · ${prof}`:`${fmt(p.regions||job.regions||0)}/9 régions · ${fmt(p.decoded||job.playersSeen||0)} intégrables · ${proto} · ${prof}`"
if old not in text:
    raise SystemExit('RADAR_V68_UI_SUCCESS_ANCHOR_MISSING')
text = text.replace(old, new, 1)

old2 = "if(phase==='ENRICHING'){steps(3);setStatus('MISE À JOUR DES PROFILS',`${fmt(job.enriched||0)} / ${fmt(job.candidates||0)}`);return}"
new2 = "if(phase==='ENRICHING'){steps(3);const ps=job.profileStats||{};setStatus('MISE À JOUR DES PROFILS',`V6.8 · ${fmt(ps.profilesResolved||job.enriched||0)} / ${fmt(ps.requested||job.candidates||0)} · ${fmt(ps.attempts||0)} essais`);return}"
if old2 not in text:
    raise SystemExit('RADAR_V68_UI_ENRICH_ANCHOR_MISSING')
text = text.replace(old2, new2, 1)

P.write_text(text, encoding='utf-8')
print('RADAR_V68_UI=PATCHED')
print('RADAR_V68_PROFILE_TELEMETRY=SAFE_AGGREGATES_ONLY')
