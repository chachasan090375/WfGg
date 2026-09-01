#!/usr/bin/env python3
import json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
AUDIT = ROOT / "frontend/lab/asset-name-audit-v24"
FAMILY_DIR = AUDIT / "families"
OUT = ROOT / "frontend/lab/asset-name-derived-vehicles-v25"
OUT.mkdir(parents=True, exist_ok=True)

# Important: this is a structural anchor, not a vocabulary filter. These are the
# model directories already proven by queue_model_path records. No tank/car/vehicle
# keyword list is used to select names.
STRUCTURAL_RE = re.compile(r"(?i)(?:^|/)models/(?:new/)?cars/")
CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")


def tokseq(text):
    text = CAMEL_RE.sub(r"\1 \2", str(text or ""))
    text = re.sub(r"\{[^}]*\}", " ", text)
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).lower()
    return [x for x in text.split() if len(x) >= 3 and not x.isdigit()]


def record_tokens(r):
    bits = [r.get("parent", ""), r.get("pattern", "")]
    for ex in (r.get("examples") or [])[:3]:
        bits.append(Path(str(ex)).name)
    return set(tokseq(" ".join(bits)))


def structural_info(r):
    parent = str(r.get("parent") or "").replace("\\", "/")
    m = STRUCTURAL_RE.search(parent)
    if not m:
        return None
    rel = parent[m.end():]
    parts = [p for p in rel.split("/") if p]
    root = parts[0] if parts else ""
    return {"root": root, "relative": rel, "prefix": parent[:m.end()]}


def iter_chunks():
    for p in sorted(FAMILY_DIR.glob("chunk-*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"WARN {p.name}: {e}", file=sys.stderr)
            continue
        for r in data:
            yield r


if not FAMILY_DIR.exists():
    raise SystemExit(f"Missing audit families: {FAMILY_DIR}")

# PASS 1 — profile every title/family, while keeping the proven Models/Cars set.
global_df = Counter()
seed_infos = []
root_token_df = Counter()
roots = set()
source_rows = 0
for r in iter_chunks():
    source_rows += 1
    ts = record_tokens(r)
    global_df.update(ts)
    si = structural_info(r)
    if si:
        roots.add(si["root"])
        root_token_df.update(set(tokseq(si["root"])))
        seed_infos.append((r, si, ts))

seed_root_count = max(1, len(roots))
# Boilerplate is inferred from the root names themselves (e.g. repeated naming
# prefixes). Nothing semantic is hard-coded here.
root_boilerplate = {
    t for t, n in root_token_df.items()
    if n / seed_root_count >= 0.55
}

seed_term_records = Counter()
seed_term_roots = defaultdict(set)
seed_examples = defaultdict(list)
seed_records = len(seed_infos)

for r, si, all_ts in seed_infos:
    root_ts = set(tokseq(si["root"]))
    relative_after_root = si["relative"][len(si["root"]):] if si["root"] else si["relative"]
    semantic_bits = [relative_after_root, r.get("pattern", "")]
    for ex in (r.get("examples") or [])[:3]:
        semantic_bits.append(Path(str(ex)).name)
    ts = set(tokseq(" ".join(semantic_bits)))
    ts -= root_ts
    ts -= root_boilerplate
    for t in ts:
        seed_term_records[t] += 1
        seed_term_roots[t].add(si["root"])
        if len(seed_examples[t]) < 6:
            seed_examples[t].append((r.get("examples") or [r.get("pattern", "")])[0])

# Learn the vocabulary from the observed vehicle families. A term survives only
# if its distribution is significantly more concentrated in Models/Cars than in
# the whole 64k-family corpus. This avoids a hand-written lexical field.
learned = []
for t, srec in seed_term_records.items():
    groot = len(seed_term_roots[t])
    gdf = global_df.get(t, 0)
    seed_p = srec / max(1, seed_records)
    global_p = gdf / max(1, source_rows)
    lift = (seed_p + 1e-9) / (global_p + 1e-9)
    # Terms seen across several independent vehicle roots are strongest. Rare
    # terms can survive when they are extremely concentrated in the seed set.
    keep = (
        (groot >= 3 and lift >= 2.2 and global_p <= 0.10) or
        (groot >= 2 and lift >= 4.0 and global_p <= 0.05) or
        (groot >= 1 and srec >= 3 and lift >= 10.0 and gdf <= 30)
    )
    if not keep:
        continue
    score = math.log2(max(1.000001, lift)) * math.log1p(groot) * math.log1p(srec)
    learned.append({
        "term": t,
        "seedRecords": srec,
        "seedRoots": groot,
        "globalRecords": gdf,
        "lift": round(lift, 3),
        "score": round(score, 3),
        "seedExamples": seed_examples[t],
    })

learned.sort(key=lambda x: (-x["score"], -x["seedRoots"], x["term"]))
term_map = {x["term"]: x for x in learned}

# Strong terms are learned, not supplied. These are used to find similarly named
# files outside the known Models/Cars tree.
strong_terms = {
    x["term"] for x in learned
    if (x["seedRoots"] >= 3 and x["lift"] >= 3.0) or x["lift"] >= 9.0
}

# PASS 2 — re-read every title and isolate exact structural vehicle families plus
# names elsewhere whose wording matches the learned signatures.
selected = []
selected_bundles = set()
outside_count = 0
exact_count = 0

for r in iter_chunks():
    si = structural_info(r)
    ts = record_tokens(r)
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
        # Names outside Cars need either two independently learned signatures or
        # one exceptionally concentrated signature. This limits false positives.
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
        } for m in sorted(matches, key=lambda x: -x["score"])[:10])

    logical = list(dict.fromkeys(r.get("logicalNames") or []))
    selected_bundles.update(logical)
    selected.append({
        "scope": scope,
        "confidence": confidence,
        "score": round(score, 3),
        "parent": r.get("parent", ""),
        "pattern": r.get("pattern", ""),
        "ext": r.get("ext", ""),
        "count": r.get("count", 0),
        "examples": r.get("examples") or [],
        "logicalNames": logical,
        "evidenceFiles": r.get("evidenceFiles") or [],
        "reasons": reasons,
    })

selected.sort(key=lambda x: (0 if x["scope"] == "derived-outside" else 1, -x["score"], x["parent"], x["pattern"]))

manifest = {
    "version": 25,
    "method": "name-derived-no-predefined-vehicle-vocabulary",
    "source": "asset-name-audit-v24/families",
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

(OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "selected-bundles.txt").write_text("\n".join(sorted(selected_bundles)) + "\n", encoding="utf-8")
(OUT / "learned-terms.txt").write_text(
    "\n".join(
        f"{x['term']}\tseedRoots={x['seedRoots']}\tseedRecords={x['seedRecords']}\tglobal={x['globalRecords']}\tlift={x['lift']}\tscore={x['score']}"
        for x in learned
    ) + "\n",
    encoding="utf-8",
)

print("V25 name-derived vehicle audit")
print(f"sourceFamilies={source_rows}")
print(f"modelsCarsExact={exact_count} roots={len(roots)}")
print(f"learnedTerms={len(learned)} strongTerms={len(strong_terms)}")
print(f"derivedOutside={outside_count}")
print(f"selectedFamilies={len(selected)} bundles={len(selected_bundles)}")
print(f"manifest={OUT / 'manifest.json'}")
