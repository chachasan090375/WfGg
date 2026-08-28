#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 29
# OFFLINE ONLY. Builds a local graphics-kit index from the installed Last War APK/splits,
# copies directly stored image assets when present, and prepares the squad replica page.
# No Last War network connection. No gameplay automation.
# Local-only output: generated graphics are NOT committed to Git.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOWNLOADS="${HOME}/storage/downloads"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE29_GRAPHICS_KIT_V1_REDACTED.txt"
KIT_DIR="${ROOT}/frontend/lab/local-assets/lastwar-kit-v1"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase29-graphics-kit.py"

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || die "python Termux absent"
command -v pm >/dev/null 2>&1 || die "commande Android pm absente"
mkdir -p "$(dirname "$PY")" "$KIT_DIR/raw"

mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || die "installation Last War introuvable ($PKG)"
VERSION="$(dumpsys package "$PKG" 2>/dev/null | sed -n 's/^[[:space:]]*versionName=//p' | head -n1 || true)"

cat > "$PY" <<'PYEOF'
import hashlib, json, os, re, shutil, sys, time, zipfile
from collections import defaultdict

out_path,kit_dir,version,*apk_paths=sys.argv[1:]
os.makedirs(os.path.join(kit_dir,"raw"),exist_ok=True)
for name in os.listdir(os.path.join(kit_dir,"raw")):
    p=os.path.join(kit_dir,"raw",name)
    if os.path.isfile(p): os.unlink(p)

MANIFEST="assets/AssetBundles/gameres"
hero_names=["Loki","Kane","Ambolt","Gump","Elsa","Farhad","Richard","Braz","Cage","Maxwell","Monica","Murphy","Williams","Marshall","Kimberly","Stetmann","McGregor","Fiona","Swift","Schuyler","Carlie","Morrison","Lucius","Adam"]
hero_ids={"Loki":30002,"Kane":30003,"Ambolt":30004,"Gump":30005,"Elsa":40007,"Farhad":40008,"Richard":40009,"Braz":40013,"Cage":40015,"Maxwell":40016,"Monica":40020,"Murphy":50006,"Williams":50007,"Marshall":50008,"Kimberly":50009,"Stetmann":50010,"McGregor":50013,"Fiona":50014,"Swift":50015,"Schuyler":50018,"Carlie":50019,"Morrison":50020,"Lucius":50021,"Adam":50022}
aliases={
 "McGregor":["mcgregor","mc_gregor"],"Stetmann":["stetmann","stettmann"],"Carlie":["carlie","carli"],
 "Kimberly":["kimberly","kim"],"Williams":["williams","william"],"Schuyler":["schuyler"],"Morrison":["morrison"],
 "Lucius":["lucius"],"Marshall":["marshall"],"Murphy":["murphy"],"Monica":["monica"],"Farhad":["farhad"],"Maxwell":["maxwell"],
 "Richard":["richard"],"Braz":["braz"],"Cage":["cage"],"Elsa":["elsa"],"Fiona":["fiona"],"Swift":["swift"],"Adam":["adam"],
 "Loki":["loki"],"Kane":["kane"],"Ambolt":["ambolt"],"Gump":["gump"]
}

categories={
 "heroPortraits": re.compile(r"heroicons(?:big|small)|lw_herobody|hero_icon_|halfbody|headicon|herohead",re.I),
 "drone": re.compile(r"(?:uav|drone|tacticalchip|skillchip|item_uav_equip)",re.I),
 "dominator": re.compile(r"(?:dominator|gorilla|cockatrice|hawk)",re.I),
 "equipment": re.compile(r"(?:lw_equip|equip_icon|equipment|unique_weapon|weapon_icon)",re.I),
 "uiFrames": re.compile(r"(?:hero.*frame|quality.*frame|rarity|star_icon|rank_icon|hero.*bg|formation|squad)",re.I),
}

manifest_raw=None; manifest_source=None
for apk in apk_paths:
    try:
        with zipfile.ZipFile(apk) as z:
            if MANIFEST in z.namelist():
                manifest_raw=z.read(MANIFEST); manifest_source=os.path.basename(apk)+":"+MANIFEST; break
    except Exception: pass
if manifest_raw is None: raise SystemExit("manifest gameres introuvable")
text=manifest_raw.decode("utf-8","ignore")
lines=[x.strip() for x in text.splitlines() if x.strip()]

path_rx=re.compile(r"(?i)(?:Assets|assets)/[A-Za-z0-9_./()\- ]+\.(?:png|jpg|jpeg|tga|psd|mat|prefab|controller|anim|asset|bytes)")
bundle_rx=re.compile(r"[A-Za-z0-9_./-]+\.bundle",re.I)
cat_paths=defaultdict(list); bundle_paths=defaultdict(list)
all_candidates=[]
for line in lines:
    paths=path_rx.findall(line)
    bundles=bundle_rx.findall(line)
    for cat,rx in categories.items():
        if rx.search(line):
            for p in paths:
                if p not in cat_paths[cat]: cat_paths[cat].append(p)
            for b in bundles:
                if b not in bundle_paths[cat]: bundle_paths[cat].append(b)
            if len(paths)==0 and len(bundles)==0 and len(cat_paths[cat])<300:
                # Retain a compact semantic record when no explicit path was parseable.
                s=re.sub(r"\s+"," ",line)[:600]
                if s not in all_candidates: all_candidates.append(s)

hero_candidates={}
combined_paths=cat_paths["heroPortraits"]+bundle_paths["heroPortraits"]
for name in hero_names:
    toks=aliases.get(name,[name.lower()])
    vals=[p for p in combined_paths if any(t in p.lower() for t in toks)]
    hero_candidates[name]={"heroId":hero_ids[name],"paths":vals[:80]}

# Copy directly packaged raster images when they exist as ZIP entries. Most Unity
# sprites live in bundles, but every direct PNG/JPG/TGA gives us an immediately usable asset.
direct=[]
direct_rx=re.compile(r"(?i)(hero|uav|drone|dominator|gorilla|cockatrice|equip|weapon|formation|squad|rank|star|quality).+\.(png|jpg|jpeg|webp)$")
for apk in apk_paths:
    try:z=zipfile.ZipFile(apk)
    except Exception:continue
    for zi in z.infolist():
        n=zi.filename
        if zi.file_size<=0 or zi.file_size>8*1024*1024: continue
        if not direct_rx.search(n): continue
        try:data=z.read(zi)
        except Exception:continue
        ext=os.path.splitext(n)[1].lower() or ".bin"
        stem=re.sub(r"[^A-Za-z0-9_.-]+","_",os.path.basename(n))[-110:]
        short=hashlib.sha1((os.path.basename(apk)+":"+n).encode()).hexdigest()[:10]
        local=f"raw/{short}_{stem}"
        with open(os.path.join(kit_dir,local),"wb") as f:f.write(data)
        direct.append({"apk":os.path.basename(apk),"sourcePath":n,"localPath":"/lab/local-assets/lastwar-kit-v1/"+local,"bytes":len(data)})
    z.close()

# Map direct files back to known heroes when filenames are explicit.
for name,obj in hero_candidates.items():
    toks=aliases.get(name,[name.lower()])
    obj["directAssets"]=[x["localPath"] for x in direct if any(t in x["sourcePath"].lower() for t in toks)][:20]

catalog={
 "format":"WFGG_LASTWAR_GRAPHICS_KIT_V1",
 "gameVersion":version or None,
 "sourceManifest":manifest_source,
 "offline":True,
 "generatedLocalEpoch":int(time.time()),
 "heroCandidates":hero_candidates,
 "categories":{k:{"paths":cat_paths[k][:1200],"bundles":bundle_paths[k][:1200]} for k in categories},
 "directAssets":direct,
 "stats":{
   "manifestLines":len(lines),
   "heroPortraitPathCandidates":len(cat_paths["heroPortraits"]),
   "heroPortraitBundleCandidates":len(bundle_paths["heroPortraits"]),
   "dronePathCandidates":len(cat_paths["drone"]),
   "dominatorPathCandidates":len(cat_paths["dominator"]),
   "equipmentPathCandidates":len(cat_paths["equipment"]),
   "uiFramePathCandidates":len(cat_paths["uiFrames"]),
   "directRasterAssets":len(direct)
 }
}
with open(os.path.join(kit_dir,"catalog.json"),"w",encoding="utf-8") as f:json.dump(catalog,f,ensure_ascii=False,indent=2)
with open(os.path.join(kit_dir,"catalog.js"),"w",encoding="utf-8") as f:
    f.write("window.WFGG_LASTWAR_GRAPHICS_KIT=")
    json.dump(catalog,f,ensure_ascii=False,separators=(",",":"))
    f.write(";\n")

with open(out_path,"w",encoding="utf-8") as o:
    o.write("WfGg Last War LAB — PHASE 29 GRAPHICS KIT V1\n")
    o.write("OFFLINE ONLY · installed static assets · local browser kit only\n\n")
    o.write(f"GAME_VERSION={version or '-'}\n")
    o.write(f"MANIFEST_SOURCE={manifest_source}\n")
    for k,v in catalog["stats"].items():o.write(f"{k}={v}\n")
    o.write(f"KIT_DIR={kit_dir}\n")
    o.write("CATALOG_JSON=frontend/lab/local-assets/lastwar-kit-v1/catalog.json\n")
    o.write("CATALOG_JS=frontend/lab/local-assets/lastwar-kit-v1/catalog.js\n")
    o.write("\nKNOWN_HERO_ASSET_COVERAGE\n")
    for name,obj in hero_candidates.items():
        o.write(f"  heroId={obj['heroId']} name={name} pathCandidates={len(obj['paths'])} directAssets={len(obj['directAssets'])}\n")
        for p in obj['paths'][:5]:o.write(f"    candidate={p}\n")
        for p in obj['directAssets'][:3]:o.write(f"    direct={p}\n")
    o.write("\nCATEGORY_SAMPLES\n")
    for cat in categories:
        o.write(f"  [{cat}]\n")
        for p in cat_paths[cat][:20]:o.write(f"    path={p}\n")
        for b in bundle_paths[cat][:12]:o.write(f"    bundle={b}\n")
    o.write("\nNEXT\n")
    o.write("  directRasterAssets>0 => witness page can already render those files.\n")
    o.write("  bundledSprites remain to decode from Unity Texture2D/SpriteAtlas; catalog paths/bundles are retained for Phase 30.\n")
    o.write("  no generated graphics are committed to Git.\n")

print(f"GRAPHICS_KIT_READY direct={len(direct)} heroPaths={len(cat_paths['heroPortraits'])} dronePaths={len(cat_paths['drone'])} output={out_path}")
PYEOF

python "$PY" "$OUT" "$KIT_DIR" "$VERSION" "${APK_PATHS[@]}"
chmod 600 "$OUT" 2>/dev/null || true
rm -f "$PY"

printf '=== PHASE 29 TERMINEE ===\n'
printf 'Aucune connexion Last War n\x27a été effectuée.\n'
printf 'Kit local : %s\n' "$KIT_DIR"
printf 'Page témoin : http://127.0.0.1:8877/lab/lastwar-squads-replica.html\n'
printf 'Fichier à partager : Téléchargements/WFGG_LASTWAR_PHASE29_GRAPHICS_KIT_V1_REDACTED.txt\n'
