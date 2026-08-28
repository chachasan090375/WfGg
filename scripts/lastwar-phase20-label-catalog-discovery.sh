#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 20
# OFFLINE ONLY. Resolves numeric catalogue IDs toward their real in-game labels
# by inspecting the locally installed Last War APK/split APK/asset-pack files.
# No Last War connection, no account credentials, no private UUID/GUID/UID.

PKG="com.fun.lastwar.gp"
DOWNLOADS="${HOME}/storage/downloads"
V3="${DOWNLOADS}/WFGG_LASTWAR_PHASE19_NORMALIZED_MODULE_DATA.json"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE20_LABEL_CATALOG_DISCOVERY_REDACTED.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase20-label-catalog.py"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

[[ -s "$V3" ]] || die "Phase 19 absente: $V3"
command -v python >/dev/null 2>&1 || die "python Termux absent"
command -v pm >/dev/null 2>&1 || die "commande Android pm absente"
mkdir -p "$(dirname "$PY")"

mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || die "installation Last War introuvable ($PKG)"

VERSION="$(dumpsys package "$PKG" 2>/dev/null | sed -n 's/^[[:space:]]*versionName=//p' | head -n1 || true)"

say "=== WfGg Last War LAB · PHASE 20 ==="
say "Mode: OFFLINE / résolution des vrais libellés catalogue"
say "Package: $PKG${VERSION:+ · version $VERSION}"
say "APK/splits détectés: ${#APK_PATHS[@]}"

cat > "$PY" <<'PYEOF'
import json, os, re, sys, zipfile
from collections import defaultdict

if len(sys.argv) < 4:
    raise SystemExit("usage: resolver <v3.json> <out.txt> <apk...>")
v3_path, out_path, *apk_paths = sys.argv[1:]
with open(v3_path, "r", encoding="utf-8") as f:
    d = json.load(f)

ids = defaultdict(set)
def add(cat, v):
    if isinstance(v, bool) or v is None: return
    try: n = int(v)
    except Exception: return
    if n: ids[cat].add(n)

for h in d.get("heroes", []): add("heroId", h.get("heroId"))
for f in d.get("armyFormations", []) + d.get("formationTemplates", []):
    for x in f.get("heroIds", []): add("heroId", x)
for e in d.get("heroEquipment", []): add("heroEquipmentCfgId", e.get("cfgId"))
for e in d.get("generalEquipment", []): add("droneComponentCfgId", e.get("cfgId"))
for e in d.get("drone", {}).get("components", []): add("droneComponentCfgId", e.get("cfgId"))
add("droneSkillId", d.get("drone", {}).get("skillId"))
for g in d.get("droneChipGroups", []):
    for c in g.get("chips", []): add("droneChipCfgId", c.get("cfgId"))
for o in d.get("overlords", []): add("dominatorId", o.get("dominatorId"))
for w in d.get("weapons", []): add("weaponSkillId", w.get("skill"))

all_targets = {}
for cat, vals in ids.items():
    for n in vals: all_targets[str(n)] = cat

# Helpful known public hero labels. These are NOT used to guess ID mappings;
# they only improve context when the same static asset contains both ID and name.
known_hero_names = [
    "Adam","Ambolt","Braz","Cage","Carlie","DVA","Elsa","Farhad","Fiona","Gump",
    "Kane","Kimberly","Loki","Lucius","Marshall","Mason","McGregor","Maxwell","Monica",
    "Morrison","Murphy","Richard","Sarah","Scarlett","Scarlet","Schuyler","Stetmann",
    "Swift","Tesla","Venom","Violet","Williams"
]

interesting_name = re.compile(r"(hero|equip|weapon|drone|chip|dominator|overlord|local|lang|i18n|text|config|table|data|lua|csv)", re.I)
interesting_ext = (".json",".txt",".csv",".xml",".lua",".bytes",".asset",".assets",".bundle",".unity3d",".dat",".bin",".resS")
printable_re = re.compile(rb"[\x20-\x7e]{4,}")

hits = defaultdict(list)
entry_summaries = []
large_candidates = []
scanned_entries = 0
scanned_bytes = 0
MAX_ENTRY = 48 * 1024 * 1024
MAX_TOTAL = 900 * 1024 * 1024

for apk_index, apk in enumerate(apk_paths, 1):
    apk_label = os.path.basename(apk) or f"apk{apk_index}"
    try:
        z = zipfile.ZipFile(apk)
    except Exception as e:
        entry_summaries.append((apk_label, "<APK unreadable>", 0, str(e)[:120]))
        continue
    infos = z.infolist()
    for info in infos:
        name = info.filename
        lname = name.lower()
        candidate = interesting_name.search(name) or lname.endswith(interesting_ext) or lname.startswith("assets/")
        if not candidate: continue
        if info.file_size > MAX_ENTRY:
            if interesting_name.search(name) or lname.endswith((".bundle",".assets",".unity3d",".bytes")):
                large_candidates.append((apk_label, name, info.file_size))
            continue
        if scanned_bytes + info.file_size > MAX_TOTAL: continue
        try:
            raw = z.read(info)
        except Exception:
            continue
        scanned_entries += 1
        scanned_bytes += len(raw)
        present = [t for t in all_targets if t.encode() in raw]
        if not present: continue
        strings = [m.group().decode("ascii", "ignore") for m in printable_re.finditer(raw)]
        # Preserve only small printable neighborhoods around strings containing IDs.
        local_hits = 0
        for i, s in enumerate(strings):
            matched = [t for t in present if t in s]
            if not matched: continue
            lo, hi = max(0, i-4), min(len(strings), i+5)
            ctx = " | ".join(strings[lo:hi])
            ctx = re.sub(r"\s+", " ", ctx)[:900]
            nearby_names = sorted({n for n in known_hero_names if n.lower() in ctx.lower()})
            for t in matched:
                key = (all_targets[t], int(t))
                if len(hits[key]) < 4:
                    hits[key].append((apk_label, name, ctx, nearby_names))
            local_hits += 1
            if local_hits >= 40: break
        entry_summaries.append((apk_label, name, info.file_size, f"targetIds={','.join(present[:20])}"))
    z.close()

with open(out_path, "w", encoding="utf-8") as out:
    out.write("WfGg Last War LAB — PHASE 20 LABEL CATALOG DISCOVERY\n")
    out.write("OFFLINE ONLY · installed game assets only · private account identifiers suppressed\n\n")
    out.write(f"TARGET_CATEGORIES={len(ids)} TARGET_IDS={len(all_targets)}\n")
    out.write(f"SCANNED_ENTRIES={scanned_entries} SCANNED_BYTES={scanned_bytes}\n")
    for cat in sorted(ids):
        out.write(f"TARGET {cat} count={len(ids[cat])} ids={','.join(map(str,sorted(ids[cat])))}\n")

    out.write("\nID_CONTEXT_CANDIDATES\n")
    unresolved = []
    for cat in sorted(ids):
        for n in sorted(ids[cat]):
            rows = hits.get((cat,n), [])
            out.write(f"\n[{cat}] id={n} hits={len(rows)}\n")
            if not rows:
                unresolved.append((cat,n))
                out.write("  (aucun contexte direct dans les entrées scannées)\n")
                continue
            for apk_label, entry, ctx, names in rows:
                out.write(f"  apk={apk_label} entry={entry}\n")
                if names: out.write(f"  nearbyKnownHeroNames={','.join(names)}\n")
                out.write(f"  context={ctx}\n")

    out.write("\nCANDIDATE_ENTRIES_WITH_TARGET_IDS\n")
    for apk_label, name, size, note in entry_summaries[:250]:
        if "targetIds=" in note:
            out.write(f"  apk={apk_label} size={size} entry={name} {note}\n")

    out.write("\nLARGE_ASSET_CANDIDATES_NOT_DECOMPRESSED\n")
    for apk_label, name, size in large_candidates[:100]:
        out.write(f"  apk={apk_label} size={size} entry={name}\n")

    out.write("\nSUMMARY\n")
    resolved = sum(1 for cat in ids for n in ids[cat] if hits.get((cat,n)))
    out.write(f"  idsWithDirectAssetContext={resolved}\n")
    out.write(f"  idsWithoutDirectAssetContext={len(unresolved)}\n")
    out.write("  guardrail=no_label_is_accepted_from_name_proximity_alone; exact mappings_require_same_record_or_static_catalog evidence\n")
    out.write("  next=inspect_matching_catalog/TextAsset records; if labels live in large Unity bundles, extract only those candidate bundles offline\n")

print(f"TARGET_IDS={len(all_targets)} RESOLVED_CONTEXT={sum(1 for k in hits if hits[k])} OUTPUT={out_path}")
PYEOF

python "$PY" "$V3" "$OUT" "${APK_PATHS[@]}"
chmod 600 "$OUT"
rm -f "$PY"

say "=== PHASE 20 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE20_LABEL_CATALOG_DISCOVERY_REDACTED.txt"
