#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 21
# OFFLINE ONLY. Goes beyond decimal-string grep from Phase 20 and inspects the
# actual static catalogue containers shipped with the installed game.
#
# Goals:
# - locate exact catalogue records for hero/equipment/drone/Overlord IDs;
# - inspect LWScripts.data and Unity asset indexes, including binary ID forms;
# - enumerate real hero asset tokens from the game's own gameres index;
# - scan the large BundleFragment0 only for targeted identifiers, streaming it
#   so it is never copied wholesale to shared storage.
#
# Privacy: no Last War network connection, no account credentials, no private
# UUID/GUID/UID values. Only public catalogue/config IDs and static game assets.

PKG="com.fun.lastwar.gp"
DOWNLOADS="${HOME}/storage/downloads"
V3="${DOWNLOADS}/WFGG_LASTWAR_PHASE19_NORMALIZED_MODULE_DATA.json"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE21_STATIC_CATALOG_FORENSICS_REDACTED.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase21-static-catalog.py"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

[[ -s "$V3" ]] || die "Phase 19 absente: $V3"
command -v python >/dev/null 2>&1 || die "python Termux absent"
command -v pm >/dev/null 2>&1 || die "commande Android pm absente"
mkdir -p "$(dirname "$PY")"

mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || die "installation Last War introuvable ($PKG)"
VERSION="$(dumpsys package "$PKG" 2>/dev/null | sed -n 's/^[[:space:]]*versionName=//p' | head -n1 || true)"

say "=== WfGg Last War LAB · PHASE 21 ==="
say "Mode: OFFLINE / forensic catalogues statiques et assets"
say "Package: $PKG${VERSION:+ · version $VERSION}"
say "APK/splits détectés: ${#APK_PATHS[@]}"
say "Le gros BundleFragment0 est parcouru en streaming; cette étape peut prendre quelques minutes."

cat > "$PY" <<'PYEOF'
import json, os, re, struct, sys, zipfile, math
from collections import defaultdict, Counter

if len(sys.argv) < 4:
    raise SystemExit("usage: phase21 <v3.json> <out.txt> <apk...>")
v3_path, out_path, *apk_paths = sys.argv[1:]
with open(v3_path, "r", encoding="utf-8") as f:
    d = json.load(f)

ids = defaultdict(set)
def add(cat, v):
    if isinstance(v, bool) or v is None: return
    try: n=int(v)
    except Exception: return
    if n: ids[cat].add(n)
for h in d.get("heroes",[]): add("heroId",h.get("heroId"))
for f in d.get("armyFormations",[])+d.get("formationTemplates",[]):
    for n in f.get("heroIds",[]): add("heroId",n)
for e in d.get("heroEquipment",[]): add("heroEquipmentCfgId",e.get("cfgId"))
for e in d.get("drone",{}).get("components",[]): add("droneComponentCfgId",e.get("cfgId"))
for g in d.get("droneChipGroups",[]):
    for c in g.get("chips",[]): add("droneChipCfgId",c.get("cfgId"))
add("droneSkillId",d.get("drone",{}).get("skillId"))
for o in d.get("overlords",[]): add("dominatorId",o.get("dominatorId"))

target_to_cats=defaultdict(set)
for cat,vals in ids.items():
    for n in vals: target_to_cats[n].add(cat)
targets=sorted(target_to_cats)
priority={50016,50017}

known_names=[
 "Adam","Ambolt","Braz","Cage","Carlie","DVA","Elsa","Farhad","Fiona","Gump","Kane","Kimberly",
 "Loki","Lucius","Marshall","Mason","McGregor","Maxwell","Monica","Morrison","Murphy","Richard",
 "Sarah","Scarlett","Schuyler","Stetmann","Swift","Tesla","Venom","Violet","Williams"
]
printable=re.compile(rb"[\x20-\x7e]{4,}")
path_re=re.compile(r"(?:Assets/[^\x00\r\n|]{3,220}|gameres_[^\x00\r\n|]{3,220}?\.bundle)",re.I)
hero_token_patterns=[
 re.compile(r"a_hero_([a-z0-9]+)",re.I),
 re.compile(r"characters[/_]hero[/_]([a-z0-9]+)",re.I),
 re.compile(r"uihero[/_]([a-z0-9]+)",re.I),
]

ascii_pat=re.compile(b"(?:"+b"|".join(re.escape(str(n).encode()) for n in targets)+b")")
le_map={struct.pack("<I",n):n for n in targets if 0<=n<=0xffffffff}
be_map={struct.pack(">I",n):n for n in targets if 0<=n<=0xffffffff}
le_pat=re.compile(b"(?:"+b"|".join(re.escape(k) for k in le_map)+b")")
be_pat=re.compile(b"(?:"+b"|".join(re.escape(k) for k in be_map)+b")")
name_pat=re.compile(b"(?:"+b"|".join(re.escape(x.encode()) for x in known_names)+b")",re.I)
keyword_pat=re.compile(rb"(?:heroId|hero_cfg|heroconfig|heroConfig|tacticalchip|tacticalweapon|dominator|overlord|drone|weapon|locali[sz]|i18n|language)",re.I)

records=defaultdict(list)
source_stats=[]
hero_tokens=Counter()
hero_paths=[]
keyword_examples=[]
name_examples=[]

# Keep contexts compact and safe: static game strings only.
def safe_strings(buf, center, radius=700):
    lo=max(0,center-radius); hi=min(len(buf),center+radius)
    vals=[]
    for m in printable.finditer(buf[lo:hi]):
        s=m.group().decode("ascii","ignore")
        s=re.sub(r"\s+"," ",s).strip()
        if len(s)>240:s=s[:240]
        if s and s not in vals: vals.append(s)
        if len(vals)>=10:break
    return " | ".join(vals)

def entropy(sample):
    if not sample:return 0.0
    c=Counter(sample); n=len(sample)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def identify_magic(head):
    for sig,name in [(b"UnityFS","UnityFS"),(b"UnityRaw","UnityRaw"),(b"UnityWeb","UnityWeb"),(b"PK\x03\x04","ZIP"),(b"\x1f\x8b","GZIP"),(b"SQLite format 3\x00","SQLite")]:
        if head.startswith(sig):return name
    return "unknown"

def process_chunk(label, buf, base_off, allow_binary=True):
    # ASCII decimal matches.
    for m in ascii_pat.finditer(buf):
        n=int(m.group())
        key=(label,n,"ascii")
        if len(records[key])<5:
            records[key].append((base_off+m.start(),safe_strings(buf,m.start(),1400 if n in priority else 650)))
    if allow_binary:
        for pat,mp,enc in ((le_pat,le_map,"le32"),(be_pat,be_map,"be32")):
            for m in pat.finditer(buf):
                n=mp.get(m.group())
                if n is None:continue
                key=(label,n,enc)
                if len(records[key])<3:
                    ctx=safe_strings(buf,m.start(),1800 if n in priority else 500)
                    records[key].append((base_off+m.start(),ctx))
    if len(keyword_examples)<80:
        for m in keyword_pat.finditer(buf):
            ctx=safe_strings(buf,m.start(),550)
            if ctx and (label,ctx) not in keyword_examples:
                keyword_examples.append((label,ctx))
                if len(keyword_examples)>=80:break
    if len(name_examples)<80:
        for m in name_pat.finditer(buf):
            ctx=safe_strings(buf,m.start(),500)
            if ctx and (label,ctx) not in name_examples:
                name_examples.append((label,ctx))
                if len(name_examples)>=80:break


def stream_entry(z, info, label, scan_binary=True, collect_paths=False):
    total=0; head=b""; sample=b""; overlap=b""; overlap_n=4096
    with z.open(info) as fh:
        while True:
            chunk=fh.read(4*1024*1024)
            if not chunk:break
            if not head: head=chunk[:64]
            if len(sample)<1024*1024: sample += chunk[:1024*1024-len(sample)]
            buf=overlap+chunk
            base=total-len(overlap)
            process_chunk(label,buf,base,scan_binary)
            if collect_paths:
                text="\n".join(m.group().decode("ascii","ignore") for m in printable.finditer(buf))
                for p in path_re.findall(text):
                    for rx in hero_token_patterns:
                        mm=rx.search(p)
                        if mm:
                            tok=mm.group(1).lower(); hero_tokens[tok]+=1
                            if len(hero_paths)<250:hero_paths.append((tok,p[:260]))
                            break
            total+=len(chunk); overlap=buf[-overlap_n:]
    source_stats.append((label,total,identify_magic(head),entropy(sample),sum(1 for b in sample if 32<=b<127)/max(1,len(sample))))

wanted_exact={
 "assets/lwScripts/LWScripts.data",
 "assets/AssetBundles/gameres",
 "assets/AssetBundles/AliasOffsetTable.bytes",
 "assets/AssetBundles/BundleOffsetTable.bytes",
 "assets/AssetBundles/BundleFragment0.bytes",
}

for apk in apk_paths:
    apk_label=os.path.basename(apk)
    try:z=zipfile.ZipFile(apk)
    except Exception:continue
    infos={i.filename:i for i in z.infolist()}
    selected=[]
    for name in wanted_exact:
        if name in infos:selected.append(infos[name])
    # Locale containers can hold the visible labels; scan all reasonably sized bins.
    for i in z.infolist():
        ln=i.filename.lower()
        if ln.startswith("assets/locale/") and ln.endswith(".bin") and i.file_size<=32*1024*1024:
            selected.append(i)
    seen=set()
    for info in selected:
        if info.filename in seen:continue
        seen.add(info.filename)
        label=f"{apk_label}:{info.filename}"
        collect=info.filename.endswith("/gameres") or info.filename.endswith("gameres")
        stream_entry(z,info,label,scan_binary=True,collect_paths=collect)
    z.close()

# Consolidate candidate exact mappings only if a name and target occur in the
# same compact static context. This is evidence, not automatic acceptance.
same_context=[]
for (label,n,enc),rows in records.items():
    for off,ctx in rows:
        names=sorted({x for x in known_names if x.lower() in ctx.lower()})
        if names:
            same_context.append((n,enc,label,off,names,ctx))

with open(out_path,"w",encoding="utf-8") as out:
    out.write("WfGg Last War LAB — PHASE 21 STATIC CATALOG FORENSICS\n")
    out.write("OFFLINE ONLY · installed static assets · no private account identifiers\n\n")
    out.write(f"TARGET_IDS={len(targets)} PRIORITY_UNKNOWN_HERO_IDS=50016,50017\n")
    out.write("SOURCE_DIAGNOSTICS\n")
    for label,size,magic,ent,ratio in source_stats:
        out.write(f"  source={label} size={size} magic={magic} entropy={ent:.3f} printableRatio={ratio:.3f}\n")

    out.write("\nPRIORITY_50016_50017\n")
    for n in (50016,50017):
        anyrow=False
        for (label,nn,enc),rows in sorted(records.items()):
            if nn!=n:continue
            anyrow=True
            out.write(f"  id={n} encoding={enc} source={label} hitsShown={len(rows)}\n")
            for off,ctx in rows:
                out.write(f"    offset={off} context={ctx or '(no printable strings nearby)'}\n")
        if not anyrow:out.write(f"  id={n} no_target_encoding_match_in_selected_static_containers\n")

    out.write("\nSAME_CONTEXT_ID_AND_KNOWN_HERO_NAME\n")
    if not same_context:out.write("  (aucun)\n")
    for n,enc,label,off,names,ctx in same_context[:120]:
        out.write(f"  id={n} encoding={enc} names={','.join(names)} source={label} offset={off}\n")
        out.write(f"    context={ctx}\n")

    out.write("\nGAME_HERO_ASSET_TOKENS\n")
    for tok,count in hero_tokens.most_common(160):
        out.write(f"  token={tok} occurrences={count}\n")
    out.write("\nGAME_HERO_ASSET_PATH_EXAMPLES\n")
    shown=set()
    for tok,p in hero_paths:
        k=(tok,p)
        if k in shown:continue
        shown.add(k);out.write(f"  token={tok} path={p}\n")
        if len(shown)>=140:break

    out.write("\nKEYWORD_CONTEXTS\n")
    for label,ctx in keyword_examples[:80]:out.write(f"  source={label} context={ctx}\n")
    out.write("\nKNOWN_NAME_CONTEXTS\n")
    for label,ctx in name_examples[:80]:out.write(f"  source={label} context={ctx}\n")

    out.write("\nTARGET_MATCH_COUNTS_BY_SOURCE_ENCODING\n")
    for (label,n,enc),rows in sorted(records.items(),key=lambda x:(x[0][1],x[0][0],x[0][2])):
        out.write(f"  id={n} category={','.join(sorted(target_to_cats[n]))} encoding={enc} source={label} shown={len(rows)}\n")

    out.write("\nINTERPRETATION_GUARDRAIL\n")
    out.write("  proximity_is_not_mapping=true\n")
    out.write("  accept_only=same_catalog_record_or_config_reference_chain_to_localization_or_asset\n")
    out.write("  next_if_scripts_high_entropy=identify/decode LWScripts container format or trace its loader offline\n")
    out.write("  next_if_bundle_has_binary_ids=use BundleOffsetTable/AliasOffsetTable to isolate referenced Unity bundle records\n")

print(f"SOURCES={len(source_stats)} HERO_ASSET_TOKENS={len(hero_tokens)} SAME_CONTEXT={len(same_context)} OUTPUT={out_path}")
PYEOF

python "$PY" "$V3" "$OUT" "${APK_PATHS[@]}"
chmod 600 "$OUT"
rm -f "$PY"

say "=== PHASE 21 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE21_STATIC_CATALOG_FORENSICS_REDACTED.txt"
