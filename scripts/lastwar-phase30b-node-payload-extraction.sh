#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 30B
# OFFLINE ONLY. Bypasses UnityPy's BundleFile parser by decoding UnityFS with the
# proven local parser, materializing bundle node payloads, then letting UnityPy
# parse the resulting SerializedFile/resource set from a temporary directory.
# No Last War network connection. No gameplay automation.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOWNLOADS="${HOME}/storage/downloads"
KIT_DIR="${ROOT}/frontend/lab/local-assets/lastwar-kit-v1"
CATALOG="${KIT_DIR}/catalog.json"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE30B_NODE_PAYLOAD_EXTRACTION_REDACTED.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase30b-node-payload-extraction.py"

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || die "python Termux absent"
command -v pm >/dev/null 2>&1 || die "commande Android pm absente"
[[ -s "$CATALOG" ]] || die "Kit Phase 29 absent: $CATALOG"
python - <<'PYTEST' >/dev/null 2>&1 || die "UnityPy/Pillow absents. Relance d'abord scripts/lastwar-phase30-termux-deps-fix.sh"
import UnityPy
from PIL import Image
PYTEST
mkdir -p "$(dirname "$PY")" "$KIT_DIR/extracted"

mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || die "installation Last War introuvable ($PKG)"

cat > "$PY" <<'PYEOF'
import io, json, lzma, os, re, shutil, struct, sys, tempfile, time, zipfile
from collections import Counter

import UnityPy
from PIL import Image

out_path, kit_dir, catalog_path, *apk_paths = sys.argv[1:]
ENTRY="assets/AssetBundles/BundleFragment0.bytes"
MAX_CANDIDATES_TO_LOAD=520
MAX_EXPORTED=1200
MAX_OUTPUT_BYTES=350*1024*1024
MAX_BUNDLE_RAW=96*1024*1024
MAX_BUNDLE_DECODED=160*1024*1024

with open(catalog_path,"r",encoding="utf-8") as f:
    catalog=json.load(f)

extract_root=os.path.join(kit_dir,"extracted")
for sub in ("heroes","drone","dominator","ui","equipment","other"):
    os.makedirs(os.path.join(extract_root,sub),exist_ok=True)

hero_aliases={
 "Loki":["loki"],"Kane":["kane"],"Ambolt":["ambolt"],"Gump":["gump"],"Elsa":["elsa"],
 "Farhad":["farhad"],"Richard":["richard"],"Braz":["braz"],"Cage":["cage"],"Maxwell":["maxwell"],"Monica":["monica"],
 "Murphy":["murphy","audie_murphy"],"Williams":["williams","william"],"Marshall":["marshall"],"Kimberly":["kimberly","kimberlyzombie"],
 "Stetmann":["stetmann","stettmann"],"McGregor":["mcgregor","mc_gregor","ewan_mcgregor"],"Fiona":["fiona"],"Swift":["swift"],
 "Schuyler":["schuyler"],"Carlie":["carlie","carli"],"Morrison":["morrison"],"Lucius":["lucius"],"Adam":["adam"]
}
active_names={"Murphy","Williams","Marshall","Kimberly","Stetmann","Carlie","Lucius","Schuyler","Morrison","McGregor","Adam","Swift","Fiona"}
all_aliases=sorted({x for vals in hero_aliases.values() for x in vals},key=len,reverse=True)
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
        if p+10>len(raw):raise ValueError("block list truncated")
        u,c,fl=struct.unpack_from(">IIH",raw,p);p+=10;blocks.append((u,c,fl))
    if p+4>len(raw):raise ValueError("node count missing")
    nc=struct.unpack_from(">I",raw,p)[0];p+=4
    if nc>200000:raise ValueError("bad node count")
    nodes=[]
    for _ in range(nc):
        if p+20>len(raw):raise ValueError("node record truncated")
        off,size,fl=struct.unpack_from(">qqI",raw,p);p+=20
        e=raw.find(b"\0",p)
        if e<0:raise ValueError("node name eof")
        path=raw[p:e].decode("utf-8","ignore");p=e+1
        nodes.append((off,size,fl,path))
    return blocks,nodes

def decode_bundle(f,start,total,want_data=True):
    f.seek(start)
    if read_cstr(f)!=b"UnityFS":raise ValueError("not UnityFS")
    fmt=struct.unpack(">I",f.read(4))[0];read_cstr(f);read_cstr(f)
    size=struct.unpack(">Q",f.read(8))[0]
    cs=struct.unpack(">I",f.read(4))[0];us=struct.unpack(">I",f.read(4))[0];flags=struct.unpack(">I",f.read(4))[0]
    hend=f.tell()
    if not (1<=fmt<=20) or size<=0 or start+size>total+16:raise ValueError("bad header")
    if size>MAX_BUNDLE_RAW:raise OverflowError("bundle raw too large")
    aligned=start+align16(hend-start) if fmt>=7 else hend
    meta_pos=start+size-cs if flags&0x80 else aligned
    f.seek(meta_pos);meta=decomp(f.read(cs),flags&0x3f,us)
    blocks,nodes=parse_block_info(meta)
    decoded_size=sum(u for u,_,_ in blocks)
    if decoded_size>MAX_BUNDLE_DECODED:raise OverflowError("bundle decoded too large")
    if not want_data:return size,nodes,None
    if flags&0x80:data_pos=aligned
    else:
        data_pos=meta_pos+cs
        if flags&0x200:data_pos=start+align16(data_pos-start)
    f.seek(data_pos);parts=[]
    for u,c,bfl in blocks:
        blob=f.read(c)
        if len(blob)!=c:raise ValueError("block truncated")
        parts.append(decomp(blob,bfl&0x3f,u))
    return size,nodes,b"".join(parts)

def category_hits(data,nodes):
    low=data.lower()+b" "+" ".join(x[3] for x in nodes).lower().encode("utf-8","ignore")
    out={}
    for cat,terms in LOWER_TERMS.items():
        vals=[t.decode("utf-8","ignore") for t in terms if t in low]
        if vals:out[cat]=vals[:30]
    return out

def hero_names_from_hits(hits):
    blob=" ".join(sum(hits.values(),[])).lower()
    return [name for name,als in hero_aliases.items() if any(a in blob for a in als)]

def candidate_priority(c):
    names=set(hero_names_from_hits(c["hits"]))
    if names & active_names:return (0,c["start"])
    cats=set(c["hits"])
    if "drone" in cats:return (1,c["start"])
    if "dominator" in cats:return (2,c["start"])
    if "ui" in cats:return (3,c["start"])
    if "heroes" in cats:return (4,c["start"])
    return (5,c["start"])

stats=Counter();errors=Counter();error_samples=[];candidates=[]
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
            size,nodes,data=decode_bundle(f,start,total,True)
            stats["bundles_decoded"]+=1
            hits=category_hits(data,nodes)
            if hits:
                candidates.append({"start":start,"size":size,"hits":hits})
            f.seek(start+size)
        except OverflowError:
            stats["oversize_skipped"]+=1
            try:f.seek(start+1)
            except Exception:break
        except Exception as e:
            errors["scan_bundle"]+=1
            try:f.seek(start+1)
            except Exception:break

candidates.sort(key=candidate_priority)
candidates=candidates[:MAX_CANDIDATES_TO_LOAD]

safe_rx=re.compile(r"[^A-Za-z0-9_.-]+")
exported=[];output_bytes=0;name_counts=Counter()

def classify_asset(name,candidate):
    low=name.lower()
    for hero,als in hero_aliases.items():
        if any(a in low for a in als):return "heroes",hero,"object_name"
    if any(x in low for x in ("uav","drone","skillchip","tacticalchip")):return "drone",None,"object_name"
    if any(x in low for x in ("dominator","gorilla","cockatrice","hawk")):return "dominator",None,"object_name"
    if any(x in low for x in ("formation","squad","rank","star","quality","frame")):return "ui",None,"object_name"
    if any(x in low for x in ("equip","weapon")):return "equipment",None,"object_name"
    cats=set(candidate["hits"])
    for cat in ("heroes","drone","dominator","ui","equipment"):
        if cat in cats:return cat,None,"bundle_category"
    return "other",None,"unknown"

def save_image(img,name,objtype,candidate,path_id):
    global output_bytes
    if len(exported)>=MAX_EXPORTED or output_bytes>=MAX_OUTPUT_BYTES:return False
    cat,hero,basis=classify_asset(name,candidate)
    stem=safe_rx.sub("_",name).strip("._")[:90] or f"object_{path_id}"
    key=f"{cat}_{stem}";name_counts[key]+=1
    if name_counts[key]>1:stem=f"{stem}_{name_counts[key]}"
    filename=f"{candidate['start']:08x}_{path_id}_{stem}.png"
    rel=f"extracted/{cat}/{filename}";full=os.path.join(kit_dir,rel)
    try:img.save(full,"PNG",optimize=True)
    except Exception:img.save(full,"PNG")
    n=os.path.getsize(full);output_bytes+=n
    exported.append({"name":name,"objectType":objtype,"category":cat,"heroName":hero,"mappingBasis":basis,
                     "bundleOffset":candidate["start"],"pathId":path_id,"width":getattr(img,"width",None),
                     "height":getattr(img,"height",None),"bytes":n,"localPath":"/lab/local-assets/lastwar-kit-v1/"+rel})
    return True

# Critical fallback: the custom parser already proves we can decode UnityFS. Instead of
# asking UnityPy to parse the raw bundle again, materialize each decoded node payload and
# let UnityPy load the node set as a local folder, preserving dependency/resource siblings.
with zipfile.ZipFile(apk) as z, z.open(info) as f:
    total=info.file_size
    for idx,c in enumerate(candidates):
        if len(exported)>=MAX_EXPORTED or output_bytes>=MAX_OUTPUT_BYTES:break
        try:
            size,nodes,data=decode_bundle(f,c["start"],total,True)
            with tempfile.TemporaryDirectory(prefix="wfgg-u-node-") as td:
                written=0
                for ni,(off,nsize,nfl,path) in enumerate(nodes):
                    if off<0 or nsize<=0 or off+nsize>len(data):continue
                    payload=data[off:off+nsize]
                    base=os.path.basename(path.replace("\\","/")) or f"node_{ni}"
                    base=safe_rx.sub("_",base)[:120] or f"node_{ni}"
                    dst=os.path.join(td,base)
                    if os.path.exists(dst):dst=os.path.join(td,f"{ni}_{base}")
                    with open(dst,"wb") as q:q.write(payload)
                    written+=1
                stats["node_payloads_written"]+=written
                if not written:raise ValueError("no node payloads")
                env=UnityPy.load(td)
                objects=list(env.objects)
                stats["node_sets_loaded"]+=1
                stats["objects_seen"]+=len(objects)
                sprites=[o for o in objects if getattr(o.type,"name","")=="Sprite"]
                for obj in sprites:
                    try:
                        d=obj.parse_as_object();name=str(getattr(d,"m_Name","") or f"sprite_{obj.path_id}")
                        img=d.image
                        if img and save_image(img,name,"Sprite",c,obj.path_id):stats["sprites_exported"]+=1
                    except Exception as e:
                        errors["sprite_export"]+=1
                        if len(error_samples)<20:error_samples.append(f"sprite {type(e).__name__}: {str(e)[:180]}")
                if not sprites:
                    for obj in objects:
                        if getattr(obj.type,"name","")!="Texture2D":continue
                        try:
                            d=obj.parse_as_object();name=str(getattr(d,"m_Name","") or f"texture_{obj.path_id}")
                            img=d.image
                            if img and save_image(img,name,"Texture2D",c,obj.path_id):stats["textures_exported"]+=1
                        except Exception as e:
                            errors["texture_export"]+=1
                            if len(error_samples)<20:error_samples.append(f"texture {type(e).__name__}: {str(e)[:180]}")
        except Exception as e:
            errors["node_set_load"]+=1
            if len(error_samples)<20:error_samples.append(f"bundleOffset={c['start']} {type(e).__name__}: {str(e)[:220]}")

catalog["decodedByPhase30NodeFallback"]=True
catalog["phase30bGeneratedLocalEpoch"]=int(time.time())
old=[x for x in catalog.get("extractedAssets",[]) if isinstance(x,dict)]
combined=[];seen=set()
for x in exported+old:
    k=x.get("localPath")
    if not k or k in seen:continue
    seen.add(k);combined.append(x)
catalog["extractedAssets"]=combined
catalog.setdefault("stats",{})["phase30bNodeSetsLoaded"]=stats["node_sets_loaded"]
catalog["stats"]["phase30bDecodedSprites"]=stats["sprites_exported"]
catalog["stats"]["phase30bDecodedTextures"]=stats["textures_exported"]
catalog["stats"]["decodedRasterAssets"]=len(combined)
for hero,node in catalog.get("heroCandidates",{}).items():
    vals=[x["localPath"] for x in exported if x.get("heroName")==hero and x.get("mappingBasis")=="object_name"]
    olda=list(node.get("directAssets") or [])
    node["directAssets"]=list(dict.fromkeys(vals+olda))[:40]
catalog["droneAssets"]=list(dict.fromkeys([x["localPath"] for x in combined if x.get("category")=="drone"]))[:160]
catalog["dominatorAssets"]=list(dict.fromkeys([x["localPath"] for x in combined if x.get("category")=="dominator"]))[:160]
catalog["uiAssets"]=list(dict.fromkeys([x["localPath"] for x in combined if x.get("category")=="ui"]))[:250]
catalog["equipmentAssets"]=list(dict.fromkeys([x["localPath"] for x in combined if x.get("category")=="equipment"]))[:250]
with open(catalog_path,"w",encoding="utf-8") as f:json.dump(catalog,f,ensure_ascii=False,indent=2)
with open(os.path.join(kit_dir,"catalog.js"),"w",encoding="utf-8") as f:
    f.write("window.WFGG_LASTWAR_GRAPHICS_KIT=");json.dump(catalog,f,ensure_ascii=False,separators=(",",":"));f.write(";\n")

with open(out_path,"w",encoding="utf-8") as o:
    o.write("WfGg Last War LAB — PHASE 30B NODE PAYLOAD EXTRACTION\n")
    o.write("GAME DATA LOCAL ONLY · custom UnityFS decode -> node payloads -> UnityPy\n\n")
    o.write(f"SOURCE={os.path.basename(apk)}:{ENTRY}\n")
    o.write(f"unityPyVersion={getattr(UnityPy,'__version__','unknown')}\n")
    o.write(f"bundlesDecoded={stats['bundles_decoded']}\n")
    o.write(f"candidateBundlesSelected={len(candidates)}\n")
    o.write(f"nodePayloadsWritten={stats['node_payloads_written']}\n")
    o.write(f"nodeSetsLoaded={stats['node_sets_loaded']}\n")
    o.write(f"objectsSeen={stats['objects_seen']}\n")
    o.write(f"spritesExported={stats['sprites_exported']}\n")
    o.write(f"texturesExported={stats['textures_exported']}\n")
    o.write(f"decodedRasterAssetsThisRun={len(exported)}\n")
    o.write(f"decodedRasterBytesThisRun={output_bytes}\n")
    o.write(f"catalogTotalExtractedAssets={len(combined)}\n")
    o.write("\nHERO_EXPLICIT_OBJECT_NAME_COVERAGE\n")
    for hero,node in catalog.get("heroCandidates",{}).items():
        vals=[x for x in exported if x.get("heroName")==hero and x.get("mappingBasis")=="object_name"]
        o.write(f"  heroId={node.get('heroId')} name={hero} assets={len(vals)}\n")
        for x in vals[:4]:o.write(f"    asset={x['name']} {x['width']}x{x['height']} path={x['localPath']}\n")
    o.write("\nCATEGORY_COUNTS_THIS_RUN\n")
    cc=Counter(x["category"] for x in exported)
    for k in ("heroes","drone","dominator","ui","equipment","other"):o.write(f"  {k}={cc[k]}\n")
    o.write("\nERROR_COUNTS\n")
    for k,v in errors.most_common():o.write(f"  {k}={v}\n")
    o.write("\nERROR_SAMPLES\n")
    for s in error_samples:o.write(f"  {s}\n")
    o.write("\nGUARDRAILS\n")
    o.write("  bundle_category_only_does_not_create_heroId_mapping=true\n")
    o.write("  hero_mapping_requires_established_name_in_object_name=true\n")
    o.write("  unknown_50016_50017_remain_unresolved_without_authoritative_table_row=true\n")
    o.write("  no_generated_graphics_committed_to_git=true\n")
    o.write("  next=reload_squad_witness_page_if_explicit_portraits_exported\n")

print(f"PHASE30B_DONE nodeSets={stats['node_sets_loaded']} images={len(exported)} sprites={stats['sprites_exported']} textures={stats['textures_exported']} output={out_path}")
PYEOF

python "$PY" "$OUT" "$KIT_DIR" "$CATALOG" "${APK_PATHS[@]}"
chmod 600 "$OUT" 2>/dev/null || true
rm -f "$PY"

printf '=== PHASE 30B TERMINEE ===\n'
printf 'Aucune connexion Last War n\x27a été effectuée.\n'
printf 'Recharge la page escouades dans Chrome si des images ont été exportées.\n'
printf 'Fichier à partager : Téléchargements/WFGG_LASTWAR_PHASE30B_NODE_PAYLOAD_EXTRACTION_REDACTED.txt\n'
