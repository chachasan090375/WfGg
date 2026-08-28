#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — direct export of the installed STATIC table container.
# No Last War network connection. No gameplay action. No account/session data.
# Purpose: upload one small static game-data archive so the table format can be
# decoded directly, instead of iterating blind diagnostics on the phone.

PKG="com.fun.lastwar.gp"
DOWNLOADS="${HOME}/storage/downloads"
OUT="${DOWNLOADS}/WFGG_LASTWAR_STATIC_TABLE_CONTAINER_FOR_ANALYSIS.zip"
REPORT="${DOWNLOADS}/WFGG_LASTWAR_STATIC_TABLE_CONTAINER_FOR_ANALYSIS_SHA256.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-export-static-table-container.py"

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || die "python Termux absent"
command -v pm >/dev/null 2>&1 || die "commande Android pm absente"
mkdir -p "$(dirname "$PY")" "$DOWNLOADS"

mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || die "installation Last War introuvable ($PKG)"

cat > "$PY" <<'PYEOF'
import hashlib, io, os, sys, zipfile
out,report,*apks=sys.argv[1:]
chosen=None
for apk in apks:
    try:z=zipfile.ZipFile(apk)
    except Exception:continue
    for zi in z.infolist():
        if not (zi.filename.startswith("assets/table/") and zi.filename.endswith(".data")):continue
        try:b=z.read(zi)
        except Exception:continue
        if not b.startswith(b"PK"):continue
        try:
            inner=zipfile.ZipFile(io.BytesIO(b))
            names=inner.namelist()
            ok=any(n.strip('/').lower()=="lw_hero" for n in names)
            inner.close()
        except Exception:ok=False
        if ok:
            chosen=(apk,zi.filename,b,names);break
    z.close()
    if chosen:break
if not chosen:raise SystemExit("conteneur statique avec membre exact lw_hero introuvable")
apk,entry,b,names=chosen
with open(out,"wb") as f:f.write(b)
sha=hashlib.sha256(b).hexdigest()
heroish=[n for n in names if "hero" in n.lower()]
with open(report,"w",encoding="utf-8") as f:
    f.write("WfGg Last War STATIC TABLE CONTAINER EXPORT\n")
    f.write("STATIC GAME DATA ONLY · no credentials · no account/session identifiers · no network\n\n")
    f.write(f"sourceApk={os.path.basename(apk)}\nsourceEntry={entry}\n")
    f.write(f"bytes={len(b)}\nsha256={sha}\nzipMembers={len(names)}\nheroRelatedMembers={len(heroish)}\n")
    f.write("containsExactLW_Hero=true\n")
    f.write("heroMembersSample="+" | ".join(heroish[:80])+"\n")
print(f"EXPORT_OK bytes={len(b)} sha256={sha}")
print(out)
print(report)
PYEOF

python "$PY" "$OUT" "$REPORT" "${APK_PATHS[@]}"
rm -f "$PY"
chmod 600 "$OUT" "$REPORT" 2>/dev/null || true
printf '\n=== EXPORT TERMINE ===\n'
printf 'Envoie-moi ce fichier :\n%s\n' "$OUT"
printf 'Il contient uniquement les tables statiques installées du jeu.\n'
