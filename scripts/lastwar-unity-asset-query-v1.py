#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

from pathlib import Path
import json
import re
import sys

ROOT = Path(sys.argv[1]).resolve()
QUERY = (sys.argv[2] if len(sys.argv) > 2 else "").strip()
if not QUERY:
    raise SystemExit('Usage: lastwar-unity-asset-query-v1.py ROOT "asset name"')
INDEX = ROOT / "frontend/lab/master-assets-v2/meta/unity-asset-name-index-v1.json"
if not INDEX.is_file():
    raise SystemExit("ERREUR: index absent; lance lastwar-unity-asset-index-v1.py")

sys.path.insert(0, str(ROOT / "scripts"))
from wfgg_unity_raw_mesh import typ, pid, sfname, pname, safe, raw_mesh_to_obj

import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION = "2019.4.41f1"


def compact(s): return re.sub(r"[^a-z0-9]+", "", str(s).lower())
needle = compact(QUERY)
idx = json.loads(INDEX.read_text("utf-8"))
hits = []
for b in idx.get("bundles", []) or []:
    score = 0; matched = []
    if needle in compact(b.get("basename", "")):
        score += 100; matched.append({"type":"bundle","name":b.get("basename")})
    for n in b.get("names", []) or []:
        if needle in compact(n.get("name", "")):
            score += 20 if n.get("type") == "Mesh" else 8
            matched.append(n)
    if score:
        hits.append({"score":score,"path":b.get("path"),"basename":b.get("basename"),"matched":matched[:100],"counts":b.get("counts") or {}})
hits.sort(key=lambda r:(-r["score"],r["basename"] or ""))

slug = safe(QUERY).lower()
out = ROOT / "frontend/lab/unity-asset-query-data" / slug
meshdir = out / "meshes"
meshdir.mkdir(parents=True, exist_ok=True)
for p in meshdir.glob("*.obj"):
    try:p.unlink()
    except Exception:pass
meshes=[];errors=[]
for hi,h in enumerate(hits,1):
    p=Path(str(h.get("path") or ""))
    if not p.is_file(): continue
    print("UNITY_ASSET_QUERY_V1_BUNDLE",f"{hi}/{len(hits)}",h["score"],p.name,flush=True)
    try: env=UnityPy.load(str(p))
    except Exception as e:
        errors.append({"bundle":p.name,"stage":"load","error":f"{type(e).__name__}:{e}"});continue
    for o in env.objects:
        if typ(o)!="Mesh": continue
        # Export every Mesh from a matched bundle: prefab names and mesh names often differ.
        try:
            text,info=raw_mesh_to_obj(o)
            fn=f"{safe(p.stem)}_p{pid(o)}_{safe(info['name'])}.obj"
            fp=meshdir/fn;fp.write_text(text,"utf-8",newline="")
            meshes.append({"bundle":p.name,"bundlePath":str(p),"pathID":str(pid(o)),"serializedFile":sfname(o),"name":info["name"],"src":f"/lab/unity-asset-query-data/{slug}/meshes/{fn}","vertexCount":info["vertexCount"],"faceCount":info["faceCount"],"hasUV0":info["hasUV0"],"queryBundleScore":h["score"]})
            print("UNITY_ASSET_QUERY_V1_MESH",info["name"],f"v={info['vertexCount']}",f"f={info['faceCount']}",flush=True)
        except Exception as e:
            errors.append({"bundle":p.name,"pathID":str(pid(o)),"name":pname(o),"stage":"raw-mesh","error":f"{type(e).__name__}:{e}"})
meshes.sort(key=lambda r:(r["vertexCount"],r["faceCount"],r["name"].lower()))
res={"format":"WFGG_UNITY_ASSET_QUERY_V1","method":"INDEX_NAME_HIT_TO_RAW_TYPETREE_OBJ","query":QUERY,"slug":slug,"counts":{"bundleHits":len(hits),"meshes":len(meshes)},"bundleHits":hits,"meshes":meshes,"errors":errors[:500]}
out.mkdir(parents=True,exist_ok=True)
(out/"manifest.json").write_text(json.dumps(res,ensure_ascii=False,indent=2)+"\n","utf-8")
print("UNITY_ASSET_QUERY_V1_READY",f"query={QUERY}",f"bundleHits={len(hits)}",f"meshes={len(meshes)}",flush=True)
print("JSON="+str(out/"manifest.json"),flush=True)
