#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

from pathlib import Path
from collections import Counter, defaultdict
import csv, json, math, re, sys

ROOT = Path(sys.argv[1]).resolve()
AUDIT = ROOT / "frontend/lab/asset-name-audit-v24"
MASTER = ROOT / "frontend/lab/master-assets-v2"
OUT = ROOT / "frontend/lab/semantic-vehicle-v25-data"
OUT.mkdir(parents=True, exist_ok=True)
MAN = OUT / "manifest.json"
TXT = OUT / "candidate-bundles.txt"

HEADER_PREFIX = "assetPath\tbundleId\tlogicalName\taliasName\tdeclaredBytes"
VEHICLE_ROOT_RE = re.compile(r"/models/(?:new/)?cars/", re.I)
RASTER_EXT = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".webp", ".psd", ".exr", ".hdr"}

# These are syntax / pipeline words, not a vehicle vocabulary. They are removed so
# the language is learned from the game's own vehicle families rather than from
# trivial Unity/path terminology.
STOP = {
    "assets","asset","art","lastwar","last","war","model","models","new",
    "cars","car","hero","mesh","texture","textures","material","materials",
    "prefab","prefabs","animation","animations","animator","common","pbr",
    "high","low","skin","file","auto","main","dir","bundle","gameres",
    "controller","timeline","playable","effect","effects","root","preview",
    "idle","attack","walk","dead","camera","move","show","skill","skll",
    "battle","city","inspecialdir","res","resource","resources","default",
}


def split_camel(s: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    return s


def tokens(text: str) -> set[str]:
    text = split_camel(str(text or "")).lower()
    parts = re.findall(r"[a-z][a-z0-9]{2,}", text)
    out = set()
    for p in parts:
        p = re.sub(r"\d+$", "", p)
        if len(p) < 3 or p in STOP:
            continue
        if p.isdigit():
            continue
        out.add(p)
    return out


def is_vehicle_seed(path: str) -> bool:
    return bool(VEHICLE_ROOT_RE.search(str(path or "").replace("\\", "/")))


def vehicle_identity(path: str) -> str:
    p = str(path or "").replace("\\", "/")
    m = VEHICLE_ROOT_RE.search(p)
    if not m:
        return ""
    tail = p[m.end():]
    first = tail.split("/", 1)[0].strip()
    return first.lower()


def identity_aliases(identity: str) -> set[str]:
    z = split_camel(identity.lower())
    z = re.sub(r"^a_hero_", "", z)
    z = re.sub(r"^hero_", "", z)
    z = re.sub(r"_v\d+$", "", z)
    z = re.sub(r"_\d+$", "", z)
    return {x for x in re.findall(r"[a-z][a-z0-9]{2,}", z) if x not in STOP and len(x) >= 3}


def find_exact_source() -> Path | None:
    roots = [MASTER / "index", MASTER / "meta", MASTER, AUDIT]
    seen = set()
    candidates = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            try:
                if not p.is_file() or p in seen:
                    continue
                seen.add(p)
                if p.stat().st_size < 2_000_000:
                    continue
                if p.suffix.lower() not in {".tsv", ".txt", ".csv"}:
                    continue
                with p.open("r", encoding="utf-8", errors="replace") as f:
                    first = f.readline().rstrip("\r\n")
                if first.startswith(HEADER_PREFIX):
                    candidates.append(p)
            except Exception:
                continue
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
    return candidates[0]


def read_rows_exact(path: Path):
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        r = csv.DictReader(f, delimiter="\t")
        for row in r:
            yield row


def load_family_fallback():
    fm = AUDIT / "families-manifest.json"
    if not fm.is_file():
        raise SystemExit("ERROR: exact asset TSV not found and V24 family manifest absent")
    data = json.loads(fm.read_text("utf-8"))
    for ch in data.get("chunks", []):
        p = AUDIT / ch["file"]
        try:
            arr = json.loads(p.read_text("utf-8"))
        except Exception:
            continue
        for x in arr:
            ex = list(x.get("examples") or [])
            path = ex[0] if ex else str(x.get("parent") or "") + "/" + str(x.get("pattern") or "") + str(x.get("ext") or "")
            yield {
                "assetPath": path,
                "bundleId": "",
                "logicalName": (x.get("logicalNames") or [""])[0],
                "aliasName": "",
                "declaredBytes": "",
                "dependencies": "",
                "confidence": "",
                "evidenceFiles": "|".join(x.get("evidenceFiles") or []),
                "_familyParent": x.get("parent") or "",
                "_familyPattern": x.get("pattern") or "",
                "_familyCount": x.get("count") or 1,
            }


def row_signature(row: dict) -> str:
    return " ".join([
        str(row.get("assetPath") or ""),
        str(row.get("logicalName") or ""),
    ])


def row_public(row: dict, matched: list[str], aliases: list[str], score: float, reason: str):
    p = str(row.get("assetPath") or "")
    ext = Path(p).suffix.lower()
    return {
        "assetPath": p,
        "basename": p.replace("\\", "/").split("/")[-1],
        "ext": ext,
        "rasterSource": ext in RASTER_EXT,
        "bundleId": str(row.get("bundleId") or ""),
        "logicalName": str(row.get("logicalName") or ""),
        "aliasName": str(row.get("aliasName") or ""),
        "declaredBytes": str(row.get("declaredBytes") or ""),
        "dependencies": str(row.get("dependencies") or ""),
        "confidence": str(row.get("confidence") or ""),
        "evidenceFiles": str(row.get("evidenceFiles") or ""),
        "matchedLearnedTerms": matched,
        "matchedVehicleAliases": aliases,
        "score": round(score, 3),
        "reason": reason,
    }


source = find_exact_source()
exact = source is not None
rows_factory = (lambda: read_rows_exact(source)) if exact else load_family_fallback

print("SEMANTIC_VEHICLE_V25_START", "exactRows=" + str(exact), "source=" + str(source or "V24 family fallback"), flush=True)

# PASS 1 — read every name. No user-provided vehicle keyword list is used.
global_df = Counter()
seed_df = Counter()
seed_identity_terms = defaultdict(set)
seed_rows = 0
total_rows = 0
identities = set()
identity_alias_set = set()

for row in rows_factory():
    total_rows += 1
    sig = row_signature(row)
    ts = tokens(sig)
    global_df.update(ts)
    p = str(row.get("assetPath") or "")
    if is_vehicle_seed(p):
        seed_rows += 1
        seed_df.update(ts)
        ident = vehicle_identity(p)
        if ident:
            identities.add(ident)
            als = identity_aliases(ident)
            identity_alias_set.update(als)
            for t in ts:
                seed_identity_terms[t].add(ident)

if seed_rows == 0:
    raise SystemExit("ERROR: no structural Models/Cars seed found")

# Learn the game's own vehicle language from repeated terms across several
# independent vehicle identities. Hero names do not qualify unless shared.
learned = []
for t, sdf in seed_df.items():
    ids = seed_identity_terms.get(t, set())
    if sdf < 2 or len(ids) < 2:
        continue
    gdf = global_df.get(t, 0)
    if not gdf:
        continue
    seed_rate = sdf / seed_rows
    global_rate = gdf / max(total_rows, 1)
    enrichment = seed_rate / max(global_rate, 1e-12)
    if enrichment < 2.0:
        continue
    weight = math.log2(1.0 + enrichment) * math.log2(1.0 + len(ids))
    learned.append({
        "term": t,
        "seedRows": sdf,
        "globalRows": gdf,
        "vehicleIdentities": len(ids),
        "enrichment": round(enrichment, 3),
        "weight": round(weight, 3),
        "identityExamples": sorted(ids)[:12],
    })

learned.sort(key=lambda x: (-x["weight"], -x["vehicleIdentities"], x["term"]))
learned = learned[:180]
learned_weight = {x["term"]: float(x["weight"]) for x in learned}
learned_terms = set(learned_weight)

print("SEMANTIC_VEHICLE_V25_LANGUAGE", f"rows={total_rows}", f"seedRows={seed_rows}", f"identities={len(identities)}", f"learnedTerms={len(learned)}", flush=True)
print("LEARNED_TOP", ", ".join(x["term"] for x in learned[:40]), flush=True)

# PASS 2 — score every remaining exact name using only vocabulary learned above,
# plus internal vehicle identity aliases learned from the Cars directory names.
candidates = []
direct_samples = []
all_direct = 0
outside_hits = 0
raster_hits = 0
bundle_names = set()

for row in rows_factory():
    p = str(row.get("assetPath") or "")
    if is_vehicle_seed(p):
        all_direct += 1
        if len(direct_samples) < 600:
            direct_samples.append(row_public(row, [], [], 999.0, "structural Models/Cars family"))
        continue

    sig = row_signature(row)
    ts = tokens(sig)
    mt = sorted(ts & learned_terms, key=lambda t: -learned_weight[t])
    ma = sorted(ts & identity_alias_set)
    if not mt and not ma:
        continue

    score = sum(learned_weight[t] for t in mt)
    # Alias bridges are deliberately weaker than learned component language.
    score += 2.25 * len(ma)
    ext = Path(p).suffix.lower()
    if ext in RASTER_EXT:
        score += 3.5
    # Multiple independent learned terms are much stronger than one coincidence.
    if len(mt) >= 2:
        score += 2.0 + min(4.0, len(mt) - 2)

    reason_bits = []
    if mt:
        reason_bits.append("langage véhicule appris: " + ", ".join(mt[:8]))
    if ma:
        reason_bits.append("alias interne appris depuis Models/Cars: " + ", ".join(ma[:6]))
    if ext in RASTER_EXT:
        reason_bits.append("source image 2D")

    rec = row_public(row, mt, ma, score, " · ".join(reason_bits))
    candidates.append(rec)
    outside_hits += 1
    raster_hits += bool(rec["rasterSource"])
    if rec["logicalName"]:
        bundle_names.add(rec["logicalName"])

# Keep a large but browser-safe set; all candidate bundles are still emitted to TXT.
candidates.sort(key=lambda x: (-x["score"], not x["rasterSource"], x["assetPath"].lower()))
all_candidates_count = len(candidates)
browser_candidates = candidates[:5000]

TXT.write_text("\n".join(sorted(bundle_names)) + ("\n" if bundle_names else ""), "utf-8")

result = {
    "format": "WFGG_LASTWAR_SEMANTIC_VEHICLE_NAMES_V25",
    "method": "Read every exact asset title when master TSV is available; use Models/Cars only as structural seed; learn repeated enriched vocabulary across independent vehicle identities; rescan every remaining name with learned terms and learned internal aliases.",
    "source": str(source) if source else "V24 family-pattern fallback",
    "exactRows": exact,
    "counts": {
        "rowsRead": total_rows,
        "directVehicleRows": all_direct,
        "vehicleIdentities": len(identities),
        "learnedTerms": len(learned),
        "outsideCandidates": all_candidates_count,
        "raster2DCandidates": raster_hits,
        "candidateBundles": len(bundle_names),
        "browserCandidates": len(browser_candidates),
    },
    "learnedTerms": learned,
    "vehicleIdentityAliases": sorted(identity_alias_set),
    "candidates": browser_candidates,
    "directSamples": direct_samples,
    "candidateBundleList": "/lab/semantic-vehicle-v25-data/candidate-bundles.txt",
    "rules": [
        "No predefined tank/car/vehicle synonym list is used to select candidates.",
        "Models/Cars is used only as a known structural ground-truth seed from the game's own directory tree.",
        "Terms must recur across multiple independent vehicle identities and be enriched versus the whole catalog before they become learned vehicle language.",
        "Internal hero/vehicle aliases are learned from directory identities and tracked separately from semantic vehicle terms.",
        "2D raster source files are prioritized after semantic matching, never used to invent the vehicle vocabulary.",
    ],
}
MAN.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")

print("SEMANTIC_VEHICLE_V25_READY", json.dumps(result["counts"], ensure_ascii=False), flush=True)
print("MANIFEST=" + str(MAN), flush=True)
print("BUNDLES=" + str(TXT), flush=True)
print("VIEWER=http://127.0.0.1:8788/lab/lastwar-semantic-vehicle-names-v25.html?v=25", flush=True)
