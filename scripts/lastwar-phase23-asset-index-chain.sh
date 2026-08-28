#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 23
# OFFLINE ONLY. Traces the game's static asset indexes to isolate exact candidate
# UnityFS/catalog records for unresolved hero IDs and companion equipment.
# Privacy: no Last War network connection, no credentials, no private UUID/GUID/UID.

PKG="com.fun.lastwar.gp"
DOWNLOADS="${HOME}/storage/downloads"
V3="${DOWNLOADS}/WFGG_LASTWAR_PHASE19_NORMALIZED_MODULE_DATA.json"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE23_ASSET_INDEX_CHAIN_REDACTED.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase23-asset-index-chain.py"

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

say "=== WfGg Last War LAB · PHASE 23 ==="
say "Mode: OFFLINE / chaîne index assets -> bundles"
say "Package: $PKG${VERSION:+ · version $VERSION}"
say "APK/splits détectés: ${#APK_PATHS[@]}"

cat > "$PY" <<'PYEOF'
import csv, io, json, os, re, struct, sys, zipfile
from collections import defaultdict, Counter

if len(sys.argv) < 4:
    raise SystemExit("usage: phase23 <v3.json> <out.txt> <apk...>")
v3_path, out_path, *apk_paths = sys.argv[1:]
with open(v3_path, "r", encoding="utf-8") as f:
    d=json.load(f)

unknown_ids={50016,50017}
hero_ids=sorted({int(h.get("heroId")) for h in d.get("heroes",[]) if h.get("heroId")})
dominator_ids=sorted({int(x.get("dominatorId")) for x in d.get("overlords",[]) if x.get("dominatorId")})
drone_cfg_ids=set()
for c in d.get("drone",{}).get("components",[]):
    if c.get("cfgId") is not None: drone_cfg_ids.add(int(c["cfgId"]))
for g in d.get("droneChipGroups",[]):
    for c in g.get("chips",[]):
        if c.get("cfgId") is not None: drone_cfg_ids.add(int(c["cfgId"]))

target_ids=set(hero_ids)|unknown_ids|set(dominator_ids)|drone_cfg_ids

wanted={
    "assets/AssetBundles/gameres",
    "assets/AssetBundles/AliasOffsetTable.bytes",
    "assets/AssetBundles/BundleOffsetTable.bytes",
    "assets/AssetBundles/BundleFragment0.bytes",
    "assets/lwScripts/LWScripts.data",
}
entries={}
for apk in apk_paths:
    try:z=zipfile.ZipFile(apk)
    except Exception:continue
    for i in z.infolist():
        if i.filename in wanted:
            entries[i.filename]=(apk,i)
    z.close()

def read_entry(name):
    if name not in entries:return None,None
    apk,info=entries[name]
    with zipfile.ZipFile(apk) as z:
        return z.read(info), os.path.basename(apk)+":"+name

printable=re.compile(rb"[\x20-\x7e]{4,}")
hero_asset_re=re.compile(r"(?:hero_icon_[a-z0-9_]+|heroicons(?:big|small)[^,| ]*|a_hero_[a-z0-9_]+|hero_remote1)",re.I)
companion_re=re.compile(r"(?:item_uav_equip_\d+\.png|uav|drone|tacticalchip|dominator|gorilla|cockatrice|hawk)",re.I)

# --- Parse gameres line records ------------------------------------------------
gameres,label_g=read_entry("assets/AssetBundles/gameres")
gameres_text=(gameres or b"").decode("utf-8","ignore")
lines=[x.strip() for x in gameres_text.splitlines() if x.strip()]

exact_id_records=defaultdict(list)
hero_asset_records=[]
companion_asset_records=[]
record_assets=[]
for line in lines:
    fields=[x.strip() for x in line.split(',')]
    ints=[]
    for idx,x in enumerate(fields):
        if re.fullmatch(r"\d+",x):
            try:ints.append((idx,int(x)))
            except Exception:pass
    for idx,n in ints:
        if n in target_ids and len(exact_id_records[n])<20:
            exact_id_records[n].append((idx,line[:1800]))
    if hero_asset_re.search(line):
        hero_asset_records.append(line[:1800])
    if companion_re.search(line):
        companion_asset_records.append(line[:1800])
    for m in re.finditer(r"([A-Za-z0-9_./-]+\.bundle)",line):
        record_assets.append(m.group(1))

# Candidate strings worth tracing through alias/offset indexes.
needles=set()
for line in hero_asset_records:
    if any(str(n) in line for n in unknown_ids):
        needles.update(re.findall(r"[A-Za-z0-9_./-]+\.bundle",line))
for n in sorted(drone_cfg_ids):
    for line in companion_asset_records:
        if re.search(rf"(?:^|[^0-9]){n}(?:[^0-9]|$)",line):
            for m in re.findall(r"[A-Za-z0-9_./-]+\.bundle",line):needles.add(m)
        if f"item_uav_equip_{n}.png" in line:needles.add(f"item_uav_equip_{n}.png")
# Always include semantic anchors independent of numeric coincidences.
needles.update(["hero_icon_","heroiconsbig","heroiconssmall","hero_remote1","item_uav_equip_","dominator","gorilla","cockatrice","tacticalchip"])

# --- Index table neighborhoods -------------------------------------------------
index_results=defaultdict(list)
index_stats=[]
for name in ("assets/AssetBundles/AliasOffsetTable.bytes","assets/AssetBundles/BundleOffsetTable.bytes"):
    raw,label=read_entry(name)
    if raw is None:continue
    ratio=sum(1 for b in raw if 32<=b<127)/max(1,len(raw))
    index_stats.append((label,len(raw),ratio))
    low=raw.lower()
    for needle in sorted(needles):
        nb=needle.encode("ascii","ignore").lower()
        if not nb:continue
        start=0;shown=0
        while shown<8:
            p=low.find(nb,start)
            if p<0:break
            lo=max(0,p-260);hi=min(len(raw),p+len(nb)+420)
            ctx=raw[lo:hi].decode("ascii","ignore")
            ctx=re.sub(r"[^\x20-\x7e]+"," | ",ctx)
            ctx=re.sub(r"\s+"," ",ctx).strip()
            index_results[(label,needle)].append((p,ctx[:1000]))
            shown+=1;start=p+1

# --- Find UnityFS signatures in the large fragment, streaming -----------------
fragment_info=None
if "assets/AssetBundles/BundleFragment0.bytes" in entries:
    apk,info=entries["assets/AssetBundles/BundleFragment0.bytes"]
    fragment_info=(apk,info)
unityfs_offsets=[]
if fragment_info:
    apk,info=fragment_info
    with zipfile.ZipFile(apk) as z, z.open(info) as fh:
        total=0;overlap=b""
        while True:
            chunk=fh.read(8*1024*1024)
            if not chunk:break
            buf=overlap+chunk;base=total-len(overlap)
            pos=0
            while True:
                p=buf.find(b"UnityFS",pos)
                if p<0:break
                off=base+p
                if not unityfs_offsets or off!=unityfs_offsets[-1]:unityfs_offsets.append(off)
                pos=p+7
            total+=len(chunk);overlap=buf[-16:]

# Pull plausible decimal offsets from index contexts and pair with nearest UnityFS.
offset_candidates=[]
for (label,needle),rows in index_results.items():
    for p,ctx in rows:
        for s in re.findall(r"\b\d{5,10}\b",ctx):
            try:n=int(s)
            except Exception:continue
            if fragment_info and 0<=n<fragment_info[1].file_size:
                offset_candidates.append((needle,n,label,ctx[:500]))
offset_candidates=offset_candidates[:500]

def nearest(vals,x):
    if not vals:return None
    import bisect
    i=bisect.bisect_left(vals,x)
    cand=[]
    if i<len(vals):cand.append(vals[i])
    if i:cand.append(vals[i-1])
    return min(cand,key=lambda y:abs(y-x)) if cand else None

# --- LWScripts semantic clues ---------------------------------------------------
lws,label_l=read_entry("assets/lwScripts/LWScripts.data")
lw_clues=[]
if lws:
    tokens=[b"HeroTemplate",b"HeroConfig",b"GetHeroByHeroId",b"heroId",b"HeroName",b"DominatorGorillaInfo",b"DominatorCockatriceInfo",b"TacticalChipManager",b"item_uav_equip"]
    low=lws.lower()
    for tok in tokens:
        start=0;shown=0
        while shown<12:
            p=low.find(tok.lower(),start)
            if p<0:break
            lo=max(0,p-320);hi=min(len(lws),p+len(tok)+520)
            vals=[]
            for m in printable.finditer(lws[lo:hi]):
                s=m.group().decode("ascii","ignore")
                s=re.sub(r"\s+"," ",s).strip()
                if s and s not in vals:vals.append(s)
                if len(vals)>=14:break
            lw_clues.append((tok.decode(),p," | ".join(vals)[:1400]))
            shown+=1;start=p+1

with open(out_path,"w",encoding="utf-8") as out:
    out.write("WfGg Last War LAB — PHASE 23 ASSET INDEX CHAIN\n")
    out.write("OFFLINE ONLY · static installed assets · no private account identifiers\n\n")
    out.write(f"HERO_IDS={len(hero_ids)} UNKNOWN_HERO_IDS=50016,50017 DRONE_CFG_IDS={len(drone_cfg_ids)} DOMINATOR_IDS={len(dominator_ids)}\n")
    out.write(f"GAMERES_LINES={len(lines)} HERO_ASSET_RECORDS={len(hero_asset_records)} COMPANION_ASSET_RECORDS={len(companion_asset_records)}\n")

    out.write("\nUNKNOWN_ID_EXACT_FIELD_RECORDS\n")
    for n in (50016,50017):
        rows=exact_id_records.get(n,[])
        out.write(f"  heroId={n} exactFieldRecords={len(rows)}\n")
        for idx,line in rows[:12]:out.write(f"    fieldIndex={idx} record={line}\n")

    out.write("\nCALIBRATION_EXACT_FIELD_RECORDS\n")
    for n in hero_ids:
        rows=exact_id_records.get(n,[])
        if not rows:continue
        out.write(f"  heroId={n} records={len(rows)}\n")
        for idx,line in rows[:3]:out.write(f"    fieldIndex={idx} record={line}\n")

    out.write("\nINDEX_TABLE_STATS\n")
    for label,size,ratio in index_stats:out.write(f"  source={label} size={size} printableRatio={ratio:.3f}\n")

    out.write("\nINDEX_TABLE_LINKS\n")
    for (label,needle),rows in sorted(index_results.items()):
        if not rows:continue
        out.write(f"  needle={needle} source={label} hitsShown={len(rows)}\n")
        for p,ctx in rows:out.write(f"    tableOffset={p} context={ctx}\n")

    out.write("\nUNITYFS_FRAGMENT_TOPOLOGY\n")
    if fragment_info:
        out.write(f"  fragmentSize={fragment_info[1].file_size} unityfsSignatures={len(unityfs_offsets)}\n")
        out.write("  firstUnityFSOffsets="+",".join(map(str,unityfs_offsets[:80]))+"\n")
    else:out.write("  BundleFragment0_not_found\n")

    out.write("\nINDEX_NUMERIC_OFFSETS_TO_NEAREST_UNITYFS\n")
    seen=set();shown=0
    for needle,n,label,ctx in offset_candidates:
        near=nearest(unityfs_offsets,n)
        key=(needle,n,near)
        if key in seen:continue
        seen.add(key)
        delta=(near-n) if near is not None else None
        out.write(f"  needle={needle} candidateOffset={n} nearestUnityFS={near if near is not None else '-'} delta={delta if delta is not None else '-'}\n")
        shown+=1
        if shown>=160:break

    out.write("\nLWSCRIPTS_HERO_CONFIG_CLUES\n")
    for tok,p,ctx in lw_clues:
        out.write(f"  token={tok} offset={p}\n")
        out.write(f"    context={ctx}\n")

    out.write("\nCOMPANION_FILENAME_EVIDENCE\n")
    for n in sorted(drone_cfg_ids):
        exact=[]
        patt=re.compile(rf"item_uav_equip_{n}\.png",re.I)
        for line in companion_asset_records:
            if patt.search(line): exact.append(line)
        if exact:
            out.write(f"  cfgId={n} exactUavIconRecords={len(exact)}\n")
            for line in exact[:6]:out.write(f"    record={line}\n")

    out.write("\nEVIDENCE_RULE\n")
    out.write("  accepted_mapping_requires=exact_catalog_field_chain_or_decoded_Unity_object\n")
    out.write("  numeric_substring_or_nearby_name_is_not_mapping=true\n")
    out.write("  unknown_hero_ids_are_not_guessed=true\n")
    out.write("  next=use_index_chain_to_extract_only_candidate_UnityFS_bundles_then_decode_TextAsset_or_MonoBehaviour_records\n")

print(f"UNITYFS={len(unityfs_offsets)} INDEX_LINK_GROUPS={sum(1 for v in index_results.values() if v)} OUTPUT={out_path}")
PYEOF

python "$PY" "$V3" "$OUT" "${APK_PATHS[@]}"
chmod 600 "$OUT"
rm -f "$PY"

say "=== PHASE 23 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE23_ASSET_INDEX_CHAIN_REDACTED.txt"
