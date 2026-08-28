#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 22
# OFFLINE ONLY. Builds an exact catalogue bridge from numeric config IDs toward
# static Last War records, localization payloads and asset/icon names.
# No Last War network connection, no credentials, no private UUID/GUID/UID.

PKG="com.fun.lastwar.gp"
DOWNLOADS="${HOME}/storage/downloads"
V3="${DOWNLOADS}/WFGG_LASTWAR_PHASE19_NORMALIZED_MODULE_DATA.json"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE22_CATALOG_BRIDGE_REDACTED.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase22-catalog-bridge.py"

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

say "=== WfGg Last War LAB · PHASE 22 ==="
say "Mode: OFFLINE / pont catalogue ID → libellé → asset"
say "Package: $PKG${VERSION:+ · version $VERSION}"
say "APK/splits détectés: ${#APK_PATHS[@]}"
say "Analyse ciblée de gameres + locales FR/EN/IT/ES + LWScripts."

cat > "$PY" <<'PYEOF'
import gzip, json, os, re, struct, sys, zipfile
from collections import defaultdict, Counter

if len(sys.argv) < 4:
    raise SystemExit("usage: phase22 <v3.json> <out.txt> <apk...>")
v3_path, out_path, *apk_paths = sys.argv[1:]
with open(v3_path, "r", encoding="utf-8") as f:
    d=json.load(f)

ids=defaultdict(set)
def add(cat,v):
    if isinstance(v,bool) or v is None:return
    try:n=int(v)
    except Exception:return
    if n:ids[cat].add(n)
for h in d.get("heroes",[]):add("heroId",h.get("heroId"))
for f in d.get("armyFormations",[])+d.get("formationTemplates",[]):
    for n in f.get("heroIds",[]):add("heroId",n)
for e in d.get("heroEquipment",[]):add("heroEquipmentCfgId",e.get("cfgId"))
for e in d.get("drone",{}).get("components",[]):add("droneComponentCfgId",e.get("cfgId"))
for g in d.get("droneChipGroups",[]):
    for c in g.get("chips",[]):add("droneChipCfgId",c.get("cfgId"))
add("droneSkillId",d.get("drone",{}).get("skillId"))
for o in d.get("overlords",[]):add("dominatorId",o.get("dominatorId"))
for w in d.get("weapons",[]):add("weaponSkillId",w.get("skill"))

targets=sorted({n for vals in ids.values() for n in vals})
cat_by_id=defaultdict(set)
for cat,vals in ids.items():
    for n in vals:cat_by_id[n].add(cat)
hero_targets=sorted(ids.get("heroId",set()))
priority={50016,50017}

known={
30002:"Loki",30003:"Kane",30004:"Ambolt",30005:"Gump",40007:"Elsa",40008:"Farhad",40009:"Richard",40013:"Braz",40015:"Cage",40016:"Maxwell",40020:"Monica",
50006:"Murphy",50007:"Williams",50008:"Marshall",50009:"Kimberly",50010:"Stetmann",50013:"McGregor",50014:"Fiona",50015:"Swift",50018:"Schuyler",50019:"Carlie",50020:"Morrison",50021:"Lucius",50022:"Adam"
}
known_names=sorted(set(known.values()))

printable=re.compile(rb"[\x20-\x7e]{5,}")
record_id_rx={n:re.compile(rf"(?<!\d){n}(?!\d)") for n in targets}
asset_name_rx=re.compile(r"[A-Za-z0-9_./-]{3,220}\.(?:png|jpg|webp|bundle|prefab|asset|bytes)",re.I)
hero_token_rxs=[
    re.compile(r"hero_icon_([a-z0-9_]+)",re.I),
    re.compile(r"sound_hero_[a-z0-9]+_([a-z0-9_]+?)(?:_\d|_prefab)",re.I),
    re.compile(r"a_hero_([a-z0-9]+)",re.I),
]
generic_tokens={"common","remote1","new","icon","ui","hero","spine","prefab"}

def strings(buf,minlen=5):
    return [m.group().decode("ascii","ignore") for m in printable.finditer(buf) if len(m.group())>=minlen]

def compact(s,limit=800):
    s=re.sub(r"\s+"," ",s).strip()
    return s if len(s)<=limit else s[:limit]+"…"

def tokens_from_record(s):
    out=[]
    for rx in hero_token_rxs:
        for m in rx.finditer(s):
            t=m.group(1).strip("_").lower()
            if t and t not in generic_tokens and t not in out:out.append(t)
    return out

def names_from_record(s):
    sl=s.lower()
    return sorted({name for name in known_names if re.search(rf"(?<![a-z]){re.escape(name.lower())}(?![a-z])",sl)})

def icon_assets(s):
    out=[]
    for m in asset_name_rx.finditer(s):
        a=m.group(0)
        al=a.lower()
        if any(k in al for k in ("hero","equip","uav","drone","chip","weapon","dominator","overlord")):
            if a not in out:out.append(a)
    return out[:20]

def magic(data):
    if data.startswith(b"\x1f\x8b"):return "GZIP"
    if data.startswith(b"UnityFS"):return "UnityFS"
    if data.startswith(b"SQLite format 3\x00"):return "SQLite"
    x=data.lstrip()[:1]
    if x in (b"{",b"["):return "JSON_OR_TEXT"
    return "unknown"

def printable_ratio(data):
    if not data:return 0.0
    sample=data[:min(len(data),2*1024*1024)]
    return sum(1 for b in sample if b in (9,10,13) or 32<=b<127)/len(sample)

same_records=defaultdict(list)
direct_assets=defaultdict(set)
all_hero_tokens=Counter()
locale_diag=[]
locale_hits=defaultdict(list)
script_clues=[]
calibration=[]

for apk in apk_paths:
    try:z=zipfile.ZipFile(apk)
    except Exception:continue
    apk_label=os.path.basename(apk)
    names=set(z.namelist())

    # gameres is the high-printable asset catalogue/index.
    gname="assets/AssetBundles/gameres"
    if gname in names:
        raw=z.read(gname)
        recs=strings(raw,12)
        for s in recs:
            sl=s.lower()
            if "hero" in sl:
                for t in tokens_from_record(s):all_hero_tokens[t]+=1
            for n in targets:
                if not record_id_rx[n].search(s):continue
                toks=tokens_from_record(s); kn=names_from_record(s); assets=icon_assets(s)
                # Exact same printable record only; no neighbouring strings.
                if toks or kn or assets or any(k in sl for k in ("hero","equip","uav","drone","chip","weapon","dominator","overlord")):
                    row={"source":f"{apk_label}:{gname}","record":compact(s),"tokens":toks,"knownNames":kn,"assets":assets}
                    if len(same_records[n])<20:same_records[n].append(row)
                for a in assets:
                    direct_assets[n].add(a)
        # Also find filenames that directly embed a target ID, regardless of record columns.
        for s in recs:
            for a in icon_assets(s):
                for n in targets:
                    if record_id_rx[n].search(a):direct_assets[n].add(a)

    # Localization packs are gzip in the installed asset pack. Decompress FR/EN/IT/ES.
    for lang in ("fr","en","it","es"):
        lname=f"assets/locale/23500/{lang}.bin"
        if lname not in names:continue
        raw=z.read(lname)
        try:dec=gzip.decompress(raw) if raw.startswith(b"\x1f\x8b") else raw
        except Exception as e:
            locale_diag.append((lang,len(raw),0,"decompress_error",0.0,str(e)[:120]));continue
        locale_diag.append((lang,len(raw),len(dec),magic(dec),printable_ratio(dec),""))
        # Exact ID searches in decompressed locale payload.
        for n in targets:
            pats=[("ascii",str(n).encode())]
            if 0<=n<=0xffffffff:pats += [("le32",struct.pack("<I",n)),("be32",struct.pack(">I",n))]
            for enc,p in pats:
                pos=dec.find(p)
                if pos<0:continue
                lo=max(0,pos-800);hi=min(len(dec),pos+800)
                ctx=" | ".join(compact(x,220) for x in strings(dec[lo:hi],4)[:12])
                if len(locale_hits[n])<8:locale_hits[n].append((lang,enc,pos,ctx))
        # If payload is JSON, find dictionaries containing a target ID and strings in same object.
        try:
            txt=dec.decode("utf-8")
            obj=json.loads(txt)
        except Exception:obj=None
        if obj is not None:
            stack=[obj]
            while stack:
                cur=stack.pop()
                if isinstance(cur,dict):
                    vals=list(cur.values())
                    nums=set()
                    for v in vals:
                        if isinstance(v,int):nums.add(v)
                        elif isinstance(v,str) and v.isdigit():nums.add(int(v))
                    strs=[v for v in vals if isinstance(v,str) and 1<=len(v)<=200]
                    for n in nums.intersection(targets):
                        ctx=compact(json.dumps(cur,ensure_ascii=False),900)
                        if len(locale_hits[n])<8:locale_hits[n].append((lang,"json_record",-1,ctx))
                    for v in vals:
                        if isinstance(v,(dict,list)):stack.append(v)
                elif isinstance(cur,list):
                    for v in cur:
                        if isinstance(v,(dict,list)):stack.append(v)

    # LWScripts: collect only structural strings, not binary-ID proximity guesses.
    sname="assets/lwScripts/LWScripts.data"
    if sname in names:
        raw=z.read(sname)
        clue_rx=re.compile(rb"[\x20-\x7e]{4,160}(?:heroId|HeroId|heroConfig|HeroConfig|localization|Localization|nameKey|NameKey|i18n|I18N|tacticalChip|TacticalChip|dominator|Dominator)[\x20-\x7e]{0,220}")
        for m in clue_rx.finditer(raw):
            s=compact(m.group().decode("ascii","ignore"),360)
            if s and s not in script_clues:script_clues.append(s)
            if len(script_clues)>=100:break
    z.close()

# Calibration: known hero IDs may only validate a record if the same record contains
# their already-established label/token. Never use calibration to guess unknown IDs.
for n,label in known.items():
    good=[]
    needle=label.lower().replace("stetmann","stetman").replace("carlie","carly")
    for row in same_records.get(n,[]):
        hay=(row["record"]+" "+" ".join(row["tokens"])).lower()
        aliases=[needle]
        if label=="Murphy":aliases += ["audie_murphy","murphy"]
        if label=="McGregor":aliases += ["ewan_mcgregor","mcgregor","ewan"]
        if any(a in hay for a in aliases):good.append(row)
    if good:calibration.append((n,label,good[:3]))

with open(out_path,"w",encoding="utf-8") as out:
    out.write("WfGg Last War LAB — PHASE 22 CATALOG BRIDGE\n")
    out.write("OFFLINE ONLY · same-record/static localization evidence only · no private account identifiers\n\n")
    out.write(f"TARGET_IDS={len(targets)} HERO_IDS={len(hero_targets)} PRIORITY_UNKNOWN=50016,50017\n")

    out.write("\nLOCALE_DECOMPRESSION_DIAGNOSTICS\n")
    for lang,cs,ds,mg,pr,err in locale_diag:
        out.write(f"  lang={lang} compressed={cs} decompressed={ds} payloadMagic={mg} printableRatio={pr:.3f}{(' error='+err) if err else ''}\n")

    out.write("\nPRIORITY_UNKNOWN_HERO_SAME_RECORD\n")
    for n in (50016,50017):
        rows=same_records.get(n,[])
        out.write(f"  heroId={n} sameRecordCandidates={len(rows)} localeHits={len(locale_hits.get(n,[]))} directAssets={len(direct_assets.get(n,set()))}\n")
        for r in rows[:12]:
            out.write(f"    source={r['source']} tokens={','.join(r['tokens']) or '-'} knownNames={','.join(r['knownNames']) or '-'}\n")
            if r['assets']:out.write(f"      assets={';'.join(r['assets'])}\n")
            out.write(f"      record={r['record']}\n")
        for lang,enc,pos,ctx in locale_hits.get(n,[])[:8]:
            out.write(f"    locale={lang} encoding={enc} offset={pos} context={ctx or '(no printable text)'}\n")
        for a in sorted(direct_assets.get(n,set()))[:15]:out.write(f"    directAsset={a}\n")

    out.write("\nKNOWN_HERO_CALIBRATION_SAME_RECORD\n")
    if not calibration:out.write("  (aucune correspondance de calibration exacte)\n")
    for n,label,rows in calibration:
        out.write(f"  heroId={n} expected={label} matchingRecords={len(rows)}\n")
        for r in rows:out.write(f"    tokens={','.join(r['tokens']) or '-'} record={r['record']}\n")

    out.write("\nALL_HERO_TARGET_SAME_RECORD_CANDIDATES\n")
    for n in hero_targets:
        rows=same_records.get(n,[])
        out.write(f"  heroId={n} candidates={len(rows)} directAssets={len(direct_assets.get(n,set()))}\n")
        for r in rows[:5]:
            out.write(f"    tokens={','.join(r['tokens']) or '-'} knownNames={','.join(r['knownNames']) or '-'} assets={';'.join(r['assets']) or '-'}\n")
            out.write(f"      record={r['record']}\n")

    out.write("\nNON_HERO_DIRECT_ASSET_FILENAMES\n")
    for n in targets:
        if n in hero_targets:continue
        assets=sorted(direct_assets.get(n,set()))
        if assets:
            out.write(f"  id={n} category={','.join(sorted(cat_by_id[n]))} assets={len(assets)}\n")
            for a in assets[:15]:out.write(f"    asset={a}\n")

    out.write("\nLOCALE_ID_HITS_ALL_TARGETS\n")
    for n in targets:
        rows=locale_hits.get(n,[])
        if not rows:continue
        out.write(f"  id={n} category={','.join(sorted(cat_by_id[n]))} hits={len(rows)}\n")
        for lang,enc,pos,ctx in rows[:5]:out.write(f"    lang={lang} encoding={enc} offset={pos} context={ctx}\n")

    out.write("\nGAME_HERO_TOKEN_DICTIONARY\n")
    for tok,count in all_hero_tokens.most_common(180):out.write(f"  token={tok} records={count}\n")

    out.write("\nLWSCRIPTS_STATIC_CONFIG_CLUES\n")
    for s in script_clues[:100]:out.write(f"  {s}\n")

    out.write("\nEVIDENCE_RULE\n")
    out.write("  accepted_mapping_requires=same_printable_catalog_record OR parsed_localization_record OR explicit_config_reference_chain\n")
    out.write("  nearby_name_only_is_rejected=true\n")
    out.write("  unknown_hero_ids_are_not_guessed=true\n")
    out.write("  next=if 50016/50017 still unresolved, isolate the specific UnityFS bundle records referenced by asset indexes and decode their TextAsset/MonoBehaviour catalog objects\n")

print(f"SAME_RECORD_IDS={sum(1 for n in targets if same_records.get(n))} LOCALE_IDS={sum(1 for n in targets if locale_hits.get(n))} HERO_TOKENS={len(all_hero_tokens)} OUTPUT={out_path}")
PYEOF

python "$PY" "$V3" "$OUT" "${APK_PATHS[@]}"
chmod 600 "$OUT"
rm -f "$PY"

say "=== PHASE 22 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE22_CATALOG_BRIDGE_REDACTED.txt"
