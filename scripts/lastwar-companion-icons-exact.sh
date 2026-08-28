#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — exact companion icon extraction
# OFFLINE ONLY. Uses the proven Phase30B/30D Unity pipeline but narrows discovery
# and export to the two exact static-table-resolved UI object names needed by the
# current account witness:
#   Drone level 162 -> appearance 1217 -> FX_wurenji_pifu04
#   Gorilla rank 47 -> appearance 1000005 -> zxl_zhuzai_touxiang_04
# No broad semantic scan, no gameplay automation, no Last War network connection.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/scripts/lastwar-phase30b-node-payload-extraction.sh"
RUNNER="$ROOT/scripts/lastwar-phase30d-engine-version-discovery.sh"
MAP="$ROOT/frontend/lab/lastwar-companion-authoritative-map.js"
TMP="$ROOT/scripts/.lastwar-companion-icons-exact.$$"

cleanup(){ rm -f "$TMP"; }
trap cleanup EXIT

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
[[ -s "$BASE" ]] || die "Phase 30B introuvable: $BASE"
[[ -s "$RUNNER" ]] || die "Phase 30D introuvable: $RUNNER"
[[ -s "$MAP" ]] || die "mapping Drone/Gorilla introuvable: $MAP"
command -v python >/dev/null 2>&1 || die "python Termux absent"

cp "$BASE" "$TMP"

python - "$TMP" "$MAP" <<'PY'
from pathlib import Path
import re, sys
p=Path(sys.argv[1]); mp=Path(sys.argv[2])
s=p.read_text(encoding='utf-8')
m=mp.read_text(encoding='utf-8')

# Validate the exact static-table-derived references before touching the extractor.
if "icon:'FX_wurenji_pifu04'" not in m:
    raise SystemExit('référence Drone niveau 162 introuvable dans le mapping')
if "icon:'zxl_zhuzai_touxiang_04'" not in m:
    raise SystemExit('référence Gorilla rang 47 introuvable dans le mapping')
if "currentAppearance:n>=160&&n<170?1217" not in m:
    raise SystemExit('apparence Drone 1217 non validée dans le mapping')
if "minRank:40,starLevel:4,appearance:1000005" not in m:
    raise SystemExit('apparence Gorilla 1000005 non validée dans le mapping')

DRONE='fx_wurenji_pifu04'
GORILLA='zxl_zhuzai_touxiang_04'
DISCOVERY=[DRONE,DRONE+'.png',GORILLA,GORILLA+'.png']

# Candidate discovery becomes exact companion-name-only.
marker='LOWER_TERMS={k:[x.encode("utf-8").lower() for x in vals] for k,vals in CATEGORY_TERMS.items()}\n'
if s.count(marker)!=1:
    raise SystemExit('ancre LOWER_TERMS introuvable')
override=(marker+
    'CATEGORY_TERMS={"companion_exact":'+repr(DISCOVERY)+'}\n'
    'LOWER_TERMS={"companion_exact":[x.encode("utf-8") for x in CATEGORY_TERMS["companion_exact"]]}\n')
s=s.replace(marker,override,1)

# This is deliberately narrow. Only matching bundles are opened and at most a few
# exact assets are persisted.
s=s.replace('MAX_CANDIDATES_TO_LOAD=520','MAX_CANDIDATES_TO_LOAD=220')
s=s.replace('MAX_EXPORTED=1200','MAX_EXPORTED=40')
s=s.replace('MAX_OUTPUT_BYTES=350*1024*1024','MAX_OUTPUT_BYTES=30*1024*1024')
s=s.replace('WFGG_LASTWAR_PHASE30B_NODE_PAYLOAD_EXTRACTION_REDACTED.txt','WFGG_LASTWAR_COMPANION_ICONS_EXACT_REDACTED.txt')
s=s.replace('PHASE30B_DONE','COMPANION_ICONS_EXACT_DONE')
s=s.replace('WfGg Last War LAB — PHASE 30B NODE PAYLOAD EXTRACTION','WfGg Last War LAB — EXACT DRONE + GORILLA ICON EXTRACTION')
s=s.replace('=== PHASE 30B TERMINEE ===','=== EXTRACTION DRONE + GORILLA TERMINEE ===')

# Exact object-name classifier. Strip a possible extension because Sprite/Texture2D
# m_Name normally contains the stem while table paths can contain .png.
start=s.index('def classify_asset(name,candidate):')
end=s.index('\ndef save_image(',start)
classify='''def companion_stem(v):
    low=str(v or "").strip().lower().replace("\\\\","/").rsplit("/",1)[-1]
    return re.sub(r"\\.(?:png|jpg|jpeg|tga|webp)$","",low)

EXACT_COMPANION_KIND={
    "fx_wurenji_pifu04":("drone","Drone","static_table_exact_level_profile"),
    "zxl_zhuzai_touxiang_04":("dominator","Gorilla","static_table_exact_rank_profile")
}

def classify_asset(name,candidate):
    return EXACT_COMPANION_KIND.get(companion_stem(name),("other",None,"not_target"))
'''
s=s[:start]+classify+s[end:]

# Hard whitelist: save only those two exact object stems.
needle='def save_image(img,name,objtype,candidate,path_id):\n    global output_bytes\n'
repl='''def save_image(img,name,objtype,candidate,path_id):
    global output_bytes
    if companion_stem(name) not in EXACT_COMPANION_KIND:
        return False
'''
if s.count(needle)!=1:
    raise SystemExit(f'point save_image inattendu: {s.count(needle)}')
s=s.replace(needle,repl,1)

# Always inspect Texture2D too. The proven base only did so when a candidate bundle
# had no Sprite objects; exact UI assets can coexist in mixed Sprite/Texture2D sets.
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

# Replace generic hero coverage block with a compact exact companion report. Keep the
# rest of the base report because its parser/Unity stats are useful if something fails.
anchor='    o.write("\\nHERO_EXPLICIT_OBJECT_NAME_COVERAGE\\n")\n'
report='''    o.write("\\nEXACT_COMPANION_TARGETS\\n")
    existing_stems={companion_stem(x.get("name","")) for x in combined}
    o.write("  droneLevel=162\\n")
    o.write("  droneAppearance=1217\\n")
    o.write("  droneIcon=FX_wurenji_pifu04\\n")
    o.write("  gorillaRank=47\\n")
    o.write("  gorillaAppearance=1000005\\n")
    o.write("  gorillaIcon=zxl_zhuzai_touxiang_04\\n")
    o.write(f"  exactCandidateBundles={len(candidates)}\\n")
    o.write(f"  dronePresentAfterRun={str('fx_wurenji_pifu04' in existing_stems).lower()}\\n")
    o.write(f"  gorillaPresentAfterRun={str('zxl_zhuzai_touxiang_04' in existing_stems).lower()}\\n")
    present=sum(1 for x in ('fx_wurenji_pifu04','zxl_zhuzai_touxiang_04') if x in existing_stems)
    o.write(f"  presentAfterRun={present}\\n")
    o.write(f"  missingAfterRun={2-present}\\n")
'''+anchor
if s.count(anchor)!=1:
    raise SystemExit('ancre rapport introuvable')
s=s.replace(anchor,report,1)

s=s.replace('  unknown_50016_50017_remain_unresolved_without_authoritative_table_row=true\\n','  companion_identity_source=decoded_static_tables\\n')

p.write_text(s,encoding='utf-8')
PY

chmod 700 "$TMP"
echo "=== EXTRACTION EXACTE · DRONE NIVEAU 162 + GORILLA RANG 47 ==="
echo "Drone : appearance 1217 · FX_wurenji_pifu04"
echo "Gorilla : appearance 1000005 · zxl_zhuzai_touxiang_04"
echo "Aucun asset non ciblé n'est sauvegardé. Aucune connexion Last War."

WFGG_PHASE30B_SRC="$TMP" bash "$RUNNER"

printf 'Fichier à partager : Téléchargements/WFGG_LASTWAR_COMPANION_ICONS_EXACT_REDACTED.txt\n'
