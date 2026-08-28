#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — authoritative hero catalog resolver
# READ-ONLY / OFFLINE vis-a-vis Last War.
# Reads only the installed static APK/table/assets plus the privacy-safe Phase 19 V3.
# Goal: resolve EVERY heroId in the snapshot to an authoritative table row and the
# corresponding official icon reference/local extracted PNG when already available.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOWNLOADS="${HOME}/storage/downloads"
V3="${DOWNLOADS}/WFGG_LASTWAR_PHASE19_NORMALIZED_MODULE_DATA.json"
OUT="${DOWNLOADS}/WFGG_LASTWAR_HERO_CATALOG_AUTHORITATIVE_REDACTED.txt"
KIT_DIR="${ROOT}/frontend/lab/local-assets/lastwar-kit-v1"
CAT_JSON="${KIT_DIR}/hero-catalog.json"
CAT_JS="${KIT_DIR}/hero-catalog.js"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-lastwar-hero-catalog-authoritative.py"

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
[[ -s "$V3" ]] || die "Phase 19 / V3 absente: $V3"
command -v python >/dev/null 2>&1 || die "python Termux absent"
command -v pm >/dev/null 2>&1 || die "commande Android pm absente"
mkdir -p "$KIT_DIR" "$(dirname "$PY")"

mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || die "installation Last War introuvable ($PKG)"

cat > "$PY" <<'PYEOF'
import csv, io, json, os, re, sys, zipfile
from collections import Counter, defaultdict

v3_path,out_path,kit_dir,cat_json,cat_js,*apk_paths=sys.argv[1:]
with open(v3_path,"r",encoding="utf-8") as f:v3=json.load(f)
hero_ids=sorted({int(x["heroId"]) for x in v3.get("heroes",[]) if x.get("heroId") is not None})

# Existing names are calibration only. Unknown IDs are never filled from guesses.
CALIBRATION={
30002:"Loki",30003:"Kane",30004:"Ambolt",30005:"Gump",40007:"Elsa",40008:"Farhad",40009:"Richard",40013:"Braz",40015:"Cage",40016:"Maxwell",40020:"Monica",
50006:"Murphy",50007:"Williams",50008:"Marshall",50009:"Kimberly",50010:"Stetmann",50013:"McGregor",50014:"Fiona",50015:"Swift",50018:"Schuyler",50019:"Carlie",50020:"Morrison",50021:"Lucius",50022:"Adam"
}

def norm(s):return re.sub(r"[^a-z0-9]+","",str(s).lower())
def clean_asset_token(s):
    s=os.path.basename(str(s).replace("\\","/"))
    s=re.sub(r"\.(?:png|jpg|jpeg|tga|webp|psd)$","",s,flags=re.I)
    s=re.sub(r"^(?:hero[_-]?icon[_-]?|icon[_-]?hero[_-]?)","",s,flags=re.I)
    s=re.sub(r"(?:_awaken(?:_lv\d+)?|_unique(?:_\d+)?|_zw|_small|_big|_head|_portrait)$","",s,flags=re.I)
    return re.sub(r"[_-]+"," ",s).strip()

def printable_ratio(b):
    if not b:return 0
    return sum(1 for x in b if x in (9,10,13) or 32<=x<127)/len(b)

def decode_text(b):
    for enc in ("utf-8-sig","utf-16-le","utf-16-be"):
        try:
            s=b.decode(enc)
            if s and sum(ch.isprintable() or ch in "\r\n\t" for ch in s)/len(s)>.82:return s
        except Exception:pass
    return None

def scalar(v):return isinstance(v,(str,int,float,bool)) or v is None

def flatten_scalars(d,prefix=""):
    out={}
    if isinstance(d,dict):
        for k,v in d.items():
            key=f"{prefix}.{k}" if prefix else str(k)
            if scalar(v):out[key]=v
            elif isinstance(v,dict):out.update(flatten_scalars(v,key))
    return out

def parse_json_rows(obj):
    rows=[]
    def walk(x):
        if isinstance(x,dict):
            if len(x)>=2:rows.append(x)
            for v in x.values():walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(obj);return rows

def parse_delimited(text):
    lines=[x for x in text.splitlines() if x.strip()]
    if not lines:return []
    samples="\n".join(lines[:25])
    delimiters=["\t",",","|",";"]
    delim=max(delimiters,key=lambda d:samples.count(d))
    if samples.count(delim)<2:return []
    try:table=list(csv.reader(lines,delimiter=delim))
    except Exception:return []
    if not table:return []
    header=[str(x).strip() for x in table[0]]
    headerish=sum(bool(re.search(r"[A-Za-z_]",x)) for x in header)>=max(2,len(header)//3)
    if not headerish:return []
    rows=[]
    for row in table[1:]:
        if not row:continue
        rows.append({header[i] if i<len(header) and header[i] else f"c{i}":v for i,v in enumerate(row)})
    return rows

def parse_payload(b):
    text=decode_text(b)
    if text:
        st=text.lstrip("\ufeff\x00 \r\n\t")
        if st.startswith(("{","[")):
            try:return parse_json_rows(json.loads(st)),"json",text
            except Exception:pass
        rows=parse_delimited(text)
        if rows:return rows,"delimited",text
    return [],"binary",text

def id_match_score(row,hid):
    flat=flatten_scalars(row);best=-1
    for k,v in flat.items():
        ks=norm(k)
        try:eq=int(v)==hid
        except Exception:eq=str(v).strip()==str(hid)
        if not eq:continue
        s=2
        if ks in ("id","heroid","hero_id","configid","cfgid","metaid"):s+=12
        if "hero" in ks and "id" in ks:s+=8
        if ks.endswith("id"):s+=3
        best=max(best,s)
    semantic=sum(any(t in norm(k) for t in ("name","appearance","quality","icon","pic","skill","type")) for k in flat)
    return best+min(semantic,8) if best>=0 else -1

def exact_rows(rows,hid):
    scored=[(id_match_score(r,hid),r) for r in rows]
    scored=[x for x in scored if x[0]>=0]
    scored.sort(key=lambda x:x[0],reverse=True)
    return scored

def values_by_key(flat,rx):
    out=[]
    for k,v in flat.items():
        if v in (None,""):continue
        if re.search(rx,k,re.I):out.append((k,v))
    return out

def candidate_human_names(flat):
    vals=values_by_key(flat,r"(?:^|\.)(?:name|hero_name|display_name|title|nickname|localization|name_key|name_id)$|name")
    out=[]
    for k,v in vals:
        if not isinstance(v,str):continue
        s=v.strip()
        if not s or len(s)>100:continue
        if re.fullmatch(r"\d+",s):continue
        out.append((k,s))
    return out

def icon_strings(flat):
    out=[]
    for k,v in flat.items():
        if not isinstance(v,str):continue
        s=v.strip()
        if re.search(r"hero.?icon|heroicons|\.png$|\.tga$|portrait|halfbody|head",s,re.I) or re.search(r"icon|pic|portrait|head",k,re.I):
            out.append((k,s))
    return out

# Locate outer static table container, then open it AS A ZIP archive. Phase 28 proved
# its first bytes are PK; this resolver follows that structure directly instead of
# scanning compressed bytes for numeric coincidences.
container=None
for apk in apk_paths:
    try:z=zipfile.ZipFile(apk)
    except Exception:continue
    for zi in z.infolist():
        if not (zi.filename.startswith("assets/table/") and zi.filename.endswith(".data")):continue
        try:b=z.read(zi)
        except Exception:continue
        if not b.startswith(b"PK"):continue
        try:
            inner=zipfile.ZipFile(io.BytesIO(b))
            names=inner.namelist()
        except Exception:continue
        exact=[n for n in names if n.strip("/").lower()=="lw_hero"]
        if exact:
            container=(apk,zi.filename,b,names,exact[0]);inner.close();break
        inner.close()
    z.close()
    if container:break
if not container:raise SystemExit("archive de tables contenant le membre exact lw_hero introuvable")
apk_path,container_entry,container_bytes,inner_names,hero_member=container
inner=zipfile.ZipFile(io.BytesIO(container_bytes))
hero_payload=inner.read(hero_member)
hero_rows,hero_format,hero_text=parse_payload(hero_payload)

# Related appearance/config members are kept narrowly scoped to Hero appearance.
appearance_members=[n for n in inner_names if "hero" in n.lower() and "appearance" in n.lower()]
appearance_sets=[]
for n in appearance_members:
    try:b=inner.read(n)
    except Exception:continue
    rows,fmt,txt=parse_payload(b)
    appearance_sets.append((n,b,rows,fmt,txt))
inner.close()

# Static gameres manifest is authoritative for asset/bundle filenames.
gameres_text="";gameres_source=None
for apk in apk_paths:
    try:z=zipfile.ZipFile(apk)
    except Exception:continue
    if "assets/AssetBundles/gameres" in z.namelist():
        try:gameres_text=z.read("assets/AssetBundles/gameres").decode("utf-8","ignore");gameres_source=os.path.basename(apk)+":assets/AssetBundles/gameres"
        except Exception:pass
    z.close()
    if gameres_text:break
gameres_lines=[x for x in gameres_text.splitlines() if x.strip()]

# Existing extracted graphics: use them as a cache, never as identity evidence by themselves.
kit_catalog={}
kit_catalog_path=os.path.join(kit_dir,"catalog.json")
if os.path.isfile(kit_catalog_path):
    try:
        with open(kit_catalog_path,"r",encoding="utf-8") as f:kit_catalog=json.load(f)
    except Exception:kit_catalog={}
extracted=[x for x in kit_catalog.get("extractedAssets",[]) if isinstance(x,dict)]

# Calibration: infer which row field carries an actual displayed name by checking known IDs.
known_field_hits=Counter()
known_rows={}
for hid,kname in CALIBRATION.items():
    rr=exact_rows(hero_rows,hid)
    if not rr:continue
    flat=flatten_scalars(rr[0][1]);known_rows[hid]=flat
    for k,v in flat.items():
        if isinstance(v,str) and norm(kname) and norm(kname) in norm(v):known_field_hits[k]+=1
best_name_field=known_field_hits.most_common(1)[0][0] if known_field_hits else None

# Helpers for exact appearance linkage and local-icon scoring.
def appearance_ids(flat):
    vals=[]
    for k,v in flat.items():
        if "appearance" not in norm(k):continue
        try:vals.append(int(v))
        except Exception:pass
    return list(dict.fromkeys(vals))

def find_appearance_rows(ids):
    out=[]
    for member,b,rows,fmt,txt in appearance_sets:
        for aid in ids:
            hits=exact_rows(rows,aid)
            if hits:out.append((member,aid,hits[0][1]))
    return out

def portrait_score(asset,tokens,icon_basenames):
    name=str(asset.get("name","") or "");path=str(asset.get("localPath","") or "")
    p=(name+" "+path).lower();s=0
    if "hero_icon_" in p:s+=900
    if asset.get("width")==158 and asset.get("height")==201:s+=500
    if asset.get("width")==140 and asset.get("height")==140:s+=120
    if any(b and b.lower() in p for b in icon_basenames):s+=1700
    if any(t and t in norm(p) for t in tokens):s+=550
    if any(x in p for x in ("eff_","effect","smoke","noise","zhuanwu","lrb_","ljq_icon","weapon")):s-=1800
    return s

catalog_rows=[]
for hid in hero_ids:
    ranked=exact_rows(hero_rows,hid)
    row=ranked[0][1] if ranked else None
    row_score=ranked[0][0] if ranked else None
    flat=flatten_scalars(row) if row else {}

    # Name resolution order: calibrated explicit display-name field -> any direct human-name field
    # -> exact row-linked icon token. The calibration map is never used to fill an unknown ID.
    name=None;name_basis=None;name_source=None
    if best_name_field and isinstance(flat.get(best_name_field),str):
        val=flat.get(best_name_field).strip()
        if val and not re.fullmatch(r"\d+",val):
            name=val;name_basis="lw_hero_calibrated_name_field";name_source=best_name_field
    if not name:
        cands=candidate_human_names(flat)
        # Prefer short plain-looking values; localization keys are retained but not presented as names.
        plain=[x for x in cands if not re.search(r"[_./]",x[1]) and len(x[1])<=40]
        if plain:name=plain[0][1];name_basis="lw_hero_name_field";name_source=plain[0][0]

    hero_icons=icon_strings(flat)
    aids=appearance_ids(flat)
    app_rows=find_appearance_rows(aids)
    for member,aid,arow in app_rows:
        af=flatten_scalars(arow)
        hero_icons.extend([(f"{member}:{k}",v) for k,v in icon_strings(af)])

    icon_basenames=[]
    for k,v in hero_icons:
        base=os.path.basename(str(v).replace("\\","/"))
        if re.search(r"\.(?:png|tga|jpg|jpeg|webp)$",base,re.I) or "hero_icon" in base.lower():icon_basenames.append(base)
    icon_basenames=list(dict.fromkeys(icon_basenames))

    # If the row doesn't expose a display name but explicitly links an official hero_icon asset,
    # the asset token becomes a semantic clue. It is only accepted when it is row/appearance-linked.
    if not name:
        named=[]
        for base in icon_basenames:
            token=clean_asset_token(base)
            if token and not re.fullmatch(r"\d+",token) and len(token)<=50:named.append(token)
        if named:
            name=named[0];name_basis="row_linked_official_icon_token";name_source=icon_basenames[0]

    # Search static manifest by exact icon basename/path. This does NOT infer identity; the identity
    # already came from the LW_Hero/appearance row.
    manifest_matches=[]
    for base in icon_basenames[:20]:
        low=base.lower()
        for line in gameres_lines:
            if low and low in line.lower():
                manifest_matches.append(line[:1200])
                if len(manifest_matches)>=30:break
        if len(manifest_matches)>=30:break
    bundle_names=[]
    for line in manifest_matches:
        bundle_names.extend(re.findall(r"[A-Za-z0-9_./-]+\.bundle",line,re.I))
    bundle_names=list(dict.fromkeys(bundle_names))

    # Match already-extracted official portrait by exact icon basename first, then resolved row name.
    tokens=[]
    if name:tokens.append(norm(name))
    tokens.extend(norm(clean_asset_token(x)) for x in icon_basenames)
    tokens=[x for x in dict.fromkeys(tokens) if len(x)>=3]
    scored=[(portrait_score(x,tokens,icon_basenames),x) for x in extracted]
    scored.sort(key=lambda x:x[0],reverse=True)
    local_icon=scored[0][1] if scored and scored[0][0]>=900 else None

    # Calibration status is informational. For established IDs, verify that decoded name agrees when possible.
    expected=CALIBRATION.get(hid)
    calibration_ok=None
    if expected and name:calibration_ok=norm(expected) in norm(name) or norm(name) in norm(expected)

    catalog_rows.append({
      "heroId":hid,
      "name":name,
      "nameBasis":name_basis,
      "nameSource":name_source,
      "authoritativeRowFound":bool(row),
      "rowScore":row_score,
      "appearanceIds":aids,
      "appearanceRowsFound":len(app_rows),
      "iconRefs":icon_basenames[:20],
      "manifestBundles":bundle_names[:20],
      "localIconPath":local_icon.get("localPath") if local_icon else None,
      "localIconObjectName":local_icon.get("name") if local_icon else None,
      "calibrationExpected":expected,
      "calibrationMatches":calibration_ok,
      "rowFields":flat
    })

resolved_names=sum(bool(x["name"]) for x in catalog_rows)
resolved_icons=sum(bool(x["localIconPath"]) for x in catalog_rows)
authoritative=sum(bool(x["authoritativeRowFound"]) for x in catalog_rows)

result={
 "format":"WFGG_LASTWAR_HERO_CATALOG_V1",
 "source":"installed_static_game_tables",
 "networkUsed":False,
 "heroCount":len(hero_ids),
 "resolvedAuthoritativeRows":authoritative,
 "resolvedNames":resolved_names,
 "resolvedLocalIcons":resolved_icons,
 "tableContainer":os.path.basename(apk_path)+":"+container_entry,
 "heroTableMember":hero_member,
 "heroTableFormat":hero_format,
 "heroTableCompressedContainer":True,
 "heroTablePayloadBytes":len(hero_payload),
 "appearanceMembers":appearance_members,
 "gameresSource":gameres_source,
 "calibratedNameField":best_name_field,
 "heroes":catalog_rows
}
with open(cat_json,"w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
with open(cat_js,"w",encoding="utf-8") as f:
    f.write("window.WFGG_LASTWAR_HERO_CATALOG=");json.dump(result,f,ensure_ascii=False,separators=(",",":"));f.write(";\n")

with open(out_path,"w",encoding="utf-8") as o:
    o.write("WfGg Last War LAB — AUTHORITATIVE HERO CATALOG\n")
    o.write("READ-ONLY · installed static tables/assets only · no Last War network connection\n\n")
    o.write(f"heroCount={len(hero_ids)}\nresolvedAuthoritativeRows={authoritative}\nresolvedNames={resolved_names}\nresolvedLocalIcons={resolved_icons}\n")
    o.write(f"tableContainer={os.path.basename(apk_path)}:{container_entry}\nheroTableMember={hero_member}\nheroTableFormat={hero_format}\nheroTablePayloadBytes={len(hero_payload)}\n")
    o.write(f"appearanceMembers={','.join(appearance_members) or '-'}\ncalibratedNameField={best_name_field or '-'}\n")
    o.write("\nHERO_CATALOG\n")
    for x in catalog_rows:
        o.write(f"  heroId={x['heroId']} name={x['name'] or 'UNRESOLVED'} row={int(x['authoritativeRowFound'])} basis={x['nameBasis'] or '-'} localIcon={x['localIconPath'] or '-'}\n")
        if x['iconRefs']:o.write("    iconRefs="+" | ".join(x['iconRefs'][:8])+"\n")
        if x['manifestBundles']:o.write("    bundles="+" | ".join(x['manifestBundles'][:5])+"\n")
    o.write("\nGUARDRAILS\n")
    o.write("  numeric_proximity_is_not_identity=true\n")
    o.write("  calibration_names_do_not_fill_unknown_ids=true\n")
    o.write("  row_or_row_linked_appearance_required_for_unknown_name=true\n")
    o.write("  local_icon_match_requires_row_linked_icon_or_resolved_row_name=true\n")
    o.write("  no_game_write=true\n  no_game_network=true\n")
    if resolved_names<len(hero_ids):o.write("  status=NAMES_INCOMPLETE_REQUIRES_DECODE_OF_LW_HERO_MEMBER_FORMAT\n")
    elif resolved_icons<len(hero_ids):o.write("  status=NAMES_COMPLETE_ICONS_NEED_EXACT_TARGET_EXTRACTION\n")
    else:o.write("  status=COMPLETE_ALL_HERO_NAMES_AND_LOCAL_ICONS\n")

print(f"HERO_CATALOG_DONE heroes={len(hero_ids)} rows={authoritative} names={resolved_names} icons={resolved_icons}")
print(f"OUTPUT={out_path}")
print(f"CATALOG={cat_json}")
PYEOF

python "$PY" "$V3" "$OUT" "$KIT_DIR" "$CAT_JSON" "$CAT_JS" "${APK_PATHS[@]}"
rm -f "$PY"
chmod 600 "$OUT" "$CAT_JSON" "$CAT_JS" 2>/dev/null || true
printf '=== CATALOGUE HEROS TERMINE ===\n'
printf 'Aucune connexion ni écriture Last War.\n'
printf 'Fichier à partager : Téléchargements/WFGG_LASTWAR_HERO_CATALOG_AUTHORITATIVE_REDACTED.txt\n'
