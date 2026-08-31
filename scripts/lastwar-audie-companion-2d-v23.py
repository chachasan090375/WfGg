#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

from pathlib import Path
from collections import Counter
import json, re, sys

import UnityPy
from PIL import Image

ROOT = Path(sys.argv[1]).resolve()
V22 = ROOT / "frontend/lab/audie-stream-v22-data/manifest.json"
OUT = ROOT / "frontend/lab/audie-companion-v23-data"
IMG = OUT / "images"
MAN = OUT / "manifest.json"
OUT.mkdir(parents=True, exist_ok=True)
IMG.mkdir(parents=True, exist_ok=True)
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

KEY_VEHICLE = re.compile(r"car|tank|vehicle|veh|auto|truck|jeep|formation|team|battle|pvp|hero|chariot|combat", re.I)
KEY_PORTRAIT = re.compile(r"hero_icon|portrait|avatar|head|face|profile|role_icon|character_icon", re.I)
KEY_SURFACE = re.compile(r"(?:^|[_\-.])(high[_\-.]?)?[dns](?:$|[_\-.])|normal|spec|rough|metal|metallic|ao|occlusion|mask|bump", re.I)


def safe(s):
    z = re.sub(r"[^A-Za-z0-9._-]+", "_", str(s or "")).strip("._")
    return z[:110] or "asset"

def as_int(v,d=0):
    try:return int(v)
    except Exception:return d

def typ(o):
    return str(getattr(getattr(o,"type",None),"name","") or "")
def pid(o):
    return int(getattr(o,"path_id",0) or 0)
def tree(o):
    try:return o.read_typetree(wrap=False,check_read=False)
    except TypeError:
        try:return o.read_typetree()
        except Exception:return {}
    except Exception:return {}

def fmt_num(v):
    if isinstance(v,int): return v
    try:return int(v)
    except Exception: pass
    s=str(v or "")
    m=re.search(r"(-?\d+)",s)
    if m:return int(m.group(1))
    for k,(_,_,nm) in ASTC.items():
        if nm.lower() in s.lower():return k
    return 0

def get_fmt(tr,d):
    vals=[]
    if isinstance(tr,dict): vals += [tr.get("m_TextureFormat"),tr.get("textureFormat"),tr.get("format")]
    vals += [getattr(d,"m_TextureFormat",None),getattr(d,"texture_format",None)]
    for v in vals:
        if v is None:continue
        n=getattr(v,"value",None)
        if n is not None:
            try:return int(n)
            except Exception:pass
        n=getattr(v,"name",None)
        if n:
            for k,(_,_,nm) in ASTC.items():
                if nm.lower()==str(n).lower():return k
        q=fmt_num(v)
        if q:return q
    return 0

def stream_info(tr):
    if not isinstance(tr,dict):return {}
    s=tr.get("m_StreamData") or tr.get("streamData") or {}
    if not isinstance(s,dict):return {}
    return {
      "path":str(s.get("path") or s.get("m_Path") or ""),
      "offset":as_int(s.get("offset",s.get("m_Offset",0))),
      "size":as_int(s.get("size",s.get("m_Size",0))),
    }

def stream_basename(p):
    p=str(p or "").replace("\\","/")
    if p.lower().startswith("archive:/"):p=p[9:]
    return p.rstrip("/").split("/")[-1]

def node_bytes(node):
    for cand in (node,getattr(node,"reader",None)):
        try:
            b=getattr(cand,"bytes",None)
            if b is not None:
                z=bytes(b)
                if z:return z
        except Exception:pass
    return b""

def walk_embedded(node,prefix="",seen=None,depth=0):
    if seen is None:seen=set()
    if node is None or depth>8 or id(node) in seen:return
    seen.add(id(node))
    try:children=getattr(node,"files",None)
    except Exception:children=None
    if not isinstance(children,dict):return
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

def expected_astc(w,h,fmt):
    if fmt not in ASTC or w<=0 or h<=0:return 0
    bw,bh,_=ASTC[fmt]
    return ((w+bw-1)//bw)*((h+bh-1)//bh)*16

def decode_astc(raw,w,h,fmt,out_png):
    if texture2ddecoder is None:raise RuntimeError("texture2ddecoder unavailable: "+DECODER)
    bw,bh,_=ASTC[fmt]
    rgba=texture2ddecoder.decode_astc(raw,w,h,bw,bh)
    Image.frombytes("RGBA",(w,h),rgba,"raw","BGRA").save(out_png)

def embedded_index(env):
    idx=[]
    root=getattr(env,"file",None)
    for name,node in walk_embedded(root):
        blob=node_bytes(node)
        if blob: idx.append((name,node,blob))
    return idx

def recover_stream(idx,sp,off,size,expected):
    if not sp:return b"",""
    for name,node,blob in idx:
        if not matches_resource(name,sp):continue
        off=max(0,as_int(off)); sz=max(0,as_int(size)) or expected
        if off>=len(blob) or sz<=0:continue
        raw=blob[off:min(len(blob),off+sz)]
        if expected and len(raw)>=expected:raw=raw[:expected]
        if raw:return raw,name
    return b"",""

def asset_name(tr,d):
    for v in ((tr or {}).get("m_Name") if isinstance(tr,dict) else None,getattr(d,"m_Name",None),getattr(d,"name",None)):
        if v:return str(v)
    return "(sans nom)"

def serialized_name(o):
    af=getattr(o,"assets_file",None)
    return str(getattr(af,"name","") or "")

def portrait_like(name,w,h):
    if KEY_PORTRAIT.search(name):return True
    # Portrait/icon sheets are often near-square but this is only a soft clue.
    return False

def surface_like(name):
    return bool(KEY_SURFACE.search(name))

def rank(rec):
    name=rec["name"]
    s=0
    if rec["decoded"]:s+=120
    if rec["vehicleKeyword"]:s+=90
    if not rec["portraitLike"]:s+=30
    if not rec["surfaceMap"]:s+=35
    if 96 <= rec["width"] <= 2048 and 96 <= rec["height"] <= 2048:s+=15
    if rec["width"]*rec["height"] >= 256*256:s+=10
    if rec["audieInName"]:s+=5
    if rec["portraitLike"]:s-=80
    if rec["surfaceMap"]:s-=70
    return s

if not V22.is_file():raise SystemExit("ERROR: V22 manifest absent")
M=json.loads(V22.read_text("utf-8"))
source=[x for x in M.get("items",[]) if x.get("decodedV22") or x.get("resolver")=="embedded_unityfs"]
carrier_paths=[]
for x in source:
    p=str(x.get("bundlePath") or "")
    if p and p not in carrier_paths:carrier_paths.append(p)

print("AUDIE_COMPANION_2D_V23_START",f"carrierBundles={len(carrier_paths)}",f"v22Decoded={sum(bool(x.get('decodedV22')) for x in source)}",flush=True)

items=[]
seen=set()
for bi,bps in enumerate(carrier_paths,1):
    bp=Path(bps)
    print("V23_BUNDLE",f"{bi}/{len(carrier_paths)}",bp.name,flush=True)
    if not bp.is_file():continue
    try:
        env=UnityPy.load(str(bp))
        eidx=embedded_index(env)
    except Exception as e:
        print("V23_BUNDLE_FAIL",bp.name,type(e).__name__,e,flush=True);continue
    for o in env.objects:
        if typ(o)!="Texture2D":continue
        key=(str(bp),pid(o))
        if key in seen:continue
        seen.add(key)
        rec={"bundle":bp.name,"bundlePath":str(bp),"pathID":str(pid(o)),"serializedFile":serialized_name(o),"name":"(sans nom)","width":0,"height":0,"textureFormat":0,"formatName":"","streamData":{},"resolver":"","resolvedResource":"","decoded":False,"src":"","errors":[]}
        try:
            tr=tree(o); d=o.read()
            rec["name"]=asset_name(tr,d)
            rec["width"]=as_int((tr or {}).get("m_Width")) or as_int(getattr(d,"m_Width",0))
            rec["height"]=as_int((tr or {}).get("m_Height")) or as_int(getattr(d,"m_Height",0))
            rec["textureFormat"]=get_fmt(tr,d)
            rec["formatName"]=ASTC.get(rec["textureFormat"],(0,0,str(rec["textureFormat"] or "UNKNOWN")))[2]
            rec["streamData"]=stream_info(tr)
            # Ignore microscopic utility textures in the visual gallery.
            if rec["width"]<32 or rec["height"]<32:continue
            png_name=f"{safe(rec['name'])}_p{rec['pathID']}_{safe(bp.name)}.png"
            png_path=IMG/png_name
            # 1) Let UnityPy handle embedded/non-streamed formats where it can.
            try:
                im=d.image
                if im is not None:
                    im.save(png_path)
                    rec["decoded"]=True;rec["resolver"]="unitypy_image";rec["src"]="/lab/audie-companion-v23-data/images/"+png_name
            except Exception as e:
                rec["errors"].append(f"unitypy:{type(e).__name__}:{e}")
            # 2) Explicit ASTC path for stream data inside the same UnityFS.
            if not rec["decoded"] and rec["textureFormat"] in ASTC:
                sd=rec["streamData"]; sp=str(sd.get("path") or "")
                expected=expected_astc(rec["width"],rec["height"],rec["textureFormat"])
                raw,resname=recover_stream(eidx,sp,sd.get("offset",0),sd.get("size",0),expected)
                if raw:
                    rec["resolver"]="embedded_unityfs";rec["resolvedResource"]=resname
                    try:
                        decode_astc(raw,rec["width"],rec["height"],rec["textureFormat"],png_path)
                        rec["decoded"]=True;rec["src"]="/lab/audie-companion-v23-data/images/"+png_name
                    except Exception as e:
                        rec["errors"].append(f"astc:{type(e).__name__}:{e}")
            nm=rec["name"]
            rec["audieInName"]=bool(re.search(r"audie|murphy",nm,re.I))
            rec["vehicleKeyword"]=bool(KEY_VEHICLE.search(nm))
            rec["portraitLike"]=portrait_like(nm,rec["width"],rec["height"])
            rec["surfaceMap"]=surface_like(nm)
            rec["likelyVehicleRender"]=bool(rec["decoded"] and not rec["portraitLike"] and not rec["surfaceMap"])
            rec["score"]=rank(rec)
            items.append(rec)
        except Exception as e:
            rec["errors"].append(f"object:{type(e).__name__}:{e}")
            rec["audieInName"]=False;rec["vehicleKeyword"]=False;rec["portraitLike"]=False;rec["surfaceMap"]=False;rec["likelyVehicleRender"]=False;rec["score"]=-999
            items.append(rec)

items.sort(key=lambda x:(-x.get("score",0),str(x.get("name") or "").lower(),x.get("bundle",""),as_int(x.get("pathID"))))
c=Counter()
for x in items:
    c["textures"]+=1
    c["decoded"]+=bool(x.get("decoded"))
    c["probable"]+=bool(x.get("likelyVehicleRender"))
    c["vehicleKeyword"]+=bool(x.get("vehicleKeyword"))
    c["portrait"]+=bool(x.get("portraitLike"))
    c["surfaceMap"]+=bool(x.get("surfaceMap"))
    c["audieNamed"]+=bool(x.get("audieInName"))

res={
  "format":"WFGG_LASTWAR_AUDIE_COMPANION_2D_V23",
  "verdict":"COMPANION_TEXTURES_READY" if c["decoded"] else "NO_COMPANION_TEXTURE_DECODED",
  "counts":{"carrierBundles":len(carrier_paths),**dict(c)},
  "carrierBundles":[Path(x).name for x in carrier_paths],
  "items":items,
  "rules":[
    "V23 does not require Audie/Murphy in the texture name.",
    "Only bundles that already yielded confirmed Murphy/Audie textures in V22 are scanned.",
    "Portrait/icon textures and D/N/S/normal/specular material maps are demoted, not deleted.",
    "The Probables tab keeps decoded textures that are neither portrait-like nor material maps, including generic names.",
  ]
}
MAN.write_text(json.dumps(res,ensure_ascii=False,indent=2)+"\n","utf-8")
print("AUDIE_COMPANION_2D_V23_READY",f"bundles={len(carrier_paths)}",f"textures={c['textures']}",f"decoded={c['decoded']}",f"probable={c['probable']}",f"vehicleKeyword={c['vehicleKeyword']}",flush=True)
for x in items[:40]:
    print("V23_TEXTURE",x.get("score"),x.get("name"),f"{x.get('width')}x{x.get('height')}",x.get("formatName"),"PNG" if x.get("decoded") else "MISS",x.get("bundle"),flush=True)
print("JSON="+str(MAN),flush=True)
print("VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-companion-2d-v23.html?v=23",flush=True)
