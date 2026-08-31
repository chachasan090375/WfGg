#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

from pathlib import Path
from collections import defaultdict, Counter
import json
import re
import sys

import UnityPy

ROOT = Path(sys.argv[1]).resolve()
V11 = ROOT / "frontend/lab/audie-model-variants-v11-data/manifest.json"
OUT = ROOT / "frontend/lab/audie-assembly-2d-v14-data"
IMG = OUT / "images"
META = ROOT / "frontend/lab/master-assets-v2/meta/audie-assembly-2d-v14.json"
MAN = OUT / "manifest.json"
OUT.mkdir(parents=True, exist_ok=True)
IMG.mkdir(parents=True, exist_ok=True)
UnityPy.config.FALLBACK_UNITY_VERSION = "2019.4.41f1"

if not V11.is_file():
    raise SystemExit("ERROR: run V11 first")

M = json.loads(V11.read_text("utf-8"))
print("AUDIE_ASSEMBLY_2D_V14_START", flush=True)

def typ(o):
    return str(getattr(getattr(o, "type", None), "name", "") or "")

def pid(o):
    return int(getattr(o, "path_id", 0) or 0)

def sfname(o):
    af = getattr(o, "assets_file", None)
    return str(getattr(af, "name", "") or getattr(af, "file_name", "") or getattr(af, "path", "") or "")

def pname(o):
    try:
        return str(o.peek_name() or "")
    except Exception:
        return ""

def safe(s):
    z = re.sub(r"[^A-Za-z0-9._-]+", "_", str(s)).strip("._")
    return z[:120] or "asset"

def tree(o):
    try:
        return o.read_typetree(wrap=False, check_read=False)
    except TypeError:
        try:
            return o.read_typetree()
        except Exception:
            return {}
    except Exception:
        return {}

def pptr(x):
    if not isinstance(x, dict):
        return None
    fid = x.get("m_FileID", x.get("fileID", x.get("file_id")))
    path = x.get("m_PathID", x.get("pathID", x.get("path_id")))
    try:
        return int(fid or 0), int(path or 0)
    except Exception:
        return None

def serial_base(s):
    s = str(s or "").replace("\\", "/")
    return s.rsplit("/", 1)[-1].lower()

def ext_name(o, file_id):
    if not file_id:
        return sfname(o)
    af = getattr(o, "assets_file", None)
    exts = list(getattr(af, "externals", []) or [])
    idx = file_id - 1
    if idx < 0 or idx >= len(exts):
        return ""
    e = exts[idx]
    for k in ("path", "name"):
        v = getattr(e, k, None)
        if v:
            return str(v)
    try:
        return str(e)
    except Exception:
        return ""

def vec3(v, default):
    if not isinstance(v, dict):
        return list(default)
    def f(k, d):
        try:
            return float(v.get(k, d))
        except Exception:
            return float(d)
    return [f("x", default[0]), f("y", default[1]), f("z", default[2])]

def quat(v):
    if not isinstance(v, dict):
        return [0.0, 0.0, 0.0, 1.0]
    def f(k, d):
        try:
            return float(v.get(k, d))
        except Exception:
            return float(d)
    return [f("x", 0), f("y", 0), f("z", 0), f("w", 1)]

# Mesh lookup includes aliases because a prefab can target a physical copy other than
# the representative chosen by V11 for the same geometry.
mesh_index = {}
mesh_by_pid = defaultdict(list)
for r in M.get("meshes", []) or []:
    row = dict(r)
    sb = serial_base(row.get("serializedFile"))
    mpid = str(row.get("pathID") or "")
    if sb and mpid:
        mesh_index[(sb, mpid)] = row
    if mpid:
        mesh_by_pid[mpid].append(row)
    for a in row.get("aliases", []) or []:
        asb = serial_base(a.get("serializedFile"))
        apid = str(a.get("pathID") or "")
        if asb and apid:
            mesh_index[(asb, apid)] = row

paths = []
seen = set()
for b in M.get("bundles", []) or []:
    p = Path(str(b.get("path") or ""))
    if p.is_file():
        k = str(p.resolve())
        if k not in seen:
            seen.add(k)
            paths.append(p)
paths.sort(key=lambda p: p.name.lower())
print("AUDIE_ASSEMBLY_2D_V14_SCANSET", f"bundles={len(paths)}", flush=True)

assemblies = []
two_d = []
usage_2d = []
errors = []
counts = Counter()
component_clues = {
    "lvdai": "chenille / track",
    "chedeng": "feu / vehicle light",
    "paotong": "canon / barrel",
    "pao": "canon",
    "lun": "roue / wheel",
    "chelun": "roue / wheel",
    "deng": "feu / light",
}

for bi, bundle in enumerate(paths, 1):
    print("AUDIE_ASSEMBLY_2D_V14_SCAN", f"{bi}/{len(paths)}", bundle.name, flush=True)
    try:
        env = UnityPy.load(str(bundle))
        objs = list(env.objects)
    except Exception as e:
        errors.append({"bundle": bundle.name, "stage": "load", "error": f"{type(e).__name__}:{e}"})
        continue

    by_sf = defaultdict(list)
    for o in objs:
        by_sf[serial_base(sfname(o))].append(o)
        counts[typ(o)] += 1

    # Independent 2D path: export Texture2D/Sprite where UnityPy can decode them.
    for o in objs:
        t = typ(o)
        if t not in {"Texture2D", "Sprite", "RenderTexture", "SpriteRenderer"}:
            continue
        tr = tree(o)
        n = pname(o) or str((tr or {}).get("m_Name") or "")
        if t == "SpriteRenderer":
            gp = pptr((tr or {}).get("m_GameObject"))
            sp = pptr((tr or {}).get("m_Sprite"))
            usage_2d.append({
                "bundle": bundle.name,
                "serializedFile": sfname(o),
                "type": t,
                "name": n,
                "pathID": str(pid(o)),
                "gameObjectPathID": str(gp[1]) if gp else "",
                "spriteFileID": sp[0] if sp else None,
                "spritePathID": str(sp[1]) if sp else "",
            })
            continue

        w = h = 0
        if isinstance(tr, dict):
            for k in ("m_Width", "width"):
                if k in tr:
                    try: w = int(tr[k] or 0)
                    except Exception: pass
            for k in ("m_Height", "height"):
                if k in tr:
                    try: h = int(tr[k] or 0)
                    except Exception: pass
        rec = {
            "bundle": bundle.name,
            "bundlePath": str(bundle),
            "serializedFile": sfname(o),
            "type": t,
            "name": n,
            "pathID": str(pid(o)),
            "width": w,
            "height": h,
            "src": "",
            "exported": False,
            "surfaceMap": bool(re.search(r"(?:^|_)(?:d|n|s)(?:$|_)|normal|spec|rough|metal", n.lower())),
            "likelyRendered2D": bool(re.search(r"sprite|icon|formation|team|hero|car|vehicle|preview|show|head|portrait", (n + " " + bundle.name).lower())),
        }
        if t in {"Texture2D", "Sprite"}:
            try:
                d = o.read()
                im = getattr(d, "image", None)
                if im is not None:
                    if not w or not h:
                        try:
                            w, h = int(im.width), int(im.height)
                            rec["width"], rec["height"] = w, h
                        except Exception:
                            pass
                    fn = f"{safe(bundle.stem)}_{safe(serial_base(sfname(o)))}_p{pid(o)}_{safe(n or t)}.png"
                    fp = IMG / fn
                    im.save(fp)
                    rec["src"] = "/lab/audie-assembly-2d-v14-data/images/" + fn
                    rec["exported"] = True
            except Exception as e:
                rec["exportError"] = f"{type(e).__name__}:{e}"
        two_d.append(rec)

    # Reconstruct each local prefab-style hierarchy from real Transform + Mesh consumers.
    for sb, sobjs in by_sf.items():
        if not sb:
            continue
        go_names = {}
        transforms = {}
        go_to_transform = {}
        mesh_parts = []

        for o in sobjs:
            if typ(o) == "GameObject":
                tr = tree(o)
                go_names[pid(o)] = pname(o) or str((tr or {}).get("m_Name") or "")

        for o in sobjs:
            if typ(o) != "Transform":
                continue
            tr = tree(o)
            gp = pptr((tr or {}).get("m_GameObject"))
            fa = pptr((tr or {}).get("m_Father"))
            tid = pid(o)
            goid = gp[1] if gp and gp[0] == 0 else 0
            transforms[tid] = {
                "id": str(tid),
                "pathID": str(tid),
                "gameObjectPathID": str(goid) if goid else "",
                "name": go_names.get(goid, ""),
                "parent": str(fa[1]) if fa and fa[0] == 0 and fa[1] else "",
                "position": vec3((tr or {}).get("m_LocalPosition"), (0, 0, 0)),
                "rotation": quat((tr or {}).get("m_LocalRotation")),
                "scale": vec3((tr or {}).get("m_LocalScale"), (1, 1, 1)),
            }
            if goid:
                go_to_transform[goid] = tid

        for o in sobjs:
            ot = typ(o)
            if ot not in {"MeshFilter", "SkinnedMeshRenderer"}:
                continue
            tr = tree(o)
            gp = pptr((tr or {}).get("m_GameObject"))
            mp = pptr((tr or {}).get("m_Mesh"))
            if not gp or not mp or not mp[1]:
                continue
            goid = gp[1] if gp[0] == 0 else 0
            target_sb = serial_base(ext_name(o, mp[0]))
            mesh = mesh_index.get((target_sb, str(mp[1])))
            if mesh is None:
                alts = mesh_by_pid.get(str(mp[1]), [])
                if len(alts) == 1:
                    mesh = alts[0]
            if mesh is None:
                continue
            tid = go_to_transform.get(goid, 0)
            gn = go_names.get(goid, "")
            clue = ""
            low = (gn + " " + str(mesh.get("name") or "")).lower()
            for k, v in component_clues.items():
                if k in low:
                    clue = v
                    break
            mesh_parts.append({
                "componentType": ot,
                "componentPathID": str(pid(o)),
                "gameObjectPathID": str(goid) if goid else "",
                "gameObject": gn,
                "transformID": str(tid) if tid else "",
                "meshName": mesh.get("name"),
                "meshPathID": str(mesh.get("pathID") or ""),
                "meshSerializedFile": mesh.get("serializedFile"),
                "meshBundle": mesh.get("bundle"),
                "src": mesh.get("src"),
                "vertexCount": mesh.get("vertexCount"),
                "faceCount": mesh.get("faceCount"),
                "clue": clue,
            })

        if not mesh_parts:
            continue

        def root_of(tid):
            seen_tid = set()
            cur = int(tid or 0)
            last = cur
            while cur and cur in transforms and cur not in seen_tid:
                seen_tid.add(cur)
                last = cur
                try:
                    nxt = int(transforms[cur].get("parent") or 0)
                except Exception:
                    nxt = 0
                if not nxt or nxt not in transforms:
                    break
                cur = nxt
            return last

        grouped = defaultdict(list)
        for part in mesh_parts:
            try: tid = int(part.get("transformID") or 0)
            except Exception: tid = 0
            grouped[root_of(tid)].append(part)

        for root_tid, parts in grouped.items():
            used_tids = set()
            for part in parts:
                try: cur = int(part.get("transformID") or 0)
                except Exception: cur = 0
                while cur and cur in transforms and cur not in used_tids:
                    used_tids.add(cur)
                    try: cur = int(transforms[cur].get("parent") or 0)
                    except Exception: cur = 0
            nodes = [transforms[x] for x in used_tids if x in transforms]
            nodes.sort(key=lambda x: int(x["pathID"]))
            root_name = transforms.get(root_tid, {}).get("name", "")
            names = " ".join([root_name, bundle.name] + [str(p.get("gameObject") or "") + " " + str(p.get("meshName") or "") for p in parts])
            if "audie" not in names.lower() and "a_hero_audie_01" not in names.lower() and len(parts) < 2:
                continue
            assemblies.append({
                "bundle": bundle.name,
                "bundlePath": str(bundle),
                "serializedFile": sb,
                "rootTransformID": str(root_tid) if root_tid else "",
                "rootName": root_name or "(root)",
                "partCount": len(parts),
                "vertexTotal": sum(int(p.get("vertexCount") or 0) for p in parts),
                "faceTotal": sum(int(p.get("faceCount") or 0) for p in parts),
                "clues": sorted({p["clue"] for p in parts if p.get("clue")}),
                "transforms": nodes,
                "parts": parts,
            })

uniq = {}
for a in assemblies:
    sig = tuple(sorted((str(p.get("src")), str(p.get("transformID"))) for p in a["parts"]))
    old = uniq.get(sig)
    if old is None or a["partCount"] > old["partCount"]:
        uniq[sig] = a
assemblies = list(uniq.values())
assemblies.sort(key=lambda a: (-a["partCount"], -a["vertexTotal"], a["rootName"].lower(), a["bundle"].lower()))

two_d.sort(key=lambda r: (
    not r.get("exported"),
    r.get("surfaceMap", False),
    not r.get("likelyRendered2D", False),
    -(int(r.get("width") or 0) * int(r.get("height") or 0)),
    str(r.get("name") or "").lower(),
))

multi = [a for a in assemblies if a["partCount"] >= 2]
rendered2d = [r for r in two_d if r.get("exported") and not r.get("surfaceMap")]
verdict = "MULTIPART_PREFAB_ASSEMBLY_FOUND" if multi else "NO_MULTIPART_ASSEMBLY_IN_CURRENT_FAMILY"
if rendered2d:
    verdict += "_AND_2D_IMAGES_PRESENT"

res = {
    "format": "WFGG_LASTWAR_AUDIE_ASSEMBLY_2D_V14",
    "verdict": verdict,
    "counts": {
        "bundles": len(paths),
        "assemblies": len(assemblies),
        "multiPartAssemblies": len(multi),
        "twoDAssets": len(two_d),
        "twoDExported": sum(1 for r in two_d if r.get("exported")),
        "spriteRenderers": len(usage_2d),
    },
    "assemblies": assemblies,
    "twoD": two_d,
    "twoDUsage": usage_2d,
    "objectTypeCounts": dict(counts),
    "errors": errors[:200],
    "rules": [
        "V14 no longer assumes one Mesh equals one vehicle.",
        "MeshFilter/SkinnedMeshRenderer consumers are grouped through the real GameObject/Transform hierarchy and rendered with original local TRS.",
        "Names such as lvdai (track/tread) and chedeng (vehicle light) are treated as component clues, not discarded as unrelated meshes.",
        "The 2D path is checked independently by extracting Texture2D/Sprite assets and listing SpriteRenderer/RenderTexture evidence.",
        "No 2D image or 3D assembly is declared to be the Formation board asset until visually confirmed.",
    ],
}
META.parent.mkdir(parents=True, exist_ok=True)
META.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", "utf-8")
MAN.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", "utf-8")

print("AUDIE_ASSEMBLY_2D_V14_READY", f"verdict={verdict}", f"assemblies={len(assemblies)}", f"multiPart={len(multi)}", f"twoDExported={res['counts']['twoDExported']}", flush=True)
for a in assemblies[:20]:
    print("V14_ASSEMBLY", a["rootName"], f"parts={a['partCount']}", f"v={a['vertexTotal']}", f"f={a['faceTotal']}", f"clues={','.join(a['clues']) or '-'}", a["bundle"], flush=True)
for r in two_d[:20]:
    if r.get("exported"):
        print("V14_2D", r["type"], r["name"] or "-", f"{r['width']}x{r['height']}", r["bundle"], flush=True)
print("JSON=" + str(META), flush=True)
print("VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-assembly-2d-v14.html?v=14", flush=True)
