#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — exact hero icon extraction
# OFFLINE ONLY. Uses the proven Phase30B/30D Unity pipeline, but candidate discovery
# and image export are driven by the 31 authoritative internal icon object names
# decoded from lw_hero + lw_hero_appearance. No public-name guessing.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/scripts/lastwar-phase30b-node-payload-extraction.sh"
RUNNER="$ROOT/scripts/lastwar-phase30d-engine-version-discovery.sh"
MAP="$ROOT/frontend/lab/lastwar-hero-authoritative-map.js"
TMP="$ROOT/scripts/.lastwar-hero-icons-exact.$$"

cleanup(){ rm -f "$TMP"; }
trap cleanup EXIT

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
[[ -s "$BASE" ]] || die "Phase 30B introuvable: $BASE"
[[ -s "$RUNNER" ]] || die "Phase 30D introuvable: $RUNNER"
[[ -s "$MAP" ]] || die "mapping héros autoritatif introuvable: $MAP"
command -v python >/dev/null 2>&1 || die "python Termux absent"

cp "$BASE" "$TMP"

python - "$TMP" "$MAP" <<'PY'
from pathlib import Path
import re, sys
p=Path(sys.argv[1]); mp=Path(sys.argv[2])
s=p.read_text(encoding='utf-8')
m=mp.read_text(encoding='utf-8')

# Parse authoritative internal object refs only.
rows=[]
for mm in re.finditer(r"\{heroId:(\d+),name:'([^']+)'[^\n]*?queueIcon:'([^']+)'[^\n]*?halfIcon:'([^']+)'",m):
    hid=int(mm.group(1)); name=mm.group(2); q=mm.group(3); h=mm.group(4)
    rows.append((hid,name,q,h))
if len(rows)!=31:
    raise SystemExit(f'mapping autoritatif incomplet: {len(rows)}/31')

aliases=[]
for hid,name,q,h in rows:
    vals=[]
    for x in (q,h):
        low=x.lower()
        vals += [low]
        if low.startswith('hero_icon_'): vals.append(low[len('hero_icon_'):])
    vals=list(dict.fromkeys(v for v in vals if v))
    aliases.append(f' "{name}":'+repr(vals).replace("'",'"'))
hero_block='hero_aliases={\n'+',\n'.join(aliases)+'\n}'

start=s.index('hero_aliases={')
end=s.index('\nactive_names=',start)
s=s[:start]+hero_block+s[end:]

# Every authoritative hero is high priority; only exact icon objects are exportable.
names=', '.join(repr(name) for _,name,_,_ in rows)
s=re.sub(r'active_names=\{[^\n]*\}', 'active_names={'+names+'}', s, count=1)

# This pass should be narrow after candidate discovery.
s=s.replace('MAX_CANDIDATES_TO_LOAD=520','MAX_CANDIDATES_TO_LOAD=420')
s=s.replace('MAX_EXPORTED=1200','MAX_EXPORTED=180')
s=s.replace('MAX_OUTPUT_BYTES=350*1024*1024','MAX_OUTPUT_BYTES=80*1024*1024')
s=s.replace('WFGG_LASTWAR_PHASE30B_NODE_PAYLOAD_EXTRACTION_REDACTED.txt','WFGG_LASTWAR_HERO_ICONS_EXACT_EXTRACTION_REDACTED.txt')
s=s.replace('PHASE30B_DONE','HERO_ICONS_EXACT_DONE')
s=s.replace('WfGg Last War LAB — PHASE 30B NODE PAYLOAD EXTRACTION','WfGg Last War LAB — EXACT 31-HERO ICON EXTRACTION')
s=s.replace('=== PHASE 30B TERMINEE ===','=== EXTRACTION ICONES HEROS TERMINEE ===')

# Inject exact object-name whitelist before save_image.
needle='def save_image(img,name,objtype,candidate,path_id):\n    global output_bytes\n'
exact=sorted({x for _,_,q,h in rows for x in (q,h)})
whitelist='EXACT_HERO_ICON_NAMES={'+','.join(repr(x.lower()) for x in exact)+'}\n\n'
repl=whitelist+'''def save_image(img,name,objtype,candidate,path_id):
    global output_bytes
    if str(name or '').lower() not in EXACT_HERO_ICON_NAMES:
        return False
'''
if s.count(needle)!=1:
    raise SystemExit(f'point save_image inattendu: {s.count(needle)}')
s=s.replace(needle,repl,1)

# Make classification exact and map back to public hero name by decoded internal ref.
old='''def classify_asset(name,candidate):
    low=name.lower()
    for hero,als in hero_aliases.items():
        if any(a in low for a in als):return "heroes",hero,"object_name"
'''
new='''def classify_asset(name,candidate):
    low=name.lower()
    for hero,als in hero_aliases.items():
        if low in als or low == "hero_icon_"+als[0] if als else False:
            return "heroes",hero,"authoritative_icon_object_name"
        if any(low == a for a in als):
            return "heroes",hero,"authoritative_icon_object_name"
'''
if old not in s:
    raise SystemExit('bloc classify_asset introuvable')
s=s.replace(old,new,1)

# Report exact target coverage, independently of old heroCandidates.
report_anchor='    o.write("\\nHERO_EXPLICIT_OBJECT_NAME_COVERAGE\\n")\n'
report='''    o.write("\\nAUTHORITATIVE_ICON_TARGETS\\n")
    target_names={x.lower() for x in EXACT_HERO_ICON_NAMES}
    existing_names={str(x.get("name","")).lower() for x in combined}
    o.write(f"  targets={len(target_names)}\\n")
    o.write(f"  presentAfterRun={sum(1 for x in target_names if x in existing_names)}\\n")
    o.write(f"  missingAfterRun={sum(1 for x in target_names if x not in existing_names)}\\n")
    for x in sorted(target_names):
        o.write(f"    {x}={'PRESENT' if x in existing_names else 'MISSING'}\\n")
'''+report_anchor
if report_anchor not in s:
    raise SystemExit('ancre rapport introuvable')
s=s.replace(report_anchor,report,1)

# Old guardrail about unresolved IDs is obsolete after authoritative map decode.
s=s.replace('  unknown_50016_50017_remain_unresolved_without_authoritative_table_row=true\\n','  hero_identity_source=decoded_lw_hero_and_lw_hero_appearance\\n')

p.write_text(s,encoding='utf-8')
PY

chmod 700 "$TMP"
echo "=== EXTRACTION EXACTE DES ICONES DES 31 HEROS ==="
echo "Cibles = noms d'objets Unity décodés depuis lw_hero_appearance."
echo "Aucun scan sémantique de noms publics; aucune image non ciblée n'est sauvegardée."
echo "Aucune connexion Last War."

WFGG_PHASE30B_SRC="$TMP" bash "$RUNNER"

printf 'Fichier à partager : Téléchargements/WFGG_LASTWAR_HERO_ICONS_EXACT_EXTRACTION_REDACTED.txt\n'
