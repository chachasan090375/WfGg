#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — exact hero icon extraction V2
# OFFLINE ONLY. Fixes two concrete weaknesses seen in V1:
#  1) candidate discovery now matches ONLY full authoritative hero_icon_* object names;
#  2) both Sprite AND Texture2D objects are inspected in every exact-match bundle.
# This is not a broad semantic scan and saves no non-target graphics.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/scripts/lastwar-phase30b-node-payload-extraction.sh"
RUNNER="$ROOT/scripts/lastwar-phase30d-engine-version-discovery.sh"
MAP="$ROOT/frontend/lab/lastwar-hero-authoritative-map.js"
TMP="$ROOT/scripts/.lastwar-hero-icons-exact-v2.$$"

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

rows=[]
for mm in re.finditer(r"\{heroId:(\d+),name:'([^']+)'[^\n]*?queueIcon:'([^']+)'[^\n]*?halfIcon:'([^']+)'",m):
    rows.append((int(mm.group(1)),mm.group(2),mm.group(3),mm.group(4)))
if len(rows)!=31:
    raise SystemExit(f'mapping autoritatif incomplet: {len(rows)}/31')

exact=sorted({x.lower() for _,_,q,h in rows for x in (q,h)})
icon_to_hero={}
for hid,name,q,h in rows:
    for x in (q,h): icon_to_hero.setdefault(x.lower(),name)

# Narrow resource discovery to exact internal object names only.
marker='LOWER_TERMS={k:[x.encode("utf-8").lower() for x in vals] for k,vals in CATEGORY_TERMS.items()}\n'
if s.count(marker)!=1:
    raise SystemExit('ancre LOWER_TERMS introuvable')
override=(marker+
    'CATEGORY_TERMS={"heroes":'+repr(exact)+'}\n'
    'LOWER_TERMS={"heroes":[x.encode("utf-8") for x in CATEGORY_TERMS["heroes"]]}\n')
s=s.replace(marker,override,1)

# Exact matches should produce a small candidate set, but keep enough headroom for atlases/variants.
s=s.replace('MAX_CANDIDATES_TO_LOAD=520','MAX_CANDIDATES_TO_LOAD=1200')
s=s.replace('MAX_EXPORTED=1200','MAX_EXPORTED=180')
s=s.replace('MAX_OUTPUT_BYTES=350*1024*1024','MAX_OUTPUT_BYTES=90*1024*1024')
s=s.replace('WFGG_LASTWAR_PHASE30B_NODE_PAYLOAD_EXTRACTION_REDACTED.txt','WFGG_LASTWAR_HERO_ICONS_EXACT_V2_REDACTED.txt')
s=s.replace('PHASE30B_DONE','HERO_ICONS_EXACT_V2_DONE')
s=s.replace('WfGg Last War LAB — PHASE 30B NODE PAYLOAD EXTRACTION','WfGg Last War LAB — EXACT HERO ICON EXTRACTION V2')
s=s.replace('=== PHASE 30B TERMINEE ===','=== EXTRACTION ICONES HEROS V2 TERMINEE ===')

# Replace generic classification with exact authoritative object-name mapping.
start=s.index('def classify_asset(name,candidate):')
end=s.index('\ndef save_image(',start)
classify='ICON_TO_HERO='+repr(icon_to_hero)+'\n\ndef classify_asset(name,candidate):\n    low=str(name or "").lower()\n    hero=ICON_TO_HERO.get(low)\n    if hero:return "heroes",hero,"authoritative_icon_object_name"\n    return "other",None,"not_target"\n'
s=s[:start]+classify+s[end:]

# Hard whitelist: save only exact icon objects.
needle='def save_image(img,name,objtype,candidate,path_id):\n    global output_bytes\n'
repl='EXACT_HERO_ICON_NAMES='+repr(set(exact))+'\n\n'+'''def save_image(img,name,objtype,candidate,path_id):
    global output_bytes
    if str(name or '').lower() not in EXACT_HERO_ICON_NAMES:
        return False
'''
if s.count(needle)!=1:
    raise SystemExit(f'point save_image inattendu: {s.count(needle)}')
s=s.replace(needle,repl,1)

# Critical V2 fix: Phase30B only inspected Texture2D when a bundle contained NO Sprite.
# Exact icon atlases can contain both, so always inspect Texture2D as well.
old='''                if not sprites:
                    for obj in objects:
                        if getattr(obj.type,"name","")!="Texture2D":continue
                        try:
                            d=obj.parse_as_object();name=str(getattr(d,"m_Name","") or f"texture_{obj.path_id}")
                            img=d.image
                            if img and save_image(img,name,"Texture2D",c,obj.path_id):stats["textures_exported"]+=1
                        except Exception as e:
                            errors["texture_export"]+=1
                            if len(error_samples)<20:error_samples.append(f"texture {type(e).__name__}: {str(e)[:180]}")
'''
new='''                for obj in objects:
                    if getattr(obj.type,"name","")!="Texture2D":continue
                    try:
                        d=obj.parse_as_object();name=str(getattr(d,"m_Name","") or f"texture_{obj.path_id}")
                        img=d.image
                        if img and save_image(img,name,"Texture2D",c,obj.path_id):stats["textures_exported"]+=1
                    except Exception as e:
                        errors["texture_export"]+=1
                        if len(error_samples)<20:error_samples.append(f"texture {type(e).__name__}: {str(e)[:180]}")
'''
if s.count(old)!=1:
    raise SystemExit(f'bloc Texture2D inattendu: {s.count(old)}')
s=s.replace(old,new,1)

# Add exact target report based on the cumulative local catalog after this run.
anchor='    o.write("\\nHERO_EXPLICIT_OBJECT_NAME_COVERAGE\\n")\n'
report='''    o.write("\\nAUTHORITATIVE_ICON_TARGETS_V2\\n")
    target_names=set(EXACT_HERO_ICON_NAMES)
    existing_names={str(x.get("name","")).lower() for x in combined}
    o.write(f"  targets={len(target_names)}\\n")
    o.write(f"  exactCandidateBundles={len(candidates)}\\n")
    o.write(f"  presentAfterRun={sum(1 for x in target_names if x in existing_names)}\\n")
    o.write(f"  missingAfterRun={sum(1 for x in target_names if x not in existing_names)}\\n")
    for x in sorted(target_names):
        o.write(f"    {x}={'PRESENT' if x in existing_names else 'MISSING'}\\n")
'''+anchor
if s.count(anchor)!=1:
    raise SystemExit('ancre rapport introuvable')
s=s.replace(anchor,report,1)

# Update guardrail text that predates the decoded map.
s=s.replace('  unknown_50016_50017_remain_unresolved_without_authoritative_table_row=true\\n','  hero_identity_source=decoded_lw_hero_and_lw_hero_appearance\\n')

p.write_text(s,encoding='utf-8')
PY

chmod 700 "$TMP"
echo "=== EXTRACTION EXACTE DES ICONES HEROS · V2 ==="
echo "Correction V2: localisation par nom d'objet hero_icon_* exact + lecture Sprite ET Texture2D."
echo "Aucun asset non ciblé n'est sauvegardé. Aucune connexion Last War."

WFGG_PHASE30B_SRC="$TMP" bash "$RUNNER"

printf 'Fichier à partager : Téléchargements/WFGG_LASTWAR_HERO_ICONS_EXACT_V2_REDACTED.txt\n'
