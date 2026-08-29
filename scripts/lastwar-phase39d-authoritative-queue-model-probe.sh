#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAP="$ROOT/frontend/lab/lastwar-hero-authoritative-map.js"
SEED="$ROOT/frontend/lab/master-assets-v2/meta/hero-vehicle-catalog-seed-v2.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE39D_AUTHORITATIVE_QUEUE_MODEL_PROBE.txt"

mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || {
  echo "ERREUR: Last War introuvable"
  exit 1
}

python - "$MAP" "$SEED" "$REPORT" "${APKS[@]}" <<'PY'
import gzip, io, json, os, re, sys, zipfile, zlib

map_path, seed_path, report_path, *apks = sys.argv[1:]

seed = json.load(open(seed_path, encoding="utf-8"))
js = open(map_path, encoding="utf-8").read()

rx = re.compile(
    r"\{heroId:(\d+),name:'([^']+)'.*?"
    r"appearance:(\d+),queueIcon:'([^']+)',"
    r"halfIcon:(?:'([^']+)'|null)",
    re.S,
)

heroes = []
for m in rx.finditer(js):
    heroes.append({
        "heroId": int(m.group(1)),
        "name": m.group(2),
        "appearance": int(m.group(3)),
        "queueIcon": m.group(4),
        "halfIcon": m.group(5) or "",
    })

if len(heroes) != 31:
    raise SystemExit(f"ERREUR: mapping héros lu={len(heroes)}, attendu=31")

seed_by_id = {int(h["heroId"]): h for h in seed["heroes"]}

def norm(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")

def flat(s):
    return norm(s).replace("_", "")

def core(root):
    s = norm(root)
    if s.startswith("a_hero_"):
        s = s[7:]
    if "_a_hero_" in s:
        s = s.split("_a_hero_", 1)[0]

    stop = {
        "zhuanwu","zhuangwu","awaken","wzsj",
        "ur","ssr","sr","show","battle","lod","high","low"
    }

    out = []
    for p in s.split("_"):
        if p in stop or p.isdigit() or re.fullmatch(r"v\d+", p):
            break
        if p:
            out.append(p)

    return "_".join(out[:4]) or s

def roots(text):
    low = text.lower().replace("\\", "/")
    out = []

    for m in re.finditer(r"a_hero_[a-z0-9_]+", low):
        x = m.group(0)
        x = re.split(
            r"_(?:animation|animator|material|matetial|materail|mesh|"
            r"prefab|texture|camera|timeline|effect|eff)(?:_|$)",
            x, 1
        )[0]
        if len(x) >= 8:
            out.append(norm(x))

    return list(dict.fromkeys(out))

def unwrap(b):
    cur = b
    for _ in range(3):
        nxt = None
        try:
            if cur.startswith(b"\x1f\x8b"):
                nxt = gzip.decompress(cur)
            else:
                for wb in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
                    try:
                        x = zlib.decompress(cur, wb)
                        if len(x) > 32:
                            nxt = x
                            break
                    except Exception:
                        pass
        except Exception:
            pass

        if nxt is None or nxt == cur:
            break
        cur = nxt
    return cur

# --- localisation du ZIP de tables ---
container = None
source = None

for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            for zi in z.infolist():
                if not (
                    zi.filename.startswith("assets/table/")
                    and zi.filename.endswith(".data")
                ):
                    continue

                try:
                    data = z.read(zi)
                except Exception:
                    continue

                if not data.startswith(b"PK\x03\x04"):
                    continue

                try:
                    inner = zipfile.ZipFile(io.BytesIO(data))
                    names = [n.strip("/").lower() for n in inner.namelist()]
                    inner.close()
                except Exception:
                    continue

                if "lw_hero_appearance" in names:
                    container = data
                    source = f"{os.path.basename(apk)}:{zi.filename}"
                    break

            if container:
                break
    except Exception:
        pass

if not container:
    raise SystemExit("ERREUR: conteneur HeroAppearance introuvable")

inner = zipfile.ZipFile(io.BytesIO(container))
lookup = {n.strip("/").lower(): n for n in inner.namelist()}

wanted = [
    "lw_hero_appearance",
    "lw_hero_appearance_b",
    "lw_hero_appearance_opt",
]

members = []

PRINT = re.compile(rb"[ -~]{3,}")

for name in wanted:
    if name not in lookup:
        continue

    real = lookup[name]
    raw = inner.read(real)
    blob = unwrap(raw)

    strings = [
        (m.start(), m.group().decode("ascii", "ignore"))
        for m in PRINT.finditer(blob)
    ]

    vehicle_strings = []
    for off, text in strings:
        if "a_hero_" not in text.lower():
            continue
        for r in roots(text):
            vehicle_strings.append((off, r, text))

    members.append({
        "name": real,
        "raw": raw,
        "blob": blob,
        "strings": strings,
        "vehicles": vehicle_strings,
    })

inner.close()

known = {}
for h in heroes:
    s = seed_by_id.get(h["heroId"], {})
    sel = s.get("selected") or {}
    if (
        s.get("selectionConfidence") in ("medium", "high")
        and sel.get("vehicleRoot")
    ):
        known[h["heroId"]] = norm(sel["vehicleRoot"])

def positions(buf, pattern):
    out = []
    p = 0
    while len(out) < 100:
        p = buf.find(pattern, p)
        if p < 0:
            break
        out.append(p)
        p += max(1, len(pattern))
    return out

results = []

for h in heroes:
    aliases = [
        h["queueIcon"],
        h["halfIcon"],
        h["name"],
        re.sub(r"^hero_icon_", "", h["queueIcon"], flags=re.I),
        re.sub(r"^hero_icon_", "", h["halfIcon"], flags=re.I),
    ]
    aliases = list(dict.fromkeys(norm(x) for x in aliases if x))

    anchors = []

    for mem in members:
        low = mem["blob"].lower()

        for alias in aliases:
            pat = alias.encode()
            if len(pat) < 3:
                continue

            for p in positions(low, pat):
                anchors.append((mem["name"], alias, p))

    candidates = {}

    for mem in members:
        same_anchors = [a for a in anchors if a[0] == mem["name"]]
        if not same_anchors:
            continue

        for moff, root, text in mem["vehicles"]:
            nearest = min(
                same_anchors,
                key=lambda a: abs(moff - a[2])
            )
            dist = abs(moff - nearest[2])

            if dist > 65536:
                continue

            if dist <= 256:
                score = 15000
            elif dist <= 768:
                score = 11000
            elif dist <= 2048:
                score = 7500
            elif dist <= 8192:
                score = 4200
            elif dist <= 32768:
                score = 1800
            else:
                score = 600

            row = candidates.setdefault(root, {
                "root": root,
                "score": 0,
                "minDist": dist,
                "hits": [],
            })

            row["score"] += score
            row["minDist"] = min(row["minDist"], dist)
            row["hits"].append((
                mem["name"],
                nearest[1],
                nearest[2],
                moff,
                dist,
                text[:250],
            ))

    cand = sorted(
        candidates.values(),
        key=lambda x: (x["score"], -x["minDist"]),
        reverse=True
    )

    top = cand[0] if cand else None
    old = known.get(h["heroId"])

    match = None
    if old and top:
        match = (
            flat(core(old)) == flat(core(top["root"]))
            or flat(core(old)) in flat(top["root"])
            or flat(core(top["root"])) in flat(old)
        )

    results.append({
        "hero": h,
        "anchors": anchors,
        "known": old,
        "match": match,
        "candidates": cand[:8],
    })

cal = [r for r in results if r["known"] and r["candidates"]]
matches = [r for r in cal if r["match"] is True]
rate = len(matches) / len(cal) if cal else 0

targets = {30005, 50014, 50019, 50025}

with open(report_path, "w", encoding="utf-8") as o:
    o.write("WfGg Last War LAB — PHASE 39D AUTHORITATIVE QUEUE MODEL PROBE\n")
    o.write("OFFLINE ONLY · HeroAppearance / queue_model_path\n")
    o.write(f"source={source}\n")
    o.write(
        f"calibration={len(matches)}/{len(cal)} "
        f"rate={rate:.3f}\n\n"
    )

    for mem in members:
        b = mem["blob"]
        o.write(f"MEMBER {mem['name']}\n")
        o.write(f"  bytes={len(b)}\n")
        o.write(f"  first32={b[:32].hex()}\n")
        o.write(f"  lua53Signature={b.find(b'\\x1bLua')}\n")
        o.write(
            f"  queue_model_path="
            f"{b.lower().count(b'queue_model_path')}\n"
        )
        o.write(
            f"  queue_icon_path="
            f"{b.lower().count(b'queue_icon_path')}\n"
        )
        o.write(
            f"  A_Hero_strings={len(mem['vehicles'])}\n\n"
        )

    for r in results:
        h = r["hero"]
        tag = "TARGET" if h["heroId"] in targets else "CAL"

        o.write(
            f"{tag} HERO {h['heroId']} {h['name']} "
            f"appearance={h['appearance']} "
            f"queueIcon={h['queueIcon']} "
            f"anchorHits={len(r['anchors'])} "
            f"known={r['known'] or '-'} "
            f"calibrationMatch={r['match']}\n"
        )

        for c in r["candidates"][:5]:
            o.write(
                f"  CAND root={c['root']} "
                f"score={c['score']} "
                f"minDist={c['minDist']} "
                f"hits={len(c['hits'])}\n"
            )

            for hit in sorted(c["hits"], key=lambda x: x[4])[:2]:
                o.write(
                    f"    HIT member={hit[0]} "
                    f"anchor={hit[1]} "
                    f"aOff={hit[2]} "
                    f"modelOff={hit[3]} "
                    f"dist={hit[4]}\n"
                )
                o.write(f"    TEXT {hit[5]}\n")

        o.write("\n")

    o.write("TARGET_SUMMARY\n")
    for r in results:
        h = r["hero"]
        if h["heroId"] not in targets:
            continue
        top = r["candidates"][0]["root"] if r["candidates"] else "-"
        dist = r["candidates"][0]["minDist"] if r["candidates"] else -1
        o.write(
            f"  {h['heroId']} {h['name']} "
            f"top={top} minDist={dist}\n"
        )

print(
    "PHASE39D_OK",
    f"members={len(members)}",
    f"calibration={len(matches)}/{len(cal)}",
    f"rate={rate:.3f}",
)
PY

git add scripts/lastwar-phase39d-authoritative-queue-model-probe.sh
git commit -m "lab: add authoritative HeroAppearance queue-model probe" || true
git push origin portal-auth-lastwar-lab-v1

echo
echo "=== PHASE 39D TERMINEE ==="
echo "Fichier à m'envoyer :"
echo "$REPORT"
echo "Ne lance pas encore la page Escouades."
