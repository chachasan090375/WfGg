#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "frontend/lab/asset-name-audit-v24"
FAMILY_DIR = AUDIT / "families"
OUT_DIR = ROOT / "frontend/lab/vehicle-name-semantic-v25"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CAMEL_1 = re.compile(r"([a-z0-9])([A-Z])")
CAMEL_2 = re.compile(r"([A-Z]+)([A-Z][a-z])")
SPLIT = re.compile(r"[^A-Za-z0-9]+")
HEXISH = re.compile(r"^[0-9a-f]{12,}$", re.I)


def structural_vehicle_seed(parent: str) -> bool:
    """Structural anchor only: no hand-authored vehicle vocabulary list.

    The authoritative game catalog already proves that hero vehicles live under
    Models/Cars and Models/New/Cars.  We use only that hierarchy as the seed.
    """
    parts = [p.lower() for p in parent.replace("\\", "/").split("/") if p]
    for i, p in enumerate(parts):
        if p != "models":
            continue
        if i + 1 < len(parts) and parts[i + 1] == "cars":
            return True
        if i + 2 < len(parts) and parts[i + 1] == "new" and parts[i + 2] == "cars":
            return True
    return False


def tokens(text: str) -> set[str]:
    text = CAMEL_2.sub(r"\1 \2", text)
    text = CAMEL_1.sub(r"\1 \2", text)
    out = set()
    for t in SPLIT.split(text.lower()):
        if len(t) < 3 or t.isdigit() or HEXISH.match(t):
            continue
        out.add(t)
    return out


def record_tokens(r: dict) -> set[str]:
    bits = [r.get("parent", ""), r.get("pattern", "")]
    bits.extend(r.get("examples") or [])
    return tokens(" ".join(bits))


def read_all_families() -> list[dict]:
    rows = []
    for fp in sorted(FAMILY_DIR.glob("chunk-*.json")):
        with fp.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            rows.extend(data)
    return rows


def main() -> None:
    rows = read_all_families()
    if not rows:
        raise SystemExit(f"No family chunks found in {FAMILY_DIR}")

    toks_by_idx = []
    global_df = Counter()
    seed_df = Counter()
    seed_idxs = []
    nonseed_idxs = []
    seed_logicals = set()
    token_seed_examples = defaultdict(list)

    for i, r in enumerate(rows):
        ts = record_tokens(r)
        toks_by_idx.append(ts)
        global_df.update(ts)
        if structural_vehicle_seed(r.get("parent", "")):
            seed_idxs.append(i)
            seed_df.update(ts)
            for ln in r.get("logicalNames") or []:
                seed_logicals.add(ln)
            for t in ts:
                if len(token_seed_examples[t]) < 3:
                    ex = (r.get("examples") or [r.get("pattern", "")])[0]
                    token_seed_examples[t].append(ex)
        else:
            nonseed_idxs.append(i)

    total = len(rows)
    nseed = max(1, len(seed_idxs))
    nnon = max(1, len(nonseed_idxs))

    learned = {}
    for t, sdf in seed_df.items():
        gdf = global_df[t]
        non_df = max(0, gdf - sdf)
        seed_rate = sdf / nseed
        global_rate = gdf / total

        # Purely data-derived rejection of generic tokens: too common globally
        # or present in nearly every seed family. No vocabulary blacklist.
        if sdf < 2:
            continue
        if global_rate > 0.12:
            continue
        if seed_rate > 0.82:
            continue

        # Smoothed log-odds enrichment inside the structural vehicle seed.
        enrich = math.log((sdf + 0.5) / (nseed + 1.0)) - math.log((non_df + 0.5) / (nnon + 1.0))
        if enrich < 1.15:
            continue
        learned[t] = {
            "token": t,
            "seedDf": sdf,
            "globalDf": gdf,
            "seedRate": round(seed_rate, 6),
            "globalRate": round(global_rate, 6),
            "enrichment": round(enrich, 4),
            "seedExamples": token_seed_examples[t],
        }

    # Strongest evidence first. A token is not accepted because of its English/
    # French meaning; it is accepted because its frequency is enriched in the
    # known vehicle subtree.
    learned_tokens = set(learned)
    candidates = []
    outside_token_examples = defaultdict(list)

    for i, r in enumerate(rows):
        ts = toks_by_idx[i]
        is_seed = i in set(seed_idxs)
        shared_bundle = any(ln in seed_logicals for ln in (r.get("logicalNames") or []))
        hits = [learned[t] for t in ts if t in learned_tokens]
        hits.sort(key=lambda x: (-x["enrichment"], -x["seedDf"], x["token"]))

        token_score = sum(min(5.0, h["enrichment"]) for h in hits)
        strong_single = bool(hits and hits[0]["enrichment"] >= 3.2 and hits[0]["seedDf"] >= 3)
        semantic_pass = len(hits) >= 2 and token_score >= 3.0

        if not (is_seed or shared_bundle or strong_single or semantic_pass):
            continue

        score = token_score
        reasons = []
        if is_seed:
            score += 100
            reasons.append("structure Models/Cars")
        if shared_bundle and not is_seed:
            score += 55
            reasons.append("même bundle qu’une famille véhicule certaine")
        if hits:
            reasons.append("signatures apprises: " + ", ".join(h["token"] for h in hits[:8]))

        for h in hits:
            t = h["token"]
            if not is_seed and len(outside_token_examples[t]) < 3:
                outside_token_examples[t].append((r.get("examples") or [r.get("pattern", "")])[0])

        examples = r.get("examples") or []
        candidates.append({
            "score": round(score, 3),
            "tier": "core" if is_seed else ("bundle" if shared_bundle else "semantic"),
            "parent": r.get("parent", ""),
            "pattern": r.get("pattern", ""),
            "ext": r.get("ext", ""),
            "count": r.get("count", 0),
            "examples": examples[:4],
            "logicalNames": (r.get("logicalNames") or [])[:8],
            "evidenceFiles": (r.get("evidenceFiles") or [])[:8],
            "learnedHits": [h["token"] for h in hits[:12]],
            "reasons": reasons,
        })

    for t, info in learned.items():
        info["outsideExamples"] = outside_token_examples.get(t, [])

    candidates.sort(key=lambda r: (-r["score"], r["parent"].lower(), r["pattern"].lower()))
    learned_list = sorted(learned.values(), key=lambda x: (-x["enrichment"], -x["seedDf"], x["token"]))

    outside = [r for r in candidates if r["tier"] != "core"]
    unique_bundles = {ln for r in candidates for ln in r.get("logicalNames", [])}

    manifest = {
        "version": 25,
        "method": "structural-seed + learned-name-enrichment",
        "handAuthoredVehicleKeywordList": False,
        "sourceFamilyCount": len(rows),
        "structuralSeedFamilies": len(seed_idxs),
        "learnedSignatureCount": len(learned_list),
        "candidateFamilies": len(candidates),
        "outsideCarsCandidates": len(outside),
        "candidateBundles": len(unique_bundles),
        "seedRule": "directory hierarchy Models/Cars or Models/New/Cars only",
        "learnedSignatures": learned_list,
        "candidates": candidates,
    }

    out = OUT_DIR / "manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Compact human-readable shortlist for quick Termux inspection.
    txt = []
    txt.append("WfGg Last War LAB — semantic vehicle-name audit V25")
    txt.append(f"families={len(rows)} seed={len(seed_idxs)} learned={len(learned_list)} candidates={len(candidates)} outsideCars={len(outside)}")
    txt.append("NO HAND-AUTHORED VEHICLE KEYWORD LIST")
    txt.append("")
    txt.append("TOP LEARNED SIGNATURES")
    for x in learned_list[:120]:
        txt.append(f"  {x['token']:<28} enrich={x['enrichment']:<7} seedDf={x['seedDf']:<5} globalDf={x['globalDf']}")
    txt.append("")
    txt.append("TOP OUTSIDE-CARS CANDIDATES")
    for r in outside[:1000]:
        txt.append(f"[{r['score']:>7}] {r['parent']} :: {r['pattern']} {r['ext']} | {', '.join(r['learnedHits'][:8])}")
        for ex in r['examples'][:2]:
            txt.append(f"    {ex}")
    (OUT_DIR / "shortlist.txt").write_text("\n".join(txt) + "\n", encoding="utf-8")

    print(json.dumps({
        "families": len(rows),
        "seed": len(seed_idxs),
        "learned": len(learned_list),
        "candidates": len(candidates),
        "outsideCars": len(outside),
        "manifest": str(out.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
