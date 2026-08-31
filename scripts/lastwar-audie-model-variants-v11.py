#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

from pathlib import Path
from collections import Counter, defaultdict
import hashlib
import json
import re
import sys

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "scripts"))
from wfgg_unity_raw_mesh import typ, pid, sfname, pname, safe, raw_mesh_to_obj

import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION = "2019.4.41f1"

V5 = ROOT / "frontend/lab/master-assets-v2/meta/audie-package-family-v5.json"
V8 = ROOT / "frontend/lab/master-assets-v2/meta/audie-mesh-external-v8.json"
OLD_MAN = ROOT / "frontend/lab/audie-mesh-carrier-v6-data/manifest.json"
OUT = ROOT / "frontend/lab/audie-model-variants-v11-data"
MESHDIR = OUT / "meshes"
META = ROOT / "frontend/lab/master-assets-v2/meta/audie-model-variants-v11.json"
MAN = OUT / "manifest.json"
OUT.mkdir(parents=True, exist_ok=True)
MESHDIR.mkdir(parents=True, exist_ok=True)
for p in MESHDIR.glob("*.obj"):
    try: p.unlink()
    except Exception: pass


def strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from strings(v)


def add_path(paths, x):
    try:
        p = Path(str(x))
    except Exception:
        return
    if p.is_file() and p.suffix.lower() == ".bundle":
        paths[str(p.resolve())] = p

paths = {}
if V5.is_file():
    v5 = json.loads(V5.read_text("utf-8"))
    for r in v5.get("bundles", []) or []:
        add_path(paths, r.get("path"))
    for r in v5.get("meshCarriers", []) or []:
        add_path(paths, r.get("path"))
else:
    v5 = {}
if V8.is_file():
    v8 = json.loads(V8.read_text("utf-8"))
    for s in strings(v8):
        if str(s).endswith(".bundle"):
            add_path(paths, s)
else:
    v8 = {}

# Direct family names are strong evidence and cheap to include.
for base in (ROOT / "frontend/lab/local_assets", Path.home() / ".cache"):
    if not base.exists():
        continue
    for p in base.rglob("*.bundle"):
        n = p.name.lower()
        if "audie" in n or "a_hero_audie_01" in n:
            add_path(paths, p)

candidates = sorted(paths.values(), key=lambda p: p.name.lower())
print("AUDIE_MODEL_VARIANTS_V11_START", f"bundles={len(candidates)}", flush=True)


def tags_for(text):
    s = str(text).lower()
    tags = []
    rules = [
        ("lod0", r"(?:^|[_-])lod[_-]?0(?:[_-]|$)"),
        ("lod1", r"(?:^|[_-])lod[_-]?1(?:[_-]|$)"),
        ("lod2", r"(?:^|[_-])lod[_-]?2(?:[_-]|$)"),
        ("lod3", r"(?:^|[_-])lod[_-]?3(?:[_-]|$)"),
        ("low", r"(?:^|[_-])(low|simple|lite|mobile)(?:[_-]|$)"),
        ("high", r"(?:^|[_-])(high|hd)(?:[_-]|$)"),
        ("battle", r"(?:^|[_-])(battle|fight|combat)(?:[_-]|$)"),
        ("formation", r"(?:^|[_-])(formation|team|array)(?:[_-]|$)"),
        ("prefab", r"prefab"),
        ("skin", r"skin"),
        ("bullet", r"bullet"),
        ("missile", r"missile"),
        ("base", r"a_hero_audie_01(?:$|[_-])"),
    ]
    for tag, pat in rules:
        if re.search(pat, s): tags.append(tag)
    return tags


def complexity_bucket(v, f):
    score = int(v or 0) + int(f or 0) * 0.5
    if score < 800: return "very-low"
    if score < 2200: return "low"
    if score < 6000: return "medium"
    return "high"

rows = []
bundle_rows = []
errors = []
for bi, p in enumerate(candidates, 1):
    print("AUDIE_MODEL_VARIANTS_V11_SCAN", f"{bi}/{len(candidates)}", p.name, flush=True)
    try:
        env = UnityPy.load(str(p))
        objs = list(env.objects)
    except Exception as e:
        errors.append({"bundle": p.name, "path": str(p), "stage": "load", "error": f"{type(e).__name__}:{e}"})
        continue
    counts = Counter(typ(o) for o in objs)
    bmesh = 0
    for o in objs:
        if typ(o) != "Mesh":
            continue
        try:
            text, info = raw_mesh_to_obj(o)
            digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
            fn = f"{safe(p.stem)}_p{pid(o)}_{safe(info['name'])}_{digest}.obj"
            fp = MESHDIR / fn
            if not fp.exists(): fp.write_text(text, "utf-8", newline="")
            full_text = p.name + " " + info["name"]
            tags = tags_for(full_text)
            bucket = complexity_bucket(info["vertexCount"], info["faceCount"])
            rec = {
                "bundle": p.name,
                "bundlePath": str(p),
                "serializedFile": sfname(o),
                "pathID": str(pid(o)),
                "name": info["name"],
                "src": "/lab/audie-model-variants-v11-data/meshes/" + fn,
                "sha1": digest,
                "vertexCount": info["vertexCount"],
                "faceCount": info["faceCount"],
                "indexCount": info["indexCount"],
                "subMeshCount": len(info.get("subMeshes") or []),
                "hasUV0": bool(info.get("hasUV0")),
                "hasNormals": bool(info.get("hasNormals")),
                "complexity": bucket,
                "tags": tags,
                "rendererReferenced": False,
            }
            rows.append(rec)
            bmesh += 1
            print("AUDIE_MODEL_VARIANTS_V11_MESH", info["name"], f"v={info['vertexCount']}", f"f={info['faceCount']}", f"complexity={bucket}", "tags=" + ",".join(tags), flush=True)
        except Exception as e:
            errors.append({"bundle": p.name, "pathID": str(pid(o)), "name": pname(o), "stage": "raw-mesh", "error": f"{type(e).__name__}:{e}"})
    bundle_rows.append({"basename": p.name, "path": str(p), "meshCount": bmesh, "counts": dict(counts)})

# Preserve exact renderer-reference evidence already obtained by V8/V10.
ref_keys = set()
for r in ((v8.get("diagnostics") or {}).get("resolvedPointers") or []):
    if str(r.get("resolvedType") or "") == "Mesh":
        ref_keys.add((Path(str(r.get("resolvedPath") or "")).name, str(r.get("meshPathID") or "")))
for r in rows:
    if (r["bundle"], r["pathID"]) in ref_keys:
        r["rendererReferenced"] = True

# Deduplicate aliases while keeping every physical source for traceability.
groups = defaultdict(list)
for r in rows:
    groups[r["sha1"]].append(r)
unique = []
for sha, xs in groups.items():
    # prefer renderer-referenced, then descriptive Audie names, then shortest bundle name
    xs.sort(key=lambda r: (not r["rendererReferenced"], "audie" not in r["name"].lower(), len(r["bundle"])))
    best = dict(xs[0])
    best["aliasCount"] = len(xs)
    best["aliases"] = [{"bundle": x["bundle"], "pathID": x["pathID"], "serializedFile": x["serializedFile"]} for x in xs]
    unique.append(best)

# For the board-model hunt, simplified meshes are surfaced first, but bullets/missiles are demoted.
def rank(r):
    accessory = any(t in r["tags"] for t in ("bullet", "missile"))
    named = "a_hero_audie_01" in r["name"].lower()
    return (
        accessory,
        not named,
        {"very-low": 0, "low": 1, "medium": 2, "high": 3}.get(r["complexity"], 9),
        r["vertexCount"],
        r["faceCount"],
        r["name"].lower(),
    )
unique.sort(key=rank)

textures = []
if OLD_MAN.is_file():
    try: textures = (json.loads(OLD_MAN.read_text("utf-8")).get("textures") or [])
    except Exception: textures = []

main_variants = [r for r in unique if "a_hero_audie_01" in r["name"].lower() and not any(t in r["tags"] for t in ("bullet", "missile"))]
low_main = [r for r in main_variants if r["complexity"] in ("very-low", "low")]
verdict = "SIMPLIFIED_MAIN_VARIANT_FOUND" if low_main else ("MULTIPLE_MAIN_VARIANTS_FOUND" if len(main_variants) > 1 else "ONLY_DETAILED_MAIN_VARIANT_IN_CURRENT_FAMILY")

res = {
    "format": "WFGG_LASTWAR_AUDIE_MODEL_VARIANTS_V11",
    "verdict": verdict,
    "purpose": "Find the actual formation-board geometry rather than assuming the first detailed Audie mesh is the runtime board model.",
    "counts": {"bundles": len(candidates), "rawMeshes": len(rows), "uniqueMeshes": len(unique), "mainVariants": len(main_variants), "simplifiedMainVariants": len(low_main), "textures": len(textures)},
    "meshes": unique,
    "mainVariants": main_variants,
    "bundles": bundle_rows,
    "textures": textures,
    "errors": errors[:300],
    "rules": [
        "The detailed A_Hero_Audie_01 mesh is no longer assumed to be the formation-board model.",
        "Every Mesh in every proven Audie family bundle is decoded from raw TypeTree data; Mesh.export()/FMOD is not used.",
        "Candidates are grouped by OBJ geometry hash so bundle aliases do not create fake variants.",
        "Complexity is measured from actual vertex/face counts and used only as a search heuristic, not proof of runtime use.",
        "Bullet and missile accessory meshes are retained but demoted when looking for the main board vehicle.",
    ],
}
META.parent.mkdir(parents=True, exist_ok=True)
META.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", "utf-8")
MAN.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", "utf-8")
print("AUDIE_MODEL_VARIANTS_V11_READY", f"verdict={verdict}", f"uniqueMeshes={len(unique)}", f"mainVariants={len(main_variants)}", f"simplifiedMain={len(low_main)}", flush=True)
for r in main_variants[:30]:
    print("MAIN_VARIANT", r["name"], f"v={r['vertexCount']}", f"f={r['faceCount']}", f"complexity={r['complexity']}", f"bundle={r['bundle']}", flush=True)
print("JSON=" + str(META), flush=True)
