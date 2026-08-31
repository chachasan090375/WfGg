#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

from pathlib import Path
from collections import defaultdict
import json, os, re, sys

import UnityPy

ROOT = Path(sys.argv[1]).resolve()
V14 = ROOT / "frontend/lab/audie-assembly-2d-v14-data/manifest.json"
OUT = ROOT / "frontend/lab/audie-2d-raw-v20-data"
IMG = OUT / "images"
MAN = OUT / "manifest.json"
OUT.mkdir(parents=True, exist_ok=True)
IMG.mkdir(parents=True, exist_ok=True)
UnityPy.config.FALLBACK_UNITY_VERSION = "2019.4.41f1"

if not V14.is_file():
    raise SystemExit("ERROR: V14 manifest absent; run lastwar-audie-assembly-2d-v14.sh first")

M = json.loads(V14.read_text("utf-8"))

def safe(s):
    z = re.sub(r"[^A-Za-z0-9._-]+", "_", str(s or "")).strip("._")
    return z[:120] or "asset"

def typ(o):
    return str(getattr(getattr(o, "type", None), "name", "") or "")

def pid(o):
    return int(getattr(o, "path_id", 0) or 0)

def sfname(o):
    af = getattr(o, "assets_file", None)
    return str(getattr(af, "name", "") or getattr(af, "file_name", "") or getattr(af, "path", "") or "")

def tree(o):
    try:
        return o.read_typetree(wrap=False, check_read=False)
    except TypeError:
        try: return o.read_typetree()
        except Exception: return {}
    except Exception:
        return {}

def as_int(v, default=0):
    try: return int(v)
    except Exception: return default

def stream_info(tr):
    if not isinstance(tr, dict): return {}
    s = tr.get("m_StreamData") or tr.get("streamData") or {}
    if not isinstance(s, dict): return {}
    return {
        "path": str(s.get("path") or s.get("m_Path") or ""),
        "offset": as_int(s.get("offset", s.get("m_Offset", 0))),
        "size": as_int(s.get("size", s.get("m_Size", 0))),
    }

def texture_format(tr, d=None):
    vals=[]
    if isinstance(tr, dict):
        for k in ("m_TextureFormat","textureFormat","format"):
            if k in tr: vals.append(tr.get(k))
    if d is not None:
        for k in ("m_TextureFormat","texture_format"):
            try: vals.append(getattr(d,k))
            except Exception: pass
    for v in vals:
        if v is None: continue
        try:
            n=getattr(v,"name",None)
            if n: return str(n)
        except Exception: pass
        return str(v)
    return ""

def audie_record(r):
    s=" ".join(str(r.get(k) or "") for k in ("name","bundle","bundlePath","serializedFile"))
    return "audie" in s.lower()

def find_obj(env, path_id, wanted_type=""):
    exact=[]
    for o in env.objects:
        if pid(o)==path_id:
            if not wanted_type or typ(o)==wanted_type: return o
            exact.append(o)
    return exact[0] if exact else None

def save_image(o, rec, method):
    d=o.read()
    tr=tree(o)
    rec["textureFormat"] = rec.get("textureFormat") or texture_format(tr,d)
    raw=None
    for k in ("image_data","m_ImageData"):
        try:
            v=getattr(d,k,None)
            if v is not None:
                raw=bytes(v)
                if raw: break
        except Exception: pass
    if raw is not None:
        rec["rawBytes"] = len(raw)
    im=getattr(d,"image",None)
    if im is None:
        raise RuntimeError("UnityPy returned no image")
    if not rec.get("width") or not rec.get("height"):
        try: rec["width"],rec["height"] = int(im.width),int(im.height)
        except Exception: pass
    fn=f"{safe(rec.get('name'))}_p{safe(rec.get('pathID'))}_{safe(rec.get('bundle'))}.png"
    fp=IMG/fn
    im.save(fp)
    rec["decoded"]=True
    rec["method"]=method
    rec["src"]="/lab/audie-2d-raw-v20-data/images/"+fn
    return True

source=[dict(r) for r in (M.get("twoD") or []) if audie_record(r) and not r.get("exported")]
print("AUDIE_2D_RAW_V20_START", f"targets={len(source)}", flush=True)

records=[]
wanted_stream_basenames=set()
by_bundle=defaultdict(list)
for r in source:
    bp=Path(str(r.get("bundlePath") or ""))
    rec={
        "name":r.get("name") or "(sans nom)", "type":r.get("type") or "Texture2D",
        "bundle":r.get("bundle") or bp.name, "bundlePath":str(bp),
        "serializedFile":r.get("serializedFile") or "", "pathID":str(r.get("pathID") or ""),
        "width":as_int(r.get("width")), "height":as_int(r.get("height")),
        "surfaceMap":bool(r.get("surfaceMap")), "likelyRendered2D":bool(r.get("likelyRendered2D")),
        "decoded":False, "src":"", "method":"", "textureFormat":"", "streamData":{},
        "resourceCandidates":[], "errors":[], "v14Error":r.get("exportError") or "",
    }
    records.append(rec)
    by_bundle[str(bp)].append(rec)

# Pass 1: inspect each exact object and retry the ordinary decoder.  This also tells us
# which external StreamData files are actually needed.
for bi,(bps,recs) in enumerate(by_bundle.items(),1):
    bp=Path(bps)
    print("V20_INSPECT", f"{bi}/{len(by_bundle)}", bp.name, f"items={len(recs)}", flush=True)
    if not bp.is_file():
        for rec in recs: rec["errors"].append("bundle_absent")
        continue
    try:
        env=UnityPy.load(str(bp))
    except Exception as e:
        for rec in recs: rec["errors"].append(f"load_bundle:{type(e).__name__}:{e}")
        continue
    for rec in recs:
        p=as_int(rec["pathID"])
        o=find_obj(env,p,rec["type"])
        if o is None:
            rec["errors"].append("pathID_not_found")
            continue
        tr=tree(o)
        rec["textureFormat"]=texture_format(tr)
        rec["width"]=rec["width"] or as_int((tr or {}).get("m_Width"))
        rec["height"]=rec["height"] or as_int((tr or {}).get("m_Height"))
        rec["streamData"]=stream_info(tr)
        sp=rec["streamData"].get("path","")
        if sp:
            base=sp.replace("\\","/").rsplit("/",1)[-1]
            if base: wanted_stream_basenames.add(base.lower())
        try:
            save_image(o,rec,"bundle-direct")
        except Exception as e:
            rec["errors"].append(f"direct:{type(e).__name__}:{e}")

# Build a small basename index only for the StreamData companions we actually need.
resource_index=defaultdict(list)
if wanted_stream_basenames:
    roots=[]
    for bps in by_bundle:
        p=Path(bps)
        if p.parent.is_dir(): roots.append(p.parent)
    for extra in (ROOT/"frontend/lab/local_assets", ROOT/"frontend/lab/master-assets-v2"):
        if extra.is_dir(): roots.append(extra)
    seen_roots=set()
    roots2=[]
    for r in roots:
        try: k=str(r.resolve())
        except Exception: k=str(r)
        if k not in seen_roots:
            seen_roots.add(k); roots2.append(r)
    print("V20_RESOURCE_SEARCH", f"names={len(wanted_stream_basenames)}", f"roots={len(roots2)}", flush=True)
    seen_paths=set()
    for root in roots2:
        for dirpath,_,files in os.walk(root):
            for fn in files:
                low=fn.lower()
                if low in wanted_stream_basenames:
                    p=Path(dirpath)/fn
                    k=str(p)
                    if k not in seen_paths:
                        seen_paths.add(k); resource_index[low].append(p)

# Pass 2: reload bundle together with the exact .resS/.resource companion, then decode.
for rec in records:
    if rec["decoded"]: continue
    sd=rec.get("streamData") or {}
    sp=str(sd.get("path") or "")
    base=sp.replace("\\","/").rsplit("/",1)[-1].lower() if sp else ""
    candidates=list(resource_index.get(base,[]))
    rec["resourceCandidates"]=[str(x) for x in candidates[:10]]
    bp=Path(rec["bundlePath"])
    if not bp.is_file() or not candidates: continue
    for rp in candidates[:6]:
        try:
            env=UnityPy.load(str(bp),str(rp))
            o=find_obj(env,as_int(rec["pathID"]),rec["type"])
            if o is None: raise RuntimeError("pathID absent after companion load")
            save_image(o,rec,"bundle+stream-resource")
            break
        except Exception as e:
            rec["errors"].append(f"resource:{rp.name}:{type(e).__name__}:{e}")

# Rank likely final renders ahead of D/N/S maps.
def score(r):
    s=0
    t=" ".join(str(r.get(k) or "") for k in ("name","bundle","serializedFile")).lower()
    if r.get("decoded"): s+=100
    if r.get("likelyRendered2D"): s+=35
    if re.search(r"sprite|preview|icon|formation|team|vehicle|car|tank|hero",t): s+=25
    if r.get("surfaceMap") or re.search(r"(?:^|[_\-.])(high[_\-.]?)?[dns](?:$|[_\-.])|normal|spec|rough|metal", str(r.get("name") or "").lower()): s-=35
    area=as_int(r.get("width"))*as_int(r.get("height"))
    if area>=256*256: s+=5
    if r.get("streamData",{}).get("path"): s+=3
    return s
for r in records: r["score"]=score(r)
records.sort(key=lambda r:(-r["score"],str(r["name"]).lower(),str(r["pathID"])))

decoded=sum(1 for r in records if r["decoded"])
streamed=sum(1 for r in records if (r.get("streamData") or {}).get("path"))
resolved=sum(1 for r in records if r.get("resourceCandidates"))
formats=defaultdict(int)
for r in records: formats[str(r.get("textureFormat") or "UNKNOWN")]+=1
res={
    "format":"WFGG_LASTWAR_AUDIE_2D_RAW_V20",
    "verdict":"AUDIE_2D_DECODED" if decoded else "AUDIE_2D_METADATA_READY_NO_NEW_DECODE",
    "counts":{"targets":len(records),"decoded":decoded,"stillRaw":len(records)-decoded,"streamed":streamed,"resourceResolved":resolved},
    "formats":dict(sorted(formats.items(), key=lambda kv:(-kv[1],kv[0]))),
    "items":records,
    "rules":[
        "Only non-exported Audie 2D assets from V14 are targeted.",
        "V20 inspects m_TextureFormat and m_StreamData before decoding.",
        "When StreamData names a companion resource, V20 searches local assets by exact basename and retries UnityPy with bundle + companion resource.",
        "D/N/S material maps are retained but ranked behind likely final renders.",
    ],
}
MAN.write_text(json.dumps(res,ensure_ascii=False,indent=2)+"\n","utf-8")
print("AUDIE_2D_RAW_V20_READY", f"targets={len(records)}", f"decoded={decoded}", f"stillRaw={len(records)-decoded}", f"streamed={streamed}", f"resourceResolved={resolved}", flush=True)
for r in records[:30]:
    print("V20_TEXTURE", "OK" if r["decoded"] else "RAW", r["name"], f"{r['width']}x{r['height']}", f"fmt={r['textureFormat'] or '?'}", f"stream={bool((r.get('streamData') or {}).get('path'))}", f"score={r['score']}", flush=True)
print("JSON="+str(MAN), flush=True)
print("VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-2d-raw-v20.html?v=20", flush=True)
