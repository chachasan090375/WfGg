#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

from pathlib import Path
from collections import defaultdict
import csv, hashlib, json, os, re, shutil, sys

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "scripts"))
from wfgg_unity_raw_mesh import typ, pid, sfname, pname, safe, raw_mesh_to_obj

import UnityPy
from PIL import Image
from UnityPy.enums import TextureFormat
import texture2ddecoder as t2d

UnityPy.config.FALLBACK_UNITY_VERSION = "2019.4.41f1"
RET = ROOT / "frontend/lab/manual-review-v27/index/retained.json"
TSV = ROOT / "frontend/lab/master-assets-v2/index/lastwar-graphics-asset-path-index-v1.tsv"
OUTROOT = ROOT / "frontend/lab/bundle-reconstruction-data"
MAX_TEXTURES = int(os.environ.get("WFGG_V29_MAX_TEXTURES", "220"))
MAX_MESHES = int(os.environ.get("WFGG_V29_MAX_MESHES", "140"))

if not RET.is_file(): raise SystemExit(f"retained index absent: {RET}")
if not TSV.is_file(): raise SystemExit(f"asset-path index absent: {TSV}")
D = json.loads(RET.read_text("utf-8"))
items = list(D.get("items") or [])
audie_anchor = next((x for x in items if int(x.get("id",0)) == 5115), {})
audie_base = [int(x) for x in (audie_anchor.get("dependencies") or [])]


def as_int(v,d=0):
    try:return int(v)
    except Exception:return d

def tree(o):
    try:return o.read_typetree(wrap=False,check_read=False)
    except TypeError:
        try:return o.read_typetree()
        except Exception:return {}
    except Exception:return {}

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
    return bool(a and b and (a==b or a.endswith("/"+b) or a.split("/")[-1]==b.split("/")[-1]))
def embedded_index(env):
    out=[]
    for name,node in walk_embedded(getattr(env,"file",None)):
        blob=node_bytes(node)
        if blob:out.append((name,blob))
    return out
def stream_info(tr):
    if not isinstance(tr,dict):return {}
    s=tr.get("m_StreamData") or tr.get("streamData") or {}
    if not isinstance(s,dict):return {}
    return {"path":str(s.get("path") or s.get("m_Path") or ""),"offset":as_int(s.get("offset",s.get("m_Offset",0))),"size":as_int(s.get("size",s.get("m_Size",0)))}
def recover_stream(idx,sd):
    sp=str((sd or {}).get("path") or ""); off=max(0,as_int((sd or {}).get("offset"))); sz=max(0,as_int((sd or {}).get("size")))
    if not sp or sz<=0:return b"",""
    for name,blob in idx:
        if matches_resource(name,sp) and off < len(blob):
            raw=blob[off:min(len(blob),off+sz)]
            if raw:return raw,name
    return b"",""
def fmt_name(fmt):
    try:return TextureFormat(int(fmt)).name
    except Exception:return str(fmt)
def bgra(raw,w,h):return Image.frombytes("RGBA",(w,h),raw,"raw","BGRA")
def decode_raw(raw,w,h,name):
    if "Crunched" in name:
        try:raw=t2d.unpack_unity_crunch(raw)
        except Exception:raw=t2d.unpack_crunch(raw)
        name=name.replace("Crunched","")
    if name.startswith("ASTC"):
        m=re.search(r"(\d+)x(\d+)",name)
        if not m:raise ValueError(name)
        im=bgra(t2d.decode_astc(raw,w,h,int(m.group(1)),int(m.group(2))),w,h)
    elif name in ("ETC_RGB4","ETC_RGB4_3DS"):im=bgra(t2d.decode_etc1(raw,w,h),w,h)
    elif name=="ETC2_RGB":im=bgra(t2d.decode_etc2(raw,w,h),w,h)
    elif name=="ETC2_RGBA1":im=bgra(t2d.decode_etc2a1(raw,w,h),w,h)
    elif name=="ETC2_RGBA8":im=bgra(t2d.decode_etc2a8(raw,w,h),w,h)
    elif name=="DXT1":im=bgra(t2d.decode_bc1(raw,w,h),w,h)
    elif name=="DXT5":im=bgra(t2d.decode_bc3(raw,w,h),w,h)
    elif name=="BC4":im=bgra(t2d.decode_bc4(raw,w,h),w,h)
    elif name=="BC5":im=bgra(t2d.decode_bc5(raw,w,h),w,h)
    elif name=="BC7":im=bgra(t2d.decode_bc7(raw,w,h),w,h)
    elif name=="RGBA32":im=Image.frombytes("RGBA",(w,h),raw[:w*h*4],"raw","RGBA")
    elif name=="BGRA32":im=Image.frombytes("RGBA",(w,h),raw[:w*h*4],"raw","BGRA")
    elif name=="ARGB32":im=Image.frombytes("RGBA",(w,h),raw[:w*h*4],"raw","ARGB")
    elif name=="RGB24":im=Image.frombytes("RGB",(w,h),raw[:w*h*3],"raw","RGB").convert("RGBA")
    else:raise ValueError("unsupported "+name)
    return im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

def export_texture(o,env,eidx,outfile):
    tr=tree(o); d=o.read(); name=str((tr or {}).get("m_Name") or getattr(d,"m_Name",None) or pname(o) or f"Texture_{pid(o)}")
    w=as_int((tr or {}).get("m_Width")) or as_int(getattr(d,"m_Width",0)); h=as_int((tr or {}).get("m_Height")) or as_int(getattr(d,"m_Height",0))
    fmt=as_int((tr or {}).get("m_TextureFormat"),as_int(getattr(d,"m_TextureFormat",0))); fn=fmt_name(fmt); resolver=""
    if w<=0 or h<=0:raise ValueError("invalid dimensions")
    try:
        im=d.image
        if im is None:raise ValueError("image none")
        im.save(outfile); resolver="unitypy-image"
    except Exception:
        raw=b""
        try:raw=bytes(d.get_image_data())
        except Exception:pass
        if raw:
            try:decode_raw(raw,w,h,fn).save(outfile);resolver="direct-image-data"
            except Exception:raw=b""
        if not raw or not outfile.is_file():
            raw,res=recover_stream(eidx,stream_info(tr))
            if not raw:raise ValueError("stream payload unresolved")
            decode_raw(raw,w,h,fn).save(outfile);resolver="embedded:"+res
    return {"name":name,"width":w,"height":h,"format":fn,"resolver":resolver}

# Which bundle IDs must be locatable. Direct Timeline candidates deliberately
# include both their manually isolated unique dependencies and the common Audie
# Exhibit dependencies. No vocabulary/keyword filtering is performed here.
def ids_for_item(x):
    root=as_int(x.get("bundleId")); ids=[root]
    if x.get("category")=="direct-candidate": ids += [as_int(v) for v in x.get("uniqueDependencies",[])] + audie_base
    elif as_int(x.get("id"))==5115: ids += audie_base
    return list(dict.fromkeys(v for v in ids if v>=0))
needed=set()
for x in items:needed.update(ids_for_item(x))

catalog=defaultdict(lambda:{"logical":set(),"alias":set(),"assets":[]})
with TSV.open("r",encoding="utf-8",errors="replace",newline="") as f:
    for r in csv.DictReader(f,delimiter="\t"):
        bid=as_int(r.get("bundleId"),-1)
        if bid not in needed:continue
        if r.get("logicalName"):catalog[bid]["logical"].add(r["logicalName"])
        if r.get("aliasName"):catalog[bid]["alias"].add(r["aliasName"])
        if len(catalog[bid]["assets"])<8 and r.get("assetPath"):catalog[bid]["assets"].append(r["assetPath"])
for x in items:
    bid=as_int(x.get("bundleId"),-1)
    if x.get("logicalName"):catalog[bid]["logical"].add(x["logicalName"])
    if x.get("aliasName"):catalog[bid]["alias"].add(x["aliasName"])

expected=defaultdict(set)
for bid in needed:
    expected[f"bundle-{bid}.bundle".lower()].add(bid)
    for n in catalog[bid]["logical"]|catalog[bid]["alias"]:expected[Path(n).name.lower()].add(bid)

roots=[ROOT,Path.home()/".cache",Path.home()/"storage/downloads",Path.home()/"storage/shared/Download",Path("/sdcard/Android/data/com.fun.lastwar.gp"),Path("/storage/emulated/0/Android/data/com.fun.lastwar.gp")]
found=defaultdict(list);seen_paths=set()
print("V29_LOCATOR_START",f"bundleIds={len(needed)}",f"names={len(expected)}",flush=True)
for base in roots:
    if not base.exists():continue
    try:
        walker=os.walk(base)
        for dp,dirs,files in walker:
            dirs[:]=[d for d in dirs if d not in {".git","node_modules","bundle-reconstruction-data","manual-review-v27"}]
            for fn in files:
                ids=expected.get(fn.lower())
                if not ids:continue
                p=str((Path(dp)/fn).resolve())
                if p in seen_paths:continue
                seen_paths.add(p)
                for bid in ids:found[bid].append(Path(p))
    except (PermissionError,OSError):pass
print("V29_LOCATOR_READY",f"resolved={sum(bool(found[x]) for x in needed)}/{len(needed)}",f"files={sum(len(v) for v in found.values())}",flush=True)

def choose_path(bid):
    xs=found.get(bid) or []
    if not xs:return None
    def rk(p):
        n=p.name.lower(); exact=0 if n==f"bundle-{bid}.bundle" else 1
        local=0 if str(ROOT) in str(p) else 1
        return (exact,local,len(str(p)))
    return sorted(xs,key=rk)[0]

def role_for_dep(x,bid):
    if bid==as_int(x.get("bundleId")):return "root"
    if bid in [as_int(v) for v in x.get("uniqueDependencies",[])]:return "candidate-specific-dependency"
    if bid in audie_base:return "audie-exhibit-dependency"
    return "dependency"

summary=[]
for pos,x in enumerate(items,1):
    root_id=as_int(x.get("bundleId")); out=OUTROOT/str(root_id); td=out/"textures"; md=out/"meshes"
    if out.exists():shutil.rmtree(out)
    td.mkdir(parents=True,exist_ok=True);md.mkdir(parents=True,exist_ok=True)
    ids=ids_for_item(x); sources=[]; textures=[];meshes=[];objects=[];errors=[];tex_hash=set();mesh_hash=set()
    print("V29_CANDIDATE",f"{pos}/{len(items)}",f"id={x.get('id')}",f"root={root_id}",x.get("name"),flush=True)
    ordered=[]
    for bid in ids:
        p=choose_path(bid)
        if p:ordered.append((bid,p,role_for_dep(x,bid)))
        else:errors.append({"bundleId":bid,"stage":"locate","error":"physical bundle not found","names":sorted(catalog[bid]["logical"]|catalog[bid]["alias"])[:4]})
    for bi,(bid,p,role) in enumerate(ordered,1):
        if len(textures)>=MAX_TEXTURES and len(meshes)>=MAX_MESHES:break
        try:env=UnityPy.load(str(p)); eidx=embedded_index(env); objs=list(env.objects)
        except Exception as e:
            errors.append({"bundleId":bid,"path":str(p),"stage":"load","error":f"{type(e).__name__}:{e}"});continue
        sources.append({"bundleId":bid,"path":str(p),"basename":p.name,"role":role,"objects":len(objs),"catalogAssets":catalog[bid]["assets"]})
        for o in objs:
            t=typ(o); nm=pname(o)
            if len(objects)<1800:objects.append({"type":t,"name":nm,"pathID":str(pid(o)),"serializedFile":sfname(o),"bundleId":bid,"role":role})
            if t=="Texture2D" and len(textures)<MAX_TEXTURES:
                try:
                    fn=f"b{bid}_p{pid(o)}_{safe(nm or 'texture')}.png"; fp=td/fn
                    info=export_texture(o,env,eidx,fp); digest=hashlib.sha1(fp.read_bytes()).hexdigest()
                    if digest in tex_hash:fp.unlink(missing_ok=True);continue
                    tex_hash.add(digest);textures.append({**info,"bundleId":bid,"pathID":str(pid(o)),"serializedFile":sfname(o),"role":role,"reason":role,"src":f"/lab/bundle-reconstruction-data/{root_id}/textures/{fn}"})
                except Exception as e:
                    if len(errors)<500:errors.append({"bundleId":bid,"type":"Texture2D","name":nm,"pathID":str(pid(o)),"stage":"texture","error":f"{type(e).__name__}:{e}"})
            elif t=="Mesh" and len(meshes)<MAX_MESHES:
                try:
                    text,info=raw_mesh_to_obj(o); digest=hashlib.sha1(text.encode("utf-8")).hexdigest()
                    if digest in mesh_hash:continue
                    mesh_hash.add(digest);fn=f"b{bid}_p{pid(o)}_{safe(info['name'])}_{digest[:10]}.obj";(md/fn).write_text(text,"utf-8",newline="")
                    meshes.append({"name":info["name"],"bundleId":bid,"pathID":str(pid(o)),"serializedFile":sfname(o),"role":role,"reason":role,"vertexCount":info["vertexCount"],"faceCount":info["faceCount"],"src":f"/lab/bundle-reconstruction-data/{root_id}/meshes/{fn}"})
                except Exception as e:
                    if len(errors)<500:errors.append({"bundleId":bid,"type":"Mesh","name":nm,"pathID":str(pid(o)),"stage":"mesh","error":f"{type(e).__name__}:{e}"})
    # Preserve deterministic order: root first, then candidate-specific, then Audie base.
    rr={"root":0,"candidate-specific-dependency":1,"audie-exhibit-dependency":2,"dependency":3}
    textures.sort(key=lambda z:(rr.get(z.get("role"),9),0 if re.search(r"murphy|audie",z.get("name",''),re.I) else 1,z.get("name",'').lower()))
    meshes.sort(key=lambda z:(rr.get(z.get("role"),9),0 if re.search(r"murphy|audie",z.get("name",''),re.I) else 1,z.get("vertexCount",0),z.get("name",'').lower()))
    manifest={
      "format":"WFGG_LASTWAR_MURPHY_VISUAL_REVIEW_DATA_V29","candidate":x,
      "bundle":{"bundleId":root_id,"assetBundleName":x.get("logicalName") or x.get("name")},
      "counts":{"objects":len(objects),"materials":0,"texturesExported":len(textures),"meshesExported":len(meshes),"renderers":0,"reconstructableRenderers":0,"types":{}},
      "sourceBundles":sources,"textures":textures,"meshes":meshes,"materials":[],"scene":[],"objects":objects,
      "diagnostics":{"requestedBundleIds":ids,"foundBundleIds":[z[0] for z in ordered],"missingBundleIds":[z for z in ids if not choose_path(z)],"errors":errors},
      "rules":["Visual data is exported only from the manually retained Murphy/Audie candidates and their structural dependencies.","Direct Timeline candidates include candidate-specific dependencies plus the Audie Exhibit dependency set.","No generic vehicle keyword filter is used to decide which dependency assets are exported."],
    }
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n","utf-8")
    summary.append({"id":x.get("id"),"bundleId":root_id,"name":x.get("name"),"requested":len(ids),"found":len(ordered),"textures":len(textures),"meshes":len(meshes),"missing":manifest["diagnostics"]["missingBundleIds"]})
    print("V29_READY",f"root={root_id}",f"bundles={len(ordered)}/{len(ids)}",f"textures={len(textures)}",f"meshes={len(meshes)}",f"missing={len(manifest['diagnostics']['missingBundleIds'])}",flush=True)

meta=ROOT/"frontend/lab/manual-review-v27/index/visual-build-v29.json"
meta.write_text(json.dumps({"version":29,"summary":summary},ensure_ascii=False,indent=2)+"\n","utf-8")
print("V29_VISUAL_BUILD_COMPLETE",f"candidates={len(summary)}",f"withVisuals={sum(bool(x['textures'] or x['meshes']) for x in summary)}",flush=True)
for x in summary:print("V29_RESULT",x["id"],f"b{x['bundleId']}",f"tex={x['textures']}",f"mesh={x['meshes']}",f"found={x['found']}/{x['requested']}",flush=True)
print("VIEWER=http://127.0.0.1:8788/lab/lastwar-murphy-visual-review-v29.html?v=29",flush=True)
