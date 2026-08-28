#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 30
# Extracts Sprite/Texture2D assets from locally installed Last War UnityFS bundles.
# No Last War network connection. No gameplay automation.
# First run may install UnityPy from PyPI if it is missing; all game-data access is local.
# Generated graphics stay under frontend/lab/local-assets/lastwar-kit-v1 and are ignored by Git.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOWNLOADS="${HOME}/storage/downloads"
KIT_DIR="${ROOT}/frontend/lab/local-assets/lastwar-kit-v1"
CATALOG="${KIT_DIR}/catalog.json"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE30_UNITY_SPRITE_EXTRACTION_REDACTED.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase30-unity-sprite-extraction.py"
UNITYPY_VERSION="1.25.3"

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || die "python Termux absent"
command -v pm >/dev/null 2>&1 || die "commande Android pm absente"
[[ -s "$CATALOG" ]] || die "Kit Phase 29 absent: $CATALOG"
mkdir -p "$(dirname "$PY")" "$KIT_DIR/extracted"

if ! python - <<'PYTEST' >/dev/null 2>&1
import UnityPy
from PIL import Image
PYTEST
then
  if [[ "${WFGG_PHASE30_NO_INSTALL:-0}" == "1" ]]; then
    die "UnityPy absent. Lance: python -m pip install 'UnityPy==${UNITYPY_VERSION}'"
  fi
  printf 'UnityPy absent — installation de la dépendance d’extraction (PyPI, une seule fois)…\n'
  python -m pip install --disable-pip-version-check "UnityPy==${UNITYPY_VERSION}"
fi

mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || die "installation Last War introuvable ($PKG)"

cat > "$PY" <<'PYEOF'
import hashlib, io, json, lzma, os, re, shutil, struct, sys, time, zipfile
from collections import Counter, defaultdict

import UnityPy
from PIL import Image

out_path, kit_dir, catalog_path, *apk_paths = sys.argv[1:]
ENTRY="assets/AssetBundles/BundleFragment0.bytes"
MAX_BUNDLE_RAW=96*1024*1024
MAX_BUNDLE_DECODED=128*1024*1024
MAX_EXPORTED=900
MAX_OUTPUT_BYTES=300*1024*1024

with open(catalog_path,"r",encoding="utf-8") as f:
    catalog=json.load(f)

# Clean only Phase-30 decoded output, never the Phase-29 raw folder.
extract_root=os.path.join(kit_dir,"extracted")
if os.path.isdir(extract_root):
    for name in os.listdir(extract_root):
        p=os.path.join(extract_root,name)
        if os.path.isdir(p): shutil.rmtree(p)
        else: os.unlink(p)
for sub in ("heroes","drone","dominator","ui","equipment","other"):
    os.makedirs(os.path.join(extract_root,sub),exist_ok=True)

hero_aliases={
 "Loki":["loki"],"Kane":["kane"],"Ambolt":["ambolt"],"Gump":["gump"],"Elsa":["elsa"],
 "Farhad":["farhad"],"Richard":["richard"],"Braz":["braz"],"Cage":["cage"],"Maxwell":["maxwell"],"Monica":["monica"],
 "Murphy":["murphy","audie_murphy"],"Williams":["williams","william"],"Marshall":["marshall"],"Kimberly":["kimberly","kimberlyzombie"],
 "Stetmann":["stetmann","stettmann"],"McGregor":["mcgregor","mc_gregor","ewan_mcgregor"],"Fiona":["fiona"],"Swift":["swift"],
 "Schuyler":["schuyler"],"Carlie":["carlie","carli"],"Morrison":["morrison"],"Lucius":["lucius"],"Adam":["adam"]
}
all_aliases=sorted({x for vals in hero_aliases.values() for x in vals},key=len,reverse=True)

# These signatures are intentionally semantic; an extracted image is still only a graphics asset,
# not an authoritative heroId mapping unless its object name itself contains the established hero name.
CATEGORY_TERMS={
 "heroes":["heroiconsbig","heroiconssmall","hero_icon_","lw_herobody","halfbody","herohead","headicon"] + all_aliases,
 "drone":["hero_icon_drone","item_uav_equip_","tacticalchip","skillchip","uav","drone"],
 "dominator":["dominator","gorilla","cockatrice","hawk"],
 "ui":["uilwherosquad","lwuiformation","uiformation","squadequip","formation","qualityframe","rarity","rankicon","staricon"],
 "equipment":["lw_equip","equip_icon","unique_weapon","weapon_icon","equipment"]
}
LOWER_TERMS={k:[x.encode("utf-8").lower() for x in vals] for k,vals in CATEGORY_TERMS.items()}

found=None
for apk in apk_paths:
    try:
        with zipfile.ZipFile(apk) as z:
            try: info=z.getinfo(ENTRY)
            except KeyError: continue
            found=(apk,info); break
    except Exception: pass
if not found: raise SystemExit("BundleFragment0.bytes introuvable")
apk,info=found

def read_cstr(f,maxlen=16384):
    b=bytearray()
    while len(b)<maxlen:
        c=f.read(1)
        if not c: raise EOFError("cstr eof")
        if c==b"\0": return bytes(b)
        b+=c
    raise ValueError("cstr too long")

def align16(n): return (n+15)&~15

def lz4_block(src,expected=None):
    src=memoryview(src);i=0;out=bytearray()
    while i<len(src):
        token=src[i];i+=1;lit=token>>4
        if lit==15:
            while True:
                if i>=len(src): raise ValueError("lz4 literal overflow")
                x=src[i];i+=1;lit+=x
                if x!=255: break
        if i+lit>len(src): raise ValueError("lz4 literal range")
        out+=src[i:i+lit];i+=lit
        if i>=len(src): break
        if i+2>len(src): raise ValueError("lz4 offset eof")
        off=src[i]|(src[i+1]<<8);i+=2
        if off<=0 or off>len(out): raise ValueError("lz4 bad offset")
        ml=(token&15)+4
        if (token&15)==15:
            while True:
                if i>=len(src): raise ValueError("lz4 match overflow")
                x=src[i];i+=1;ml+=x
                if x!=255: break
        pos=len(out)-off
        for _ in range(ml): out.append(out[pos]);pos+=1
    return bytes(out)

def decomp(blob,typ,expected=None):
    typ &= 0x3f
    if typ==0:return blob
    if typ in (2,3):return lz4_block(blob,expected)
    if typ==1:
        for fmt in (lzma.FORMAT_AUTO,lzma.FORMAT_ALONE):
            try:return lzma.decompress(blob,format=fmt)
            except Exception:pass
        raise ValueError("lzma decode failed")
    raise ValueError(f"compression {typ}")

def parse_block_info(raw):
    if len(raw)<20:raise ValueError("blockinfo short")
    p=16;bc=struct.unpack_from(">I",raw,p)[0];p+=4
    if bc>200000:raise ValueError("bad block count")
    blocks=[]
    for _ in range(bc):
        u,c,fl=struct.unpack_from(">IIH",raw,p);p+=10;blocks.append((u,c,fl))
    nc=struct.unpack_from(">I",raw,p)[0];p+=4
    if nc>200000:raise ValueError("bad node count")
    nodes=[]
    for _ in range(nc):
        off,size,fl=struct.unpack_from(">qqI",raw,p);p+=20
        e=raw.find(b"\0",p)
        if e<0:raise ValueError("node name eof")
        path=raw[p:e].decode("utf-8","ignore");p=e+1
        nodes.append((off,size,fl,path))
    return blocks,nodes

def category_hits(data):
    low=data.lower(); out={}
    for cat,terms in LOWER_TERMS.items():
        hits=[t.decode("utf-8","ignore") for t in terms if t in low]
        if hits:out[cat]=hits[:20]
    return out

stats=Counter();errors=Counter();candidates=[]

# Pass 1: decode UnityFS payloads and retain only bundles that contain graphics semantics.
with zipfile.ZipFile(apk) as z, z.open(info) as f:
    total=info.file_size
    while f.tell()<total:
        start=f.tell();sig=f.read(8)
        if not sig:break
        if not sig.startswith(b"UnityFS"):
            buf=sig+f.read(min(2*1024*1024,total-f.tell()))
            q=buf.find(b"UnityFS\0")
            if q<0:continue
            start+=q;f.seek(start)
        try:
            if read_cstr(f)!=b"UnityFS":f.seek(start+1);continue
            fmt=struct.unpack(">I",f.read(4))[0]
            unity=read_cstr(f);rev=read_cstr(f)
            size=struct.unpack(">Q",f.read(8))[0]
            cs=struct.unpack(">I",f.read(4))[0]
            us=struct.unpack(">I",f.read(4))[0]
            flags=struct.unpack(">I",f.read(4))[0]
            hend=f.tell()
            if not (1<=fmt<=20) or size<=0 or start+size>total+16:raise ValueError("bad header")
            if size>MAX_BUNDLE_RAW:stats["bundle_raw_too_large"]+=1;f.seek(start+size);continue
            aligned=start+align16(hend-start) if fmt>=7 else hend
            meta_pos=start+size-cs if flags&0x80 else aligned
            f.seek(meta_pos);meta=decomp(f.read(cs),flags&0x3f,us)
            blocks,nodes=parse_block_info(meta)
            decoded_size=sum(u for u,_,_ in blocks)
            if decoded_size>MAX_BUNDLE_DECODED:stats["bundle_decoded_too_large"]+=1;f.seek(start+size);continue
            if flags&0x80:data_pos=aligned
            else:
                data_pos=meta_pos+cs
                if flags&0x200:data_pos=start+align16(data_pos-start)
            f.seek(data_pos);parts=[]
            for u,c,bfl in blocks:
                blob=f.read(c)
                if len(blob)!=c:raise ValueError("block truncated")
                parts.append(decomp(blob,bfl&0x3f,u))
            data=b"".join(parts);stats["bundles_decoded"]+=1
            hits=category_hits(data)
            # Node names sometimes preserve semantics even when serialized payload strings do not.
            node_text=" ".join(x[3] for x in nodes).lower().encode("utf-8","ignore")
            nh=category_hits(node_text)
            for cat,vals in nh.items():hits.setdefault(cat,[]).extend(x for x in vals if x not in hits.get(cat,[]))
            if hits:
                candidates.append({"start":start,"size":size,"hits":hits,"nodes":[x[3] for x in nodes[:12]]})
                stats["candidate_bundles"]+=1
            f.seek(start+size)
        except Exception as e:
            errors[type(e).__name__]+=1
            try:f.seek(start+1)
            except Exception:break

# Prefer hero/drone/dominator/UI candidates and avoid spending hours on generic equipment bundles.
def priority(c):
    cats=set(c["hits"])
    return (0 if "heroes" in cats else 1 if "drone" in cats else 2 if "dominator" in cats else 3 if "ui" in cats else 4,c["start"])
candidates.sort(key=priority)

safe_rx=re.compile(r"[^A-Za-z0-9_.-]+")
exported=[];output_bytes=0;seen_png_names=Counter()

def classify_asset(name,bundle_cats):
    low=name.lower()
    for hero,als in hero_aliases.items():
        if any(a in low for a in als): return "heroes",hero
    if any(x in low for x in ("uav","drone","skillchip","tacticalchip")):return "drone",None
    if any(x in low for x in ("dominator","gorilla","cockatrice","hawk")):return "dominator",None
    if any(x in low for x in ("formation","squad","rank","star","quality","frame")):return "ui",None
    if any(x in low for x in ("equip","weapon")):return "equipment",None
    for cat in ("heroes","drone","dominator","ui","equipment"):
        if cat in bundle_cats:return cat,None
    return "other",None

def save_image(img,name,objtype,candidate,path_id):
    global output_bytes
    if len(exported)>=MAX_EXPORTED or output_bytes>=MAX_OUTPUT_BYTES:return False
    cats=set(candidate["hits"]);cat,hero=classify_asset(name,cats)
    # In generic hero atlas bundles, retain sprites/textures even if the object name itself is opaque.
    low=name.lower()
    if cat=="heroes" and not hero and "heroes" not in cats:return False
    stem=safe_rx.sub("_",name).strip("._")[:90] or f"object_{path_id}"
    key=f"{cat}_{stem}";seen_png_names[key]+=1
    if seen_png_names[key]>1:stem=f"{stem}_{seen_png_names[key]}"
    filename=f"{candidate['start']:08x}_{path_id}_{stem}.png"
    rel=f"extracted/{cat}/{filename}"
    full=os.path.join(kit_dir,rel)
    try:
        img.save(full,"PNG",optimize=True)
        n=os.path.getsize(full)
    except Exception:
        try:
            img.save(full,"PNG");n=os.path.getsize(full)
        except Exception:return False
    output_bytes+=n
    exported.append({
      "name":name,"objectType":objtype,"category":cat,"heroName":hero,
      "bundleOffset":candidate["start"],"pathId":path_id,
      "width":getattr(img,"width",None),"height":getattr(img,"height",None),"bytes":n,
      "localPath":"/lab/local-assets/lastwar-kit-v1/"+rel
    })
    return True

# Pass 2: feed only candidate raw UnityFS bundles to UnityPy and export Sprite/Texture2D PNGs.
with zipfile.ZipFile(apk) as z, z.open(info) as f:
    for ci,c in enumerate(candidates):
        if len(exported)>=MAX_EXPORTED or output_bytes>=MAX_OUTPUT_BYTES:break
        try:
            f.seek(c["start"]);raw=f.read(c["size"])
            if len(raw)!=c["size"]:raise ValueError("raw bundle truncated")
            env=UnityPy.load(io.BytesIO(raw));stats["unitypy_bundles_loaded"]+=1
            # Export Sprite first; they are usually the correct cropped atlas regions.
            objects=list(env.objects)
            sprite_count=0
            for obj in objects:
                if obj.type.name!="Sprite":continue
                try:
                    d=obj.parse_as_object();name=str(getattr(d,"m_Name","") or f"sprite_{obj.path_id}")
                    img=d.image
                    if img and save_image(img,name,"Sprite",c,obj.path_id):
                        sprite_count+=1;stats["sprites_exported"]+=1
                except Exception as e:errors["sprite_export"]+=1
            # Export Texture2D only when the bundle did not expose Sprite objects, avoiding duplicate atlas dumps.
            if sprite_count==0:
                for obj in objects:
                    if obj.type.name!="Texture2D":continue
                    try:
                        d=obj.parse_as_object();name=str(getattr(d,"m_Name","") or f"texture_{obj.path_id}")
                        img=d.image
                        if img and save_image(img,name,"Texture2D",c,obj.path_id):stats["textures_exported"]+=1
                    except Exception:errors["texture_export"]+=1
        except Exception as e:
            errors["unitypy_bundle"]+=1

# Fold decoded assets back into the Phase-29 catalog so the existing witness page uses them immediately.
catalog["format"]="WFGG_LASTWAR_GRAPHICS_KIT_V1"
catalog["decodedByPhase30"]=True
catalog["phase30GeneratedLocalEpoch"]=int(time.time())
catalog["extractedAssets"]=exported
catalog.setdefault("stats",{})["phase30CandidateBundles"]=len(candidates)
catalog["stats"]["decodedSprites"]=stats["sprites_exported"]
catalog["stats"]["decodedTextures"]=stats["textures_exported"]
catalog["stats"]["decodedRasterAssets"]=len(exported)

for hero,node in catalog.get("heroCandidates",{}).items():
    vals=[x["localPath"] for x in exported if x.get("heroName")==hero]
    old=list(node.get("directAssets") or [])
    node["directAssets"]=list(dict.fromkeys(vals+old))[:30]

catalog["droneAssets"]=[x["localPath"] for x in exported if x["category"]=="drone"][:120]
catalog["dominatorAssets"]=[x["localPath"] for x in exported if x["category"]=="dominator"][:120]
catalog["uiAssets"]=[x["localPath"] for x in exported if x["category"]=="ui"][:200]
catalog["equipmentAssets"]=[x["localPath"] for x in exported if x["category"]=="equipment"][:200]

with open(catalog_path,"w",encoding="utf-8") as f:json.dump(catalog,f,ensure_ascii=False,indent=2)
with open(os.path.join(kit_dir,"catalog.js"),"w",encoding="utf-8") as f:
    f.write("window.WFGG_LASTWAR_GRAPHICS_KIT=")
    json.dump(catalog,f,ensure_ascii=False,separators=(",",":"));f.write(";\n")

with open(out_path,"w",encoding="utf-8") as o:
    o.write("WfGg Last War LAB — PHASE 30 UNITY SPRITE EXTRACTION\n")
    o.write("GAME DATA LOCAL ONLY · no Last War network connection · graphics remain local\n\n")
    o.write(f"SOURCE={os.path.basename(apk)}:{ENTRY}\n")
    o.write(f"unityPyVersion={getattr(UnityPy,'__version__','unknown')}\n")
    o.write(f"fragmentBytes={info.file_size}\n")
    o.write(f"bundlesDecoded={stats['bundles_decoded']}\n")
    o.write(f"candidateBundles={len(candidates)}\n")
    o.write(f"unityPyBundlesLoaded={stats['unitypy_bundles_loaded']}\n")
    o.write(f"spritesExported={stats['sprites_exported']}\n")
    o.write(f"texturesExported={stats['textures_exported']}\n")
    o.write(f"decodedRasterAssets={len(exported)}\n")
    o.write(f"decodedRasterBytes={output_bytes}\n")
    o.write(f"catalogUpdated={catalog_path}\n")
    o.write("\nHERO_DECODED_COVERAGE\n")
    for hero,node in catalog.get("heroCandidates",{}).items():
        vals=[x for x in exported if x.get("heroName")==hero]
        o.write(f"  heroId={node.get('heroId')} name={hero} decodedAssets={len(vals)}\n")
        for x in vals[:5]:o.write(f"    asset={x['name']} {x['width']}x{x['height']} path={x['localPath']}\n")
    o.write("\nCATEGORY_COUNTS\n")
    cc=Counter(x["category"] for x in exported)
    for k in ("heroes","drone","dominator","ui","equipment","other"):o.write(f"  {k}={cc[k]}\n")
    o.write("\nCANDIDATE_BUNDLE_SAMPLES\n")
    for c in candidates[:80]:o.write(f"  offset={c['start']} size={c['size']} categories={','.join(c['hits'])} hits={';'.join(sum(c['hits'].values(),[])[:12])}\n")
    o.write("\nERROR_COUNTS\n")
    for k,v in errors.most_common():o.write(f"  {k}={v}\n")
    o.write("\nGUARDRAILS\n")
    o.write("  graphics_asset_name_is_not_new_heroId_mapping=true\n")
    o.write("  unknown_50016_50017_remain_unresolved_without_authoritative_table_row=true\n")
    o.write("  no_generated_graphics_committed_to_git=true\n")
    o.write("  next=reload_squad_witness_page_and_compare_real_portraits_drone_ui_assets\n")

print(f"PHASE30_DONE candidates={len(candidates)} images={len(exported)} sprites={stats['sprites_exported']} textures={stats['textures_exported']} output={out_path}")
PYEOF

python "$PY" "$OUT" "$KIT_DIR" "$CATALOG" "${APK_PATHS[@]}"
chmod 600 "$OUT" 2>/dev/null || true
rm -f "$PY"

printf '=== PHASE 30 TERMINEE ===\n'
printf 'Aucune connexion Last War n\x27a été effectuée.\n'
printf 'Recharge la page escouades dans Chrome.\n'
printf 'Fichier à partager : Téléchargements/WFGG_LASTWAR_PHASE30_UNITY_SPRITE_EXTRACTION_REDACTED.txt\n'
