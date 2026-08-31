#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

from pathlib import Path
from collections import Counter
import json, os, re, sys

import UnityPy
from PIL import Image

ROOT = Path(sys.argv[1]).resolve()
V21 = ROOT / "frontend/lab/audie-astc-v21-data/manifest.json"
OUT = ROOT / "frontend/lab/audie-stream-v22-data"
IMG = OUT / "images"
RAW = OUT / "raw"
MAN = OUT / "manifest.json"
OUT.mkdir(parents=True, exist_ok=True)
IMG.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)
UnityPy.config.FALLBACK_UNITY_VERSION = "2019.4.41f1"

try:
    import texture2ddecoder
    DECODER = "OK"
except Exception as e:
    texture2ddecoder = None
    DECODER = f"{type(e).__name__}:{e}"

ASTC = {
    48:(4,4,"ASTC_4x4"),49:(5,5,"ASTC_5x5"),50:(6,6,"ASTC_6x6"),
    51:(8,8,"ASTC_8x8"),52:(10,10,"ASTC_10x10"),53:(12,12,"ASTC_12x12"),
}

def safe(s):
    z=re.sub(r"[^A-Za-z0-9._-]+","_",str(s or "")).strip("._")
    return z[:110] or "asset"

def as_int(v,d=0):
    try:return int(v)
    except Exception:return d

def stream_path(s):
    p=str((s or {}).get("path") or "").replace("\\","/")
    return p

def stream_basename(p):
    p=str(p or "").replace("\\","/")
    if p.lower().startswith("archive:/"): p=p[9:]
    return p.rstrip("/").split("/")[-1]

def node_bytes(node):
    # BundleFile children are commonly EndianBinaryReader instances. Other
    # UnityPy file wrappers expose the same bytes through .reader.bytes.
    try:
        b=getattr(node,"bytes",None)
        if b is not None:
            b=bytes(b)
            if b:return b
    except Exception:pass
    try:
        rd=getattr(node,"reader",None)
        b=getattr(rd,"bytes",None)
        if b is not None:
            b=bytes(b)
            if b:return b
    except Exception:pass
    return b""

def walk_embedded(node,prefix="",seen=None,depth=0):
    if seen is None:seen=set()
    if depth>8 or id(node) in seen:return
    seen.add(id(node))
    try: children=getattr(node,"files",None)
    except Exception: children=None
    if not isinstance(children,dict):return
    # SerializedFile.files is {pathID:ObjectReader}; Bundle/Web/APK files use
    # string keys. Only recurse through real named container children.
    for k,v in children.items():
        if not isinstance(k,str):continue
        name=(prefix+"/"+k).strip("/")
        yield name,v
        yield from walk_embedded(v,name,seen,depth+1)

def matches_resource(candidate,target):
    a=str(candidate or "").replace("\\","/").lower().strip("/")
    b=str(target or "").replace("\\","/").lower()
    if b.startswith("archive:/"):b=b[9:]
    b=b.strip("/")
    if not a or not b:return False
    return a==b or a.endswith("/"+b) or a.split("/")[-1]==b.split("/")[-1]

def slice_payload(blob,offset,size,expected=0):
    if not blob:return b""
    offset=max(0,as_int(offset)); size=max(0,as_int(size))
    if size<=0:size=expected
    if size<=0 or offset>=len(blob):return b""
    end=min(len(blob),offset+size)
    raw=blob[offset:end]
    # ASTC payload has a deterministic block size; StreamData can occasionally
    # report a padded region. Trim only when enough bytes are available.
    if expected and len(raw)>=expected:raw=raw[:expected]
    return raw

def expected_astc(w,h,fmt):
    if fmt not in ASTC or w<=0 or h<=0:return 0
    bw,bh,_=ASTC[fmt]
    return ((w+bw-1)//bw)*((h+bh-1)//bh)*16

def decode_astc(raw,w,h,fmt,out_png):
    if texture2ddecoder is None:raise RuntimeError("texture2ddecoder unavailable: "+DECODER)
    bw,bh,_=ASTC[fmt]
    rgba=texture2ddecoder.decode_astc(raw,w,h,bw,bh)
    Image.frombytes("RGBA",(w,h),rgba,"raw","BGRA").save(out_png)

if not V21.is_file():
    raise SystemExit("ERROR: V21 manifest absent; run V21 first")
M=json.loads(V21.read_text("utf-8"))
source=[dict(x) for x in M.get("items",[]) if not x.get("decoded")]

# Build a tiny disk index only for resource basenames actually requested by the
# 44 StreamData targets. This avoids a blind rescan of all game assets.
needed={stream_basename(stream_path(x.get("streamData"))) .lower() for x in source if stream_basename(stream_path(x.get("streamData")))}
disk_index={}
print("V22_DISK_INDEX_START",f"needed={len(needed)}",flush=True)
for base,dirs,files in os.walk(ROOT):
    # generated output trees cannot contain the original resource
    dirs[:]=[d for d in dirs if d not in {".git","node_modules","audie-stream-v22-data"}]
    for fn in files:
        low=fn.lower()
        if low in needed:
            disk_index.setdefault(low,[]).append(str(Path(base)/fn))
print("V22_DISK_INDEX_READY",f"matchedNames={len(disk_index)}",f"files={sum(map(len,disk_index.values()))}",flush=True)

bundle_cache={}
def load_bundle(bp):
    key=str(bp)
    if key not in bundle_cache:
        bundle_cache[key]=UnityPy.load(key)
    return bundle_cache[key]

def recover_from_embedded(bp,sp,off,size,expected):
    env=load_bundle(bp)
    root=getattr(env,"file",None)
    names=[]
    best=[]
    for name,node in walk_embedded(root):
        names.append(name)
        if matches_resource(name,sp):
            blob=node_bytes(node)
            raw=slice_payload(blob,off,size,expected)
            best.append((name,len(blob),raw))
    for name,blen,raw in best:
        if raw:return raw,"embedded:"+name,names
    return b"","",names

def recover_from_disk(sp,off,size,expected):
    bn=stream_basename(sp).lower()
    for fp in disk_index.get(bn,[]):
        try:
            blob=Path(fp).read_bytes()
            raw=slice_payload(blob,off,size,expected)
            if raw:return raw,"disk:"+fp
        except Exception:pass
    return b"",""

items=[]
print("AUDIE_STREAM_V22_START",f"targets={len(source)}",f"decoder={DECODER}",flush=True)
for i,r in enumerate(source,1):
    sp=stream_path(r.get("streamData")); sd=r.get("streamData") or {}
    fmt=as_int(r.get("textureFormat")); w=as_int(r.get("width")); h=as_int(r.get("height"))
    off=as_int(sd.get("offset")); size=as_int(sd.get("size")); expected=expected_astc(w,h,fmt)
    bp=Path(str(r.get("bundlePath") or ""))
    rec=dict(r)
    rec.update({
        "streamPath":sp,"streamBasename":stream_basename(sp),"offset":off,"streamSize":size,
        "expectedBytes":expected,"resolver":"","resolvedResource":"","rawBytesV22":0,
        "rawSrcV22":"","srcV22":"","decodedV22":False,"v22Errors":[],"embeddedNames":[],
    })
    print("V22_TARGET",f"{i}/{len(source)}",rec.get("name"),bp.name,f"fmt={fmt}",f"stream={sp or '-'}",flush=True)
    raw=b""
    if not sp:
        rec["v22Errors"].append("no_stream_path")
    elif not bp.is_file():
        rec["v22Errors"].append("bundle_absent")
    else:
        try:
            raw,method,names=recover_from_embedded(bp,sp,off,size,expected)
            rec["embeddedNames"]=names[:80]
            if raw:
                rec["resolver"]="embedded_unityfs"; rec["resolvedResource"]=method[9:]
        except Exception as e:
            rec["v22Errors"].append(f"embedded:{type(e).__name__}:{e}")
    if not raw and sp:
        try:
            raw,method=recover_from_disk(sp,off,size,expected)
            if raw:
                rec["resolver"]="disk_resource"; rec["resolvedResource"]=method[5:]
        except Exception as e:
            rec["v22Errors"].append(f"disk:{type(e).__name__}:{e}")
    if raw:
        rec["rawBytesV22"]=len(raw)
        rn=f"{safe(rec.get('name'))}_p{safe(rec.get('pathID'))}_{safe(bp.name)}.bin"
        rp=RAW/rn; rp.write_bytes(raw); rec["rawSrcV22"]="/lab/audie-stream-v22-data/raw/"+rn
        if fmt in ASTC and w and h:
            try:
                pn=rn[:-4]+".png"; pp=IMG/pn
                decode_astc(raw,w,h,fmt,pp)
                rec["decodedV22"]=True; rec["srcV22"]="/lab/audie-stream-v22-data/images/"+pn
            except Exception as e:
                rec["v22Errors"].append(f"decode:{type(e).__name__}:{e}")
    else:
        rec["v22Errors"].append("stream_resource_or_payload_unresolved")
    items.append(rec)

# Put likely final/icon/preview renders first, material maps last.
def rank(x):
    t=(str(x.get("name") or "")+" "+str(x.get("bundle") or "")).lower()
    s=200 if x.get("decodedV22") else 0
    if x.get("rawBytesV22"):s+=80
    if re.search(r"hero_icon|icon|preview|formation|team|vehicle|car|tank|avatar",t):s+=45
    if x.get("likelyRendered2D"):s+=30
    if x.get("surfaceMap") or re.search(r"(?:^|[_\-.])(high[_\-.]?)?[dns](?:$|[_\-.])|normal|spec|rough|metal",str(x.get("name") or "").lower()):s-=60
    return s
for x in items:x["scoreV22"]=rank(x)
items.sort(key=lambda x:(-x["scoreV22"],str(x.get("name") or "").lower()))

c=Counter()
for x in items:
    c["targets"]+=1
    c["streamed"]+=bool(x.get("streamPath"))
    c["embeddedMatch"]+=x.get("resolver")=="embedded_unityfs"
    c["diskMatch"]+=x.get("resolver")=="disk_resource"
    c["rawRecovered"]+=bool(x.get("rawBytesV22"))
    c["decoded"]+=bool(x.get("decodedV22"))
    c["unresolved"]+=not bool(x.get("rawBytesV22"))
res={
    "format":"WFGG_LASTWAR_AUDIE_STREAM_V22",
    "verdict":"STREAM_IMAGES_DECODED" if c["decoded"] else ("STREAM_BYTES_RECOVERED" if c["rawRecovered"] else "RESOURCE_CONTAINER_NOT_IN_TARGET_BUNDLE"),
    "decoder":DECODER,"counts":dict(c),"diskResourceNames":{k:v for k,v in disk_index.items()},"items":items,
    "rules":[
        "V22 resolves m_StreamData inside the actual UnityFS/AssetBundle before trying standalone files.",
        "archive:/ paths are matched by full suffix and resource basename.",
        "Payload bytes are sliced using StreamData offset/size and checked against the deterministic ASTC block size.",
        "If embeddedMatch and diskMatch remain zero, the resource lives outside the target bundle and must be recovered from the APK/split/remote cache container rather than decoded again.",
    ],
}
MAN.write_text(json.dumps(res,ensure_ascii=False,indent=2)+"\n","utf-8")
print("AUDIE_STREAM_V22_READY",f"verdict={res['verdict']}",f"embedded={c['embeddedMatch']}",f"disk={c['diskMatch']}",f"raw={c['rawRecovered']}",f"decoded={c['decoded']}",f"unresolved={c['unresolved']}",flush=True)
for x in items[:30]:
    print("V22_TEXTURE","PNG" if x.get("decodedV22") else ("RAW" if x.get("rawBytesV22") else "MISS"),x.get("name"),f"{x.get('width')}x{x.get('height')}",x.get("formatName"),f"resolver={x.get('resolver') or '-'}",f"res={x.get('resolvedResource') or x.get('streamBasename') or '-'}",flush=True)
print("JSON="+str(MAN),flush=True)
print("VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-stream-v22.html?v=22",flush=True)
