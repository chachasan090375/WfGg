#!/usr/bin/env python3
import csv, json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend/lab/master-assets-v2/index/lastwar-graphics-asset-path-index-v1.tsv"
OUT = ROOT / "frontend/lab/asset-name-derived-vehicles-v25"
OUT.mkdir(parents=True, exist_ok=True)

# Seul ancrage initial : l'arborescence structurellement prouvée par les
# queue_model_path existants. Aucun dictionnaire tank/car/vehicle/engin n'est utilisé.
STRUCTURAL_RE = re.compile(r"(?i)(?:^|/)models/(?:new/)?cars/")
CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")


def tokseq(text):
    text = CAMEL_RE.sub(r"\1 \2", str(text or ""))
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).lower()
    return [x for x in text.split() if len(x) >= 3 and not x.isdigit()]


def row_tokens(row):
    return set(tokseq(row.get("assetPath", "")))


def structural_info(asset_path):
    p = str(asset_path or "").replace("\\", "/")
    m = STRUCTURAL_RE.search(p)
    if not m:
        return None
    rel = p[m.end():]
    parts = [x for x in rel.split("/") if x]
    root = parts[0] if parts else ""
    return {"root": root, "relative": rel, "prefix": p[:m.end()]}


def rows():
    with SOURCE.open("r", encoding="utf-8", errors="replace", newline="") as f:
        yield from csv.DictReader(f, delimiter="\t")


if not SOURCE.exists():
    raise SystemExit(f"Index exact absent: {SOURCE}")

# PASS 1 : lire chaque nom exact et mesurer son vocabulaire global.
global_df = Counter()
seed_rows = []
roots = set()
root_token_df = Counter()
source_rows = 0

for row in rows():
    source_rows += 1
    ts = row_tokens(row)
    global_df.update(ts)
    si = structural_info(row.get("assetPath"))
    if si:
        roots.add(si["root"])
        root_token_df.update(set(tokseq(si["root"])))
        seed_rows.append((row, si))

seed_root_count = max(1, len(roots))
# Préfixes d'identité récurrents déduits automatiquement des racines de modèles.
root_boilerplate = {t for t, n in root_token_df.items() if n / seed_root_count >= 0.55}

seed_term_records = Counter()
seed_term_roots = defaultdict(set)
seed_examples = defaultdict(list)
seed_count = len(seed_rows)

for row, si in seed_rows:
    asset_path = row.get("assetPath", "")
    root_ts = set(tokseq(si["root"]))
    rel_after_root = si["relative"][len(si["root"]):] if si["root"] else si["relative"]
    ts = set(tokseq(rel_after_root + " " + Path(asset_path).name))
    ts -= root_ts
    ts -= root_boilerplate
    for t in ts:
        seed_term_records[t] += 1
        seed_term_roots[t].add(si["root"])
        if len(seed_examples[t]) < 8:
            seed_examples[t].append(asset_path)

# Le vocabulaire est appris par concentration statistique dans les modèles de véhicules.
learned = []
for t, srec in seed_term_records.items():
    root_support = len(seed_term_roots[t])
    gdf = global_df.get(t, 0)
    seed_p = srec / max(1, seed_count)
    global_p = gdf / max(1, source_rows)
    lift = (seed_p + 1e-9) / (global_p + 1e-9)
    keep = (
        (root_support >= 3 and lift >= 2.2 and global_p <= 0.10) or
        (root_support >= 2 and lift >= 4.0 and global_p <= 0.05) or
        (root_support >= 1 and srec >= 3 and lift >= 10.0 and gdf <= 40)
    )
    if not keep:
        continue
    score = math.log2(max(1.000001, lift)) * math.log1p(root_support) * math.log1p(srec)
    learned.append({
        "term": t,
        "seedRecords": srec,
        "seedRoots": root_support,
        "globalRecords": gdf,
        "lift": round(lift, 3),
        "score": round(score, 3),
        "seedExamples": seed_examples[t],
    })

learned.sort(key=lambda x: (-x["score"], -x["seedRoots"], x["term"]))
term_map = {x["term"]: x for x in learned}
strong_terms = {
    x["term"] for x in learned
    if (x["seedRoots"] >= 3 and x["lift"] >= 3.0) or x["lift"] >= 9.0
}

# PASS 2 : relire les 107247 titres. Tous les noms sous Models/Cars sont gardés ;
# hors de cette arborescence, seuls les noms partageant des signatures apprises
# sont remontés, avec justification détaillée.
selected = []
selected_bundles = set()
outside_count = 0
exact_count = 0

for row in rows():
    asset_path = row.get("assetPath", "")
    si = structural_info(asset_path)
    ts = row_tokens(row)
    reasons = []

    if si:
        exact_count += 1
        scope = "models-cars-exact"
        confidence = "structure-certaine"
        score = 1000.0
        reasons.append({"kind": "structure", "value": si["prefix"]})
    else:
        matches = [term_map[t] for t in sorted(ts & strong_terms)]
        if not matches:
            continue
        exceptional = [m for m in matches if m["lift"] >= 12.0 and m["seedRoots"] >= 2]
        if len(matches) < 2 and not exceptional:
            continue
        score = sum(m["score"] for m in matches)
        scope = "derived-outside"
        confidence = "forte" if len(matches) >= 3 or exceptional else "a-verifier"
        outside_count += 1
        reasons.extend({
            "kind": "terme-appris",
            "value": m["term"],
            "seedRoots": m["seedRoots"],
            "seedRecords": m["seedRecords"],
            "globalRecords": m["globalRecords"],
            "lift": m["lift"],
        } for m in sorted(matches, key=lambda x: -x["score"])[:12])

    logical = row.get("logicalName", "")
    if logical:
        selected_bundles.add(logical)
    selected.append({
        "scope": scope,
        "confidence": confidence,
        "score": round(score, 3),
        "parent": str(Path(asset_path).parent).replace("\\", "/"),
        "pattern": Path(asset_path).name,
        "ext": Path(asset_path).suffix,
        "count": 1,
        "examples": [asset_path],
        "logicalNames": [logical] if logical else [],
        "aliasName": row.get("aliasName", ""),
        "bundleId": row.get("bundleId", ""),
        "declaredBytes": row.get("declaredBytes", ""),
        "dependencies": row.get("dependencies", ""),
        "evidenceFiles": [x for x in (row.get("evidenceFiles", "") or "").split("|") if x],
        "reasons": reasons,
    })

selected.sort(key=lambda x: (0 if x["scope"] == "derived-outside" else 1, -x["score"], x["parent"], x["pattern"]))

manifest = {
    "version": 25,
    "method": "exact-asset-path-name-derived-no-predefined-vehicle-vocabulary",
    "source": "master-assets-v2/index/lastwar-graphics-asset-path-index-v1.tsv",
    "sourceFamilies": source_rows,
    "seed": {
        "rule": "structural Models/(New/)?Cars path proven by existing queue_model_path records",
        "families": exact_count,
        "roots": len(roots),
        "rootBoilerplateInferred": sorted(root_boilerplate),
    },
    "learnedTermCount": len(learned),
    "strongTermCount": len(strong_terms),
    "derivedOutsideFamilies": outside_count,
    "selectedFamilies": len(selected),
    "selectedBundleCount": len(selected_bundles),
    "learnedTerms": learned,
    "selected": selected,
}

(OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
(OUT / "selected-bundles.txt").write_text("\n".join(sorted(selected_bundles)) + "\n", encoding="utf-8")
(OUT / "learned-terms.txt").write_text(
    "\n".join(
        f"{x['term']}\tseedRoots={x['seedRoots']}\tseedRecords={x['seedRecords']}\tglobal={x['globalRecords']}\tlift={x['lift']}\tscore={x['score']}"
        for x in learned
    ) + "\n",
    encoding="utf-8",
)

print("V25 exact-name-derived vehicle audit")
print(f"exactNamesRead={source_rows}")
print(f"modelsCarsExact={exact_count} roots={len(roots)}")
print(f"learnedTerms={len(learned)} strongTerms={len(strong_terms)}")
print(f"derivedOutside={outside_count}")
print(f"selectedNames={len(selected)} bundles={len(selected_bundles)}")
print(f"manifest={OUT / 'manifest.json'}")
