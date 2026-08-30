#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# V3 wrapper: keeps the proven V2 extraction/PPtr logic and patches only
# UnityPy ContainerHelper lookup semantics. Runtime script stays under repo/scripts
# so BASH_SOURCE-based ROOT continues to resolve correctly.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/scripts/lastwar-formation-ptr-exact-audit-v2.sh"
TMP="$ROOT/scripts/.lastwar-formation-ptr-exact-audit-v3-runtime.sh"
trap 'rm -f "$TMP"' EXIT

python - "$BASE" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]); dst=Path(sys.argv[2]); s=src.read_text('utf-8')
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

# UnityPy ContainerHelper.get() raises KeyError in this installed version.
# Use exact __getitem__ first, then a slash/case-normalized EXACT full-path comparison.
# No basename, substring, score or nearest-name substitution is allowed.
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
    # Diagnostic only. These values are NEVER selected as target.
    nearby=[str(k) for k,_ in items if 'uiheropvpformationpanel' in str(k).lower()]
    sample=[str(k) for k,_ in items[:80]]
    report.write_text(
        'WfGg Last War — FORMATION EXACT PPtr AUDIT V3\\n\\n'
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
    raise SystemExit('V3_PATCH_TARGET_NOT_FOUND')
dst.write_text(s.replace(old,new),'utf-8')
PY
chmod +x "$TMP"
exec bash "$TMP" "$@"
