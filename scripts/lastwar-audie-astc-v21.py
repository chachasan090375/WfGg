#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

from pathlib import Path
from collections import Counter
import json, re, sys, traceback

import UnityPy
from PIL import Image

ROOT = Path(sys.argv[1]).resolve()
V20 = ROOT / "frontend/lab/audie-2d-raw-v20-data/manifest.json"
V14 = ROOT / "frontend/lab/audie-assembly-2d-v14-data/manifest.json"
OUT = ROOT / "frontend/lab/audie-astc-v21-data"
IMG = OUT / "images"
RAW = OUT / "raw"
MAN = OUT / "manifest.json"
OUT.mkdir(parents=True, exist_ok=True)
IMG.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)
UnityPy.config.FALLBACK_UNITY_VERSION = "2019.4.41f1"

try:
    import texture2ddecoder
    DECODER_IMPORT = "OK"
except Exception as e:
    texture2ddecoder = None
    DECODER_IMPORT = f"{type(e).__name__}:{e}"

ASTC = {
    48: (4, 4, "ASTC_4x4"),
    49: (5, 5, "ASTC_5x5"),
    50: (6, 6, "ASTC_6x6"),
    51: (8, 8, "ASTC_8x8"),
    52: (10, 10, "ASTC_10x10"),
    53: (12, 12, "ASTC_12x12"),
}

def safe(s):
    z = re.sub(r"[^A-Za-z0-9._-]+", "_", str(s or "")).strip("._")
    return z[:100] or "asset"

def typ(o):
    return str(getattr(getattr(o, "type", None), "name", "") or "")

def pid(o):
    return int(getattr(o, "path_id", 0) or 0)

def as_int(v, d=0):
    try: return int(v)
    except Exception: return d

def tree(o):
    try:
        return o.read_typetree(wrap=False, check_read=False)
    except TypeError:
        try: return o.read_typetree()
        except Exception: return {}
    except Exception:
        return {}

def find_obj(env, path_id, wanted="Texture2D"):
    fallback = None
    for o in env.objects:
        if pid(o) != path_id:
            continue
        if typ(o) == wanted:
            return o
        fallback = fallback or o
    return fallback

def fmt_num(v):
    if isinstance(v, int): return v
    try: return int(v)
    except Exception: pass
    s = str(v or "")
    m = re.search(r"(-?\d+)", s)
    if m: return int(m.group(1))
    names = {name:n for n,(_,_,name) in ASTC.items()}
    for name,n in names.items():
        if name.lower() in s.lower(): return n
    return 0

def get_fmt(tr, d):
    vals=[]
    if isinstance(tr, dict):
        vals += [tr.get("m_TextureFormat"), tr.get("textureFormat"), tr.get("format")]
    for k in ("m_TextureFormat", "texture_format"):
        try: vals.append(getattr(d,k,None))
        except Exception: pass
    for v in vals:
        if v is None: continue
        n = getattr(v, "value", None)
        if n is not None:
            try: return int(n)
            except Exception: pass
        n = getattr(v, "name", None)
        if n:
            for k,(_,_,nm) in ASTC.items():
                if str(nm).lower() == str(n).lower(): return k
        z = fmt_num(v)
        if z: return z
    return 0

def stream_info(tr):
    if not isinstance(tr,dict): return {}
    s=tr.get("m_StreamData") or tr.get("streamData") or {}
    if not isinstance(s,dict): return {}
    return {
        "path": str(s.get("path") or s.get("m_Path") or ""),
        "offset": as_int(s.get("offset",s.get("m_Offset",0))),
        "size": as_int(s.get("size",s.get("m_Size",0))),
    }

def get_raw(d):
    errors=[]
    # UnityPy's image_data accessor is the best route because it already knows
    # about StreamData and resources registered in the Environment.
    for attr in ("image_data", "m_ImageData"):
        try:
            v=getattr(d,attr,None)
            if v is None: continue
            b=bytes(v)
            if b: return b, attr, errors
        except Exception as e:
            errors.append(f"{attr}:{type(e).__name__}:{e}")
    return b"", "", errors

def astc_file(raw, w, h, bw, bh, path):
    # ASTC file header: magic 13 ABA1 5C, block x/y/z, 24-bit dimensions.
    hdr=bytearray([0x13,0xAB,0xA1,0x5C,bw,bh,1])
    for n in (w,h,1):
        hdr += bytes((n & 255, (n>>8)&255, (n>>16)&255))
    path.write_bytes(bytes(hdr)+raw)

def decode_explicit(raw, w, h, fmt, out_png):
    if texture2ddecoder is None:
        raise RuntimeError("texture2ddecoder unavailable: "+DECODER_IMPORT)
    if fmt not in ASTC:
        raise RuntimeError(f"format {fmt} is not ASTC 48..53")
    bw,bh,_=ASTC[fmt]
    rgba=texture2ddecoder.decode_astc(raw,w,h,bw,bh)
    # texture2ddecoder returns BGRA according to its API.
    im=Image.frombytes("RGBA",(w,h),rgba,"raw","BGRA")
    # Unity texture coordinate origin is commonly bottom-left; do not flip here.
    # Viewer exposes the actual result so we preserve decoder output faithfully.
    im.save(out_png)

src_path = V20 if V20.is_file() else V14
if not src_path.is_file():
    raise SystemExit("ERROR: V20/V14 manifest absent")
M=json.loads(src_path.read_text("utf-8"))
if src_path == V20:
    source=[dict(x) for x in M.get("items",[]) if not x.get("decoded")]
else:
    source=[dict(x) for x in M.get("twoD",[]) if "audie" in " ".join(str(x.get(k) or "") for k in ("name","bundle","serializedFile")).lower() and not x.get("exported")]

print("AUDIE_ASTC_V21_START", f"targets={len(source)}", f"decoder={DECODER_IMPORT}", flush=True)
items=[]
for i,r in enumerate(source,1):
    bp=Path(str(r.get("bundlePath") or ""))
    rec={
        "name":r.get("name") or "(sans nom)",
        "bundle":r.get("bundle") or bp.name,
        "bundlePath":str(bp),
        "serializedFile":r.get("serializedFile") or "",
        "pathID":str(r.get("pathID") or ""),
        "width":as_int(r.get("width")), "height":as_int(r.get("height")),
        "textureFormat":fmt_num(r.get("textureFormat")),
        "formatName":"", "streamData":r.get("streamData") or {},
        "rawBytes":0,"rawMethod":"","rawSrc":"","astcSrc":"","src":"",
        "decoded":False,"decoder":"","errors":[],
        "likelyRendered2D":bool(r.get("likelyRendered2D")),
        "surfaceMap":bool(r.get("surfaceMap")),
    }
    print("V21_TARGET",f"{i}/{len(source)}",rec["name"],rec["bundle"],f"p={rec['pathID']}",flush=True)
    if not bp.is_file():
        rec["errors"].append("bundle_absent")
        items.append(rec); continue
    try:
        env=UnityPy.load(str(bp))
        o=find_obj(env,as_int(rec["pathID"]),"Texture2D")
        if o is None: raise RuntimeError("pathID_not_found")
        tr=tree(o)
        d=o.read()
        rec["width"] = rec["width"] or as_int((tr or {}).get("m_Width")) or as_int(getattr(d,"m_Width",0))
        rec["height"] = rec["height"] or as_int((tr or {}).get("m_Height")) or as_int(getattr(d,"m_Height",0))
        rec["textureFormat"] = rec["textureFormat"] or get_fmt(tr,d)
        rec["streamData"] = rec["streamData"] or stream_info(tr)
        if rec["textureFormat"] in ASTC:
            rec["formatName"] = ASTC[rec["textureFormat"]][2]
        else:
            rec["formatName"] = str(rec["textureFormat"] or "UNKNOWN")
        raw,method,errs=get_raw(d)
        rec["errors"].extend(errs)
        if raw:
            rec["rawBytes"]=len(raw); rec["rawMethod"]=method
            raw_name=f"{safe(rec['name'])}_p{safe(rec['pathID'])}_{safe(rec['bundle'])}.bin"
            raw_path=RAW/raw_name; raw_path.write_bytes(raw)
            rec["rawSrc"]="/lab/audie-astc-v21-data/raw/"+raw_name
            if rec["textureFormat"] in ASTC and rec["width"] and rec["height"]:
                bw,bh,_=ASTC[rec["textureFormat"]]
                astc_name=raw_name[:-4]+".astc"
                astc_path=RAW/astc_name
                astc_file(raw,rec["width"],rec["height"],bw,bh,astc_path)
                rec["astcSrc"]="/lab/audie-astc-v21-data/raw/"+astc_name
                png_name=raw_name[:-4]+".png"
                png_path=IMG/png_name
                try:
                    decode_explicit(raw,rec["width"],rec["height"],rec["textureFormat"],png_path)
                    rec["decoded"]=True; rec["decoder"]="texture2ddecoder.decode_astc"
                    rec["src"]="/lab/audie-astc-v21-data/images/"+png_name
                except Exception as e:
                    rec["errors"].append(f"astc_decode:{type(e).__name__}:{e}")
        else:
            rec["errors"].append("raw_payload_unavailable")
    except Exception as e:
        rec["errors"].append(f"object:{type(e).__name__}:{e}")
    items.append(rec)

# Ranking: decoded final-looking assets first; maps last.
def score(r):
    s=100 if r.get("decoded") else 0
    t=(str(r.get("name") or "")+" "+str(r.get("bundle") or "")).lower()
    if r.get("likelyRendered2D"): s+=35
    if re.search(r"hero_icon|sprite|preview|icon|formation|team|vehicle|car|tank",t): s+=30
    if r.get("surfaceMap") or re.search(r"(?:^|[_\-.])(high[_\-.]?)?[dns](?:$|[_\-.])|normal|spec|rough|metal",str(r.get("name") or "").lower()): s-=35
    if r.get("rawBytes"): s+=10
    return s
for r in items: r["score"]=score(r)
items.sort(key=lambda r:(-r["score"],str(r["name"]).lower(),str(r["pathID"])))

counts=Counter()
for r in items:
    counts["decoded"] += bool(r["decoded"])
    counts["rawAvailable"] += bool(r["rawBytes"])
    counts["rawMissing"] += not bool(r["rawBytes"])
    counts["astc"] += r["textureFormat"] in ASTC
    counts["streamed"] += bool((r.get("streamData") or {}).get("path"))
formats=Counter(r.get("formatName") or "UNKNOWN" for r in items)
res={
    "format":"WFGG_LASTWAR_AUDIE_ASTC_V21",
    "verdict":"ASTC_IMAGES_DECODED" if counts["decoded"] else ("RAW_ASTC_RECOVERED_DECODER_BLOCKED" if counts["rawAvailable"] else "STREAM_PAYLOAD_STILL_UNRESOLVED"),
    "decoderImport":DECODER_IMPORT,
    "counts":{"targets":len(items),**dict(counts)},
    "formats":dict(formats),
    "items":items,
    "rules":[
        "Formats 48..53 are treated explicitly as ASTC 4x4..12x12.",
        "V21 first asks UnityPy only for raw image_data; PNG conversion is then performed explicitly through texture2ddecoder.decode_astc.",
        "A .astc file with a valid 16-byte ASTC header is emitted whenever raw ASTC bytes are recovered, even if the Python decoder is unavailable.",
        "If rawAvailable is zero, the remaining blocker is StreamData/container resolution rather than ASTC decompression.",
    ]
}
MAN.write_text(json.dumps(res,ensure_ascii=False,indent=2)+"\n","utf-8")
print("AUDIE_ASTC_V21_READY",f"verdict={res['verdict']}",f"decoded={counts['decoded']}",f"rawAvailable={counts['rawAvailable']}",f"rawMissing={counts['rawMissing']}",f"decoder={DECODER_IMPORT}",flush=True)
for r in items[:30]:
    print("V21_TEXTURE","PNG" if r["decoded"] else ("RAW" if r["rawBytes"] else "MISS"),r["name"],f"{r['width']}x{r['height']}",r["formatName"],f"bytes={r['rawBytes']}",f"stream={str((r.get('streamData') or {}).get('path') or '-')[:80]}",flush=True)
print("JSON="+str(MAN),flush=True)
print("VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-astc-v21.html?v=21",flush=True)
