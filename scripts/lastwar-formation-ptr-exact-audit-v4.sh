#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — Formation exact serialized PPtr audit V4.
# V2 proven current-APK extraction + V3 exact container lookup +
# exact loading of APK serialized file "assets/bin/Data/unity default resources".
# This closes external PPtrs such as Library/unity default resources#10101
# only when the APK contains exactly one matching entry.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/scripts/lastwar-formation-ptr-exact-audit-v2.sh"
TMP="$ROOT/scripts/.lastwar-formation-ptr-exact-audit-v4-runtime.sh"
trap 'rm -f "$TMP"' EXIT

python - "$BASE" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]); dst=Path(sys.argv[2]); s=src.read_text('utf-8')

# Keep V2 immutable on disk; route all generated outputs to V4.
s=s.replace('lastwar-formation-ptr-exact-v2', 'lastwar-formation-ptr-exact-v4')
s=s.replace('formation-ptr-exact-v2.json', 'formation-ptr-exact-v4.json')
s=s.replace('WFGG_LASTWAR_FORMATION_PTR_EXACT_V2.txt', 'WFGG_LASTWAR_FORMATION_PTR_EXACT_V4.txt')
s=s.replace('wfgg-lastwar-formation-ptr-exact-v2.py', 'wfgg-lastwar-formation-ptr-exact-v4.py')
s=s.replace('WFGG_LASTWAR_FORMATION_PPTR_EXACT_V2', 'WFGG_LASTWAR_FORMATION_PPTR_EXACT_V4')
s=s.replace('FORMATION EXACT PPtr AUDIT V2', 'FORMATION EXACT PPtr AUDIT V4')
s=s.replace('FORMATION_PTR_V2_', 'FORMATION_PTR_V4_')
s=s.replace('FORMATION_PTR_EXACT_V2_OK', 'FORMATION_PTR_EXACT_V4_OK')
s=s.replace('map exact Formation PPtr graph from live APK tables', 'close exact Formation PPtr externals from live APK resources')

# Apply the V3 exact UnityPy ContainerHelper lookup fix.
old="""container=getattr(env,'container',{}) or {}
root=container.get(target_asset)
if root is None:
    matches=[v for k,v in container.items() if str(k).lower()==target_asset.lower()]
    if len(matches)==1:root=matches[0]
if root is None:
    nearby=[str(k) for k in container if 'uiheropvpformationpanel' in str(k).lower()]
    raise SystemExit('TARGET_PREFAB_CONTAINER_ENTRY_NOT_FOUND exactPathRequired=true nearby='+repr(nearby[:20]))
"""
new="""container=getattr(env,'container',None)
if container is None:
    raise SystemExit('UNITYPY_CONTAINER_ABSENT')
try:
    items=list(container.items())
except Exception as e:
    raise SystemExit('UNITYPY_CONTAINER_ITEMS_FAILED '+type(e).__name__+':'+str(e))
root=None
try:
    root=container[target_asset]
except KeyError:
    pass
except Exception as e:
    print('FORMATION_PTR_CONTAINER_DIRECT_LOOKUP_WARNING',type(e).__name__,str(e)[:180])
def exact_path_norm(x):
    return str(x).replace('\\\\','/').strip().lower()
if root is None:
    want=exact_path_norm(target_asset)
    exact=[(str(k),v) for k,v in items if exact_path_norm(k)==want]
    if len(exact)==1:
        root=exact[0][1]
        print('FORMATION_PTR_CONTAINER_EXACT_NORMALIZED_PATH',exact[0][0])
    elif len(exact)>1:
        raise SystemExit('TARGET_PREFAB_CONTAINER_PATH_AMBIGUOUS exactNormalizedMatches='+repr([k for k,_ in exact[:20]]))
if root is None:
    nearby=[str(k) for k,_ in items if 'uiheropvpformationpanel' in str(k).lower()]
    sample=[str(k) for k,_ in items[:80]]
    report.write_text(
        'WfGg Last War — FORMATION EXACT PPtr AUDIT V4\\n\\n'
        'TARGET CONTAINER ENTRY NOT FOUND\\n'
        'exactRequired='+target_asset+'\\n'
        'containerCount='+str(len(items))+'\\n'
        'nearbyDiagnostic='+repr(nearby[:40])+'\\n'
        'sampleKeys='+repr(sample)+'\\n',
        'utf-8'
    )
    raise SystemExit('TARGET_PREFAB_CONTAINER_ENTRY_NOT_FOUND exactPathRequired=true containerCount='+str(len(items))+' nearbyDiagnostic='+repr(nearby[:20]))
"""
if old not in s:
    raise SystemExit('V4_CONTAINER_PATCH_TARGET_NOT_FOUND')
s=s.replace(old,new)

# Load the exact serialized Unity default resources from the CURRENT installed APK.
old_env="""# ---------------- exact serialized PPtr graph ----------------
env=UnityPy.load(*[str(p) for _,p in bundle_files])
"""
new_env="""# ---------------- exact serialized PPtr graph ----------------
# Resolve built-in external serialized file by exact APK entry identity only.
default_resource_entry='assets/bin/Data/unity default resources'
default_hits=[]
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            if default_resource_entry in z.namelist():
                default_hits.append((apk,default_resource_entry,z.getinfo(default_resource_entry).file_size))
    except Exception as e:
        print('FORMATION_PTR_V4_DEFAULT_RESOURCE_APK_WARNING',apk,type(e).__name__,str(e)[:160])
if len(default_hits)!=1:
    raise SystemExit('UNITY_DEFAULT_RESOURCES_EXACT_ENTRY_COUNT expected=1 actual='+str(len(default_hits))+' hits='+repr([(str(a),e,n) for a,e,n in default_hits]))
default_apk,default_entry,default_size=default_hits[0]
default_dst=local/'unity default resources'
with zipfile.ZipFile(default_apk) as z:
    default_bytes=z.read(default_entry)
if len(default_bytes)!=default_size:
    raise SystemExit('UNITY_DEFAULT_RESOURCES_SIZE_MISMATCH')
default_dst.write_bytes(default_bytes)
default_sha256=hashlib.sha256(default_bytes).hexdigest()
print('FORMATION_PTR_V4_DEFAULT_RESOURCE',default_entry,'bytes='+str(len(default_bytes)),'sha256='+default_sha256)
env=UnityPy.load(*[str(p) for _,p in bundle_files],str(default_dst))
"""
if old_env not in s:
    raise SystemExit('V4_ENV_PATCH_TARGET_NOT_FOUND')
s=s.replace(old_env,new_env)

# Preserve exact provenance in the result JSON.
old_result="""'catalogSource':{'gameres':str(gameres),'gameresSha256':hashlib.sha256(gameres.read_bytes()).hexdigest()},'dependencySelection'"""
new_result="""'catalogSource':{'gameres':str(gameres),'gameresSha256':hashlib.sha256(gameres.read_bytes()).hexdigest()},'externalSerializedResources':[{'externalPath':'Library/unity default resources','apk':str(default_apk),'entry':default_entry,'bytes':len(default_bytes),'sha256':default_sha256,'selection':'exact_apk_entry'}],'dependencySelection'"""
if old_result not in s:
    raise SystemExit('V4_RESULT_PATCH_TARGET_NOT_FOUND')
s=s.replace(old_result,new_result)

dst.write_text(s,'utf-8')
PY
chmod +x "$TMP"
exec bash "$TMP" "$@"
