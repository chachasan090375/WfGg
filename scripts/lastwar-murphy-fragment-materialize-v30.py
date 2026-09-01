#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

from pathlib import Path
from collections import defaultdict
import csv, json, os, re, subprocess, sys, zipfile

ROOT = Path(sys.argv[1]).resolve()
RET = ROOT / "frontend/lab/manual-review-v27/index/retained.json"
TSV = ROOT / "frontend/lab/master-assets-v2/index/lastwar-graphics-asset-path-index-v1.tsv"
OUT = ROOT / "frontend/lab/local_assets/v30-fragment-materialized"
OUT.mkdir(parents=True, exist_ok=True)

if not RET.is_file(): raise SystemExit(f"retained index absent: {RET}")
if not TSV.is_file(): raise SystemExit(f"asset-path index absent: {TSV}")


def as_int(v,d=-1):
    try:return int(v)
    except Exception:return d

def norm(s):return str(s or "").replace("\\","/").strip()
def base(s):return Path(norm(s)).name

data=json.loads(RET.read_text("utf-8"))
items=list(data.get("items") or [])
audie=next((x for x in items if as_int(x.get("id"))==5115),{})
audie_deps=[as_int(x) for x in (audie.get("dependencies") or []) if as_int(x)>=0]
needed=set()
for x in items:
    bid=as_int(x.get("bundleId"));
    if bid>=0:needed.add(bid)
    if x.get("category")=="direct-candidate":
        needed.update(as_int(v) for v in (x.get("uniqueDependencies") or []) if as_int(v)>=0)
        needed.update(audie_deps)
    elif as_int(x.get("id"))==5115:
        needed.update(audie_deps)

rows=defaultdict(list)
with TSV.open("r",encoding="utf-8",errors="replace",newline="") as f:
    for r in csv.DictReader(f,delimiter="\t"):
        bid=as_int(r.get("bundleId"))
        if bid not in needed:continue
        rec={
            "bundleId":bid,
            "assetPath":norm(r.get("assetPath")),
            "logicalName":norm(r.get("logicalName")),
            "aliasName":norm(r.get("aliasName")),
            "tableFragment":norm(r.get("tableFragment")),
            "fragmentEntry":norm(r.get("fragmentEntry")),
            "offset":as_int(r.get("offset"),0),
            "spanBytes":as_int(r.get("spanBytes"),0),
            "declaredBytes":as_int(r.get("declaredBytes"),0),
            "identity":norm(r.get("identity")),
            "confidence":as_int(r.get("confidence"),0),
        }
        rows[bid].append(rec)

# Choose one deterministic reconstruction descriptor per bundle ID.
# Prefer entries with fragment path + positive span and strongest confidence.
desc={}
for bid,xs in rows.items():
    xs=sorted(xs,key=lambda r:(not bool(r["fragmentEntry"] or r["tableFragment"]),-(r["confidence"]),-(r["spanBytes"]),r["assetPath"]))
    for r in xs:
        if (r["fragmentEntry"] or r["tableFragment"]) and r["spanBytes"]>0 and r["offset"]>=0:
            desc[bid]=r;break

frag_names=set()
for r in desc.values():
    if r["fragmentEntry"]:frag_names.add(base(r["fragmentEntry"]).lower())
    if r["tableFragment"]:frag_names.add(base(r["tableFragment"]).lower())

roots=[
    ROOT,
    Path.home()/".cache",
    Path.home()/"storage/downloads",
    Path.home()/"storage/shared/Download",
    Path("/sdcard/Android/data/com.fun.lastwar.gp"),
    Path("/storage/emulated/0/Android/data/com.fun.lastwar.gp"),
]

disk=defaultdict(list)
print("V30_FRAGMENT_SCAN_START",f"neededBundles={len(needed)}",f"fragmentNames={len(frag_names)}",flush=True)
for rt in roots:
    if not rt.exists():continue
    try:
        for dp,dirs,files in os.walk(rt):
            dirs[:]=[d for d in dirs if d not in {".git","node_modules","bundle-reconstruction-data","v30-fragment-materialized"}]
            for fn in files:
                low=fn.lower()
                if low in frag_names:
                    disk[low].append(Path(dp)/fn)
    except (PermissionError,OSError):
        pass
print("V30_FRAGMENT_DISK_READY",f"matchedNames={len(disk)}",f"files={sum(len(v) for v in disk.values())}",flush=True)

# Also inspect installed APK/splits. BundleFragment*.bytes commonly live inside
# assets/AssetBundles and therefore do not appear as normal files on Android.
apks=[]
try:
    out=subprocess.check_output(["pm","path","com.fun.lastwar.gp"],text=True,stderr=subprocess.DEVNULL,timeout=15)
    for line in out.splitlines():
        if line.startswith("package:"):
            p=Path(line[8:].strip())
            if p.is_file():apks.append(p)
except Exception:pass
for rt in [Path.home()/"storage/downloads",Path.home()/"storage/shared/Download",ROOT]:
    if not rt.exists():continue
    try:
        for p in rt.rglob("*.apk"):
            if p not in apks:apks.append(p)
    except Exception:pass

zip_hits=defaultdict(list)
for ap in apks:
    try:
        with zipfile.ZipFile(ap) as z:
            for zi in z.infolist():
                b=Path(zi.filename).name.lower()
                if b in frag_names:
                    zip_hits[b].append((ap,zi.filename,zi.file_size))
    except Exception:pass
print("V30_FRAGMENT_APK_READY",f"apks={len(apks)}",f"matchedNames={len(zip_hits)}",flush=True)


def read_slice_file(p,off,size):
    with p.open("rb") as f:
        f.seek(off)
        return f.read(size)

def read_slice_zip(ap,entry,off,size):
    with zipfile.ZipFile(ap) as z:
        with z.open(entry,"r") as f:
            try:f.seek(off)
            except Exception:
                left=off
                while left>0:
                    chunk=f.read(min(left,1024*1024))
                    if not chunk:break
                    left-=len(chunk)
            return f.read(size)

def plausible_bundle(blob):
    if not blob:return False
    return blob.startswith((b"UnityFS",b"UnityWeb",b"UnityRaw"))

def recover(r):
    names=[]
    if r.get("fragmentEntry"):names.append(base(r["fragmentEntry"]).lower())
    if r.get("tableFragment"):names.append(base(r["tableFragment"]).lower())
    names=list(dict.fromkeys(names))
    off=max(0,r["offset"]); sz=max(0,r["spanBytes"] or r["declaredBytes"])
    if sz<=0:return b"",{"error":"zero span"}
    for n in names:
        for p in disk.get(n,[]):
            try:
                blob=read_slice_file(p,off,sz)
                if plausible_bundle(blob):return blob,{"mode":"disk-fragment","source":str(p),"fragment":n}
                # tolerate table offsets with a small alignment/header skew
                probe=blob.find(b"UnityFS",0,min(len(blob),8192))
                if probe>=0:return blob[probe:],{"mode":"disk-fragment-adjusted","source":str(p),"fragment":n,"adjust":probe}
            except Exception:pass
    for n in names:
        for ap,entry,_ in zip_hits.get(n,[]):
            try:
                blob=read_slice_zip(ap,entry,off,sz)
                if plausible_bundle(blob):return blob,{"mode":"apk-fragment","source":str(ap),"entry":entry,"fragment":n}
                probe=blob.find(b"UnityFS",0,min(len(blob),8192))
                if probe>=0:return blob[probe:],{"mode":"apk-fragment-adjusted","source":str(ap),"entry":entry,"fragment":n,"adjust":probe}
            except Exception:pass
    return b"",{"error":"fragment source/slice unresolved","fragments":names,"offset":off,"span":sz}

report=[]
for i,bid in enumerate(sorted(needed),1):
    dest=OUT/f"bundle-{bid}.bundle"
    # Keep already valid materializations.
    if dest.is_file():
        try:
            head=dest.open("rb").read(8)
            if head.startswith((b"UnityFS",b"UnityWeb",b"UnityRaw")):
                report.append({"bundleId":bid,"status":"existing","path":str(dest),"bytes":dest.stat().st_size});continue
        except Exception:pass
    r=desc.get(bid)
    if not r:
        report.append({"bundleId":bid,"status":"missing-descriptor"});continue
    blob,src=recover(r)
    if blob:
        dest.write_bytes(blob)
        report.append({"bundleId":bid,"status":"materialized","path":str(dest),"bytes":len(blob),"descriptor":r,"source":src})
        print("V30_BUNDLE",f"{i}/{len(needed)}",bid,"OK",len(blob),src.get("mode"),flush=True)
    else:
        report.append({"bundleId":bid,"status":"unresolved","descriptor":r,"source":src})
        print("V30_BUNDLE",f"{i}/{len(needed)}",bid,"MISS",src.get("error"),flush=True)

ok=sum(x["status"] in {"materialized","existing"} for x in report)
rep={"format":"WFGG_LASTWAR_MURPHY_FRAGMENT_MATERIALIZE_V30","needed":len(needed),"materializedOrExisting":ok,"items":report}
(OUT/"report.json").write_text(json.dumps(rep,ensure_ascii=False,indent=2)+"\n","utf-8")
print("V30_READY",f"materializedOrExisting={ok}/{len(needed)}",f"out={OUT}",flush=True)
