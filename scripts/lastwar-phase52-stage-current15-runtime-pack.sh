#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 52
# STAGE EXACT CURRENT-15 WEB RUNTIME PACK
# CODE ONLY · OFFLINE ONLY · no generated geometry · no generated motion.
#
# Inputs already validated:
#  - Phase49B exact OBJ/PNG export
#  - Phase50 exact rig topology
#  - Phase51C exact decoded idle/show_idle transforms
#
# This phase does not render yet. It assembles one deterministic local runtime
# package per hero and verifies that the ordinary idle clip is fully resolved.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
P49="$ROOT/frontend/lab/master-assets-v2/meta/current15-web-export-v2.json"
P50="$ROOT/frontend/lab/master-assets-v2/meta/current15-rig-idle-structure-v1.json"
P51="$ROOT/frontend/lab/master-assets-v2/meta/current15-idle-keyframes-v3.json"
WEB49="$ROOT/frontend/lab/local_assets/lastwar-current15-web-v2"
RIG50="$ROOT/frontend/lab/local_assets/lastwar-current15-rig-idle-v1"
ANIM51="$ROOT/frontend/lab/local_assets/lastwar-current15-animation-v3"
OUT="$ROOT/frontend/lab/local_assets/lastwar-current15-runtime-v1"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/current15-runtime-pack-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE52_CURRENT15_RUNTIME_PACK.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-phase52-runtime-pack.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P49" ]] || fail "Phase49B manifest absent"
[[ -s "$P50" ]] || fail "Phase50 manifest absent"
[[ -s "$P51" ]] || fail "Phase51C manifest absent"
[[ -d "$WEB49" ]] || fail "Phase49B assets locaux absents"
[[ -d "$RIG50" ]] || fail "Phase50 assets locaux absents"
[[ -d "$ANIM51" ]] || fail "Phase51C animations locales absentes"

rm -rf "$OUT"
mkdir -p "$OUT" "$(dirname "$MANIFEST")" "$(dirname "$REPORT")" "$(dirname "$PY")"

cat > "$PY" <<'PY'
from pathlib import Path
import json, shutil, sys, hashlib

p49,p50,p51,web49,rig50,anim51,out,manifest,report=map(Path,sys.argv[1:])
j49=json.loads(p49.read_text(encoding='utf-8'))
j50=json.loads(p50.read_text(encoding='utf-8'))
j51=json.loads(p51.read_text(encoding='utf-8'))

h49={int(x['heroId']):x for x in j49.get('heroes',[])}
h50={int(x['heroId']):x for x in j50.get('heroes',[])}
h51={int(x['heroId']):x for x in j51.get('heroes',[])}
ids=sorted(set(h49)&set(h50)&set(h51))
if len(ids)!=15: raise SystemExit(f'expected 15 common heroes, got {len(ids)}')

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def cp(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    return {'file':str(dst.relative_to(out)),'bytes':dst.stat().st_size,'sha256':sha(dst)}

rows=[]
for n,hid in enumerate(ids,1):
    a,b,c=h49[hid],h50[hid],h51[hid]
    name=a.get('name') or str(hid);hd=out/str(hid);hd.mkdir(parents=True,exist_ok=True)
    print(f'PHASE52_HERO {n}/15 id={hid} name={name}',flush=True)
    row={'heroId':hid,'name':name,'queueModelPath':a.get('queueModelPath'),'rendererMode':c.get('rendererMode'),'meshFiles':[],'textureFiles':[],'rigFiles':[],'animationFiles':[],'idleFullyResolved':False,'ready':False,'errors':[]}
    try:
        srcw=web49/str(hid)
        for item in a.get('meshes',[]):
            if not item.get('exported'): continue
            s=srcw/item['file']; d=hd/item['file']; row['meshFiles'].append(cp(s,d))
        for item in a.get('textures',[]):
            if not item.get('exported'): continue
            s=srcw/item['file']; d=hd/item['file']; row['textureFiles'].append(cp(s,d))

        sr=rig50/str(hid)
        if (sr/'rig.json.gz').is_file(): row['rigFiles'].append(cp(sr/'rig.json.gz',hd/'rig.json.gz'))
        for sm in b.get('skinMeshes',[]):
            fn=sm.get('file')
            if fn and (sr/fn).is_file(): row['rigFiles'].append(cp(sr/fn,hd/'skin'/Path(fn).name))

        idle=[x for x in c.get('clips',[]) if x.get('kind')=='idle' and x.get('decoded')]
        pres=[x for x in c.get('clips',[]) if x.get('kind')=='presentationIdle' and x.get('decoded')]
        if len(idle)!=1: raise ValueError(f'idle exact count={len(idle)}')
        ic=idle[0]
        row['idleFullyResolved']=int(ic.get('resolvedTransformBindings',0))==int(ic.get('transformBindings',-1)) and int(ic.get('transformBindings',0))>0
        if not row['idleFullyResolved']: raise ValueError(f'idle unresolved {ic.get("resolvedTransformBindings")}/{ic.get("transformBindings")}')
        sa=anim51/str(hid)
        row['animationFiles'].append({'kind':'idle','clipName':ic.get('name'),**cp(sa/ic['file'],hd/'animation'/'idle.json.gz')})
        if pres:
            pc=pres[0]
            row['animationFiles'].append({'kind':'presentationIdle','clipName':pc.get('name'),'resolvedBindings':pc.get('resolvedTransformBindings'),'transformBindings':pc.get('transformBindings'),**cp(sa/pc['file'],hd/'animation'/'presentation-idle.json.gz')})

        hero_index={
          'format':'WFGG_LASTWAR_HERO_RUNTIME_V1','heroId':hid,'name':name,
          'queueModelPath':a.get('queueModelPath'),'rendererMode':c.get('rendererMode'),
          'defaultFormationClip':'idle','idleFullyResolved':row['idleFullyResolved'],
          'meshFiles':[x['file'].split(f'{hid}/',1)[-1] for x in row['meshFiles']],
          'textureFiles':[x['file'].split(f'{hid}/',1)[-1] for x in row['textureFiles']],
          'rigFiles':[x['file'].split(f'{hid}/',1)[-1] for x in row['rigFiles']],
          'animationFiles':[{k:v for k,v in x.items() if k not in ('bytes','sha256')} for x in row['animationFiles']],
        }
        (hd/'runtime.json').write_text(json.dumps(hero_index,ensure_ascii=False,indent=2),encoding='utf-8')
        row['runtimeJson']=str((hd/'runtime.json').relative_to(out));row['ready']=bool(row['meshFiles'] and row['textureFiles'] and row['animationFiles'] and row['idleFullyResolved'])
    except Exception as e: row['errors'].append(repr(e))
    rows.append(row)
    print('PHASE52_HERO_DONE',hid,f"ready={row['ready']}",f"meshes={len(row['meshFiles'])}",f"textures={len(row['textureFiles'])}",f"rig={len(row['rigFiles'])}",f"anim={len(row['animationFiles'])}",flush=True)

summary={
 'format':'WFGG_LASTWAR_CURRENT15_RUNTIME_PACK_V1','networkUsed':False,'heroCount':15,
 'readyCount':sum(x['ready'] for x in rows),'idleFullyResolvedCount':sum(x['idleFullyResolved'] for x in rows),
 'meshFileCount':sum(len(x['meshFiles']) for x in rows),'textureFileCount':sum(len(x['textureFiles']) for x in rows),
 'rigFileCount':sum(len(x['rigFiles']) for x in rows),'animationFileCount':sum(len(x['animationFiles']) for x in rows),
 'heroes':[{k:v for k,v in x.items() if k not in ('meshFiles','textureFiles','rigFiles','animationFiles')} for x in rows],
 'guardrails':{'ordinaryIdleDefault':True,'noGeneratedGeometry':True,'noGeneratedMotion':True,'noAnimationSubstitution':True,'noLastWarNetwork':True}
}
manifest.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['WfGg Last War LAB — PHASE 52 CURRENT15 RUNTIME PACK',f"heroes=15 ready={summary['readyCount']}/15 idleFullyResolved={summary['idleFullyResolvedCount']}/15",f"meshes={summary['meshFileCount']} textures={summary['textureFileCount']} rigFiles={summary['rigFileCount']} animationFiles={summary['animationFileCount']}",'']
for x in rows: lines.append(f"HERO {x['heroId']} {x['name']} ready={x['ready']} mode={x['rendererMode']} idleFullyResolved={x['idleFullyResolved']} errors={x['errors']}")
lines += ['','GUARDRAILS','  ordinary_idle_default=true','  no_generated_geometry=true','  no_generated_motion=true','  no_animation_substitution=true','  no_lastwar_network=true']
report.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE52_OK',f"ready={summary['readyCount']}/15",f"idleFullyResolved={summary['idleFullyResolvedCount']}/15",f"meshes={summary['meshFileCount']}",f"textures={summary['textureFileCount']}",flush=True)
print('PHASE52_REPORT',report,flush=True)
PY

python "$PY" "$P49" "$P50" "$P51" "$WEB49" "$RIG50" "$ANIM51" "$OUT" "$MANIFEST" "$REPORT"

git add "$MANIFEST"
if ! git diff --cached --quiet; then
  git commit -m "lab: record exact current15 animated runtime pack"
  git push origin "$BRANCH"
fi
printf 'PHASE52_DONE report=%s\n' "$REPORT"
