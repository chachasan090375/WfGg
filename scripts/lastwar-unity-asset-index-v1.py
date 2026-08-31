#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

from pathlib import Path
from collections import Counter
import json
import sys
import time

ROOT = Path(sys.argv[1]).resolve()
OUT = ROOT / "frontend/lab/master-assets-v2/meta/unity-asset-name-index-v1.json"

import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION = "2019.4.41f1"

KEEP = {"AssetBundle","GameObject","Mesh","MeshFilter","MeshRenderer","SkinnedMeshRenderer","Material","Texture2D","Sprite","AnimationClip","Animator","AnimatorController","Avatar","MonoBehaviour","Shader"}


def typ(o): return str(getattr(getattr(o, "type", None), "name", "") or "")
def pid(o): return str(getattr(o, "path_id", 0) or 0)
def sfname(o):
    af = getattr(o, "assets_file", None)
    return str(getattr(af, "name", "") or getattr(af, "file_name", "") or "")
def pname(o):
    try: return str(o.peek_name() or "")
    except Exception: return ""

old = {}
if OUT.is_file():
    try: old = json.loads(OUT.read_text("utf-8"))
    except Exception: old = {}
old_by_path = {r.get("path"): r for r in old.get("bundles", []) or [] if r.get("path")}

paths = []
seen = set()
for base in (ROOT / "frontend/lab/local_assets", Path.home() / ".cache"):
    if not base.exists(): continue
    for p in base.rglob("*.bundle"):
        try: k = str(p.resolve())
        except Exception: k = str(p)
        if k in seen: continue
        seen.add(k); paths.append(p)
paths.sort(key=lambda p: p.name.lower())

print("UNITY_ASSET_NAME_INDEX_V1_START", f"bundles={len(paths)}", flush=True)
rows = []; errors = []; reused = 0; rescanned = 0
for i, p in enumerate(paths, 1):
    try:
        st = p.stat(); size = int(st.st_size); mtime = int(st.st_mtime)
    except Exception:
        size = 0; mtime = 0
    key = str(p.resolve())
    prev = old_by_path.get(key)
    if prev and int(prev.get("size", -1)) == size and int(prev.get("mtime", -1)) == mtime:
        rows.append(prev); reused += 1
        if i % 100 == 0: print("UNITY_ASSET_NAME_INDEX_V1_PROGRESS", f"{i}/{len(paths)}", f"reused={reused}", f"rescanned={rescanned}", flush=True)
        continue
    rescanned += 1
    try:
        env = UnityPy.load(str(p)); objs = list(env.objects)
        counts = Counter(typ(o) for o in objs)
        names = []
        for o in objs:
            t = typ(o)
            if t not in KEEP: continue
            n = pname(o)
            if not n: continue
            names.append({"type": t, "name": n, "pathID": pid(o), "serializedFile": sfname(o)})
        rows.append({"path": key, "basename": p.name, "size": size, "mtime": mtime, "objectCount": len(objs), "counts": dict(counts), "names": names})
    except Exception as e:
        errors.append({"path": key, "basename": p.name, "error": f"{type(e).__name__}:{e}"})
    if i % 50 == 0: print("UNITY_ASSET_NAME_INDEX_V1_PROGRESS", f"{i}/{len(paths)}", f"reused={reused}", f"rescanned={rescanned}", flush=True)

res = {"format":"WFGG_UNITY_ASSET_NAME_INDEX_V1","generatedAt":int(time.time()),"bundleCount":len(rows),"reused":reused,"rescanned":rescanned,"bundles":rows,"errors":errors[:500]}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8")
print("UNITY_ASSET_NAME_INDEX_V1_READY", f"bundles={len(rows)}", f"reused={reused}", f"rescanned={rescanned}", f"errors={len(errors)}", flush=True)
print("JSON=" + str(OUT), flush=True)
