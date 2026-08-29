#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 53C
# NULL PPtr GUARD FOR EXACT OBJECT-KEY SCENE LINKS
# CODE ONLY · OFFLINE ONLY · no fuzzy matching · no generated assets.
#
# Phase53B introduced the correct identity model (assets_file + pathId) but its
# helper functions could touch .reader/.read() on Unity null PPtrs (m_PathID=0).
# UnityPy raises on those by design. This wrapper patches only that dereference
# guard and keeps the full Phase53B binding logic unchanged.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
BASE="$ROOT/scripts/lastwar-phase53b-build-exact-objectkey-scene-links.sh"
TMP="$ROOT/scripts/.lastwar-phase53c-generated.sh"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$BASE" ]] || fail "Phase53B absente: $BASE"

python - "$BASE" "$TMP" <<'PY'
from pathlib import Path
import re, sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')

# Keep Phase53B outputs intact.
repls=[
 ('PHASE 53B','PHASE 53C'),
 ('PHASE53B','PHASE53C'),
 ('lastwar-current15-runtime-v3-scene','lastwar-current15-runtime-v4-scene'),
 ('current15-runtime-scene-links-v2.json','current15-runtime-scene-links-v3.json'),
 ('WFGG_LASTWAR_PHASE53B_CURRENT15_EXACT_OBJECTKEY_SCENE_LINKS.txt','WFGG_LASTWAR_PHASE53C_CURRENT15_EXACT_OBJECTKEY_SCENE_LINKS.txt'),
 ('wfgg-phase53b-objectkey-scene-links.py','wfgg-phase53c-null-pptr-objectkey.py'),
]
for a,b in repls: src=src.replace(a,b)

old_pid="""def pid_raw(x):
    if x is None:return None
    for y in (x,getattr(x,'reader',None),getattr(x,'object_reader',None)):
        if y is None:continue
        for a in ('path_id','m_PathID'):
            try:
                v=getattr(y,a,None)
                if v is not None:return int(v)
            except:pass
    return None
"""
new_pid="""def pid_raw(x):
    if x is None:return None
    # IMPORTANT: inspect the pointer's own m_PathID before touching .reader.
    # UnityPy deliberately raises when resolving a null PPtr (m_PathID == 0).
    for a in ('path_id','m_PathID'):
        try:
            v=getattr(x,a,None)
            if v is not None:return int(v)
        except Exception:pass
    for rel in ('reader','object_reader'):
        try:y=getattr(x,rel,None)
        except Exception:y=None
        if y is None:continue
        for a in ('path_id','m_PathID'):
            try:
                v=getattr(y,a,None)
                if v is not None:return int(v)
            except Exception:pass
    return None
"""
if old_pid not in src: raise SystemExit('Phase53C patch failed: pid_raw block not found')
src=src.replace(old_pid,new_pid,1)

old_assets="""def assets_name_from_reader(r):
    if r is None:return ''
    for y in (r,getattr(r,'reader',None),getattr(r,'object_reader',None)):
        if y is None:continue
        for a in ('assets_file','assetsfile'):
            try:
                af=getattr(y,a,None)
                if af is not None:
                    n=str(getattr(af,'name','') or getattr(af,'path','') or '')
                    if n:return n
            except:pass
    return ''
"""
new_assets="""def assets_name_from_reader(r):
    if r is None:return ''
    ys=[r]
    for rel in ('reader','object_reader'):
        try:y=getattr(r,rel,None)
        except Exception:y=None
        if y is not None:ys.append(y)
    for y in ys:
        for a in ('assets_file','assetsfile'):
            try:
                af=getattr(y,a,None)
                if af is not None:
                    n=str(getattr(af,'name','') or getattr(af,'path','') or '')
                    if n:return n
            except Exception:pass
    return ''
"""
if old_assets not in src: raise SystemExit('Phase53C patch failed: assets_name block not found')
src=src.replace(old_assets,new_assets,1)

# Add an early null-PPtr guard in ptr_reader.
needle="""def ptr_reader(p):
    if p is None:return None
"""
replacement="""def ptr_reader(p):
    if p is None:return None
    raw=pid_raw(p)
    if raw==0:return None
"""
if needle not in src: raise SystemExit('Phase53C patch failed: ptr_reader entry not found')
src=src.replace(needle,replacement,1)

# pkey must never ask ptr_reader to dereference a null PPtr.
needle="""def pkey(p):
    return rkey(ptr_reader(p))
"""
replacement="""def pkey(p):
    if p is None:return None
    raw=pid_raw(p)
    if raw==0:return None
    return rkey(ptr_reader(p))
"""
if needle not in src: raise SystemExit('Phase53C patch failed: pkey block not found')
src=src.replace(needle,replacement,1)

# pobj/pname are diagnostic-name helpers only. Null references have no name.
needle="""def pobj(p):
    if p is None:return None
"""
replacement="""def pobj(p):
    if p is None:return None
    if pid_raw(p)==0:return None
"""
if needle not in src: raise SystemExit('Phase53C patch failed: pobj entry not found')
src=src.replace(needle,replacement,1)

Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod 700 "$TMP"
trap 'rm -f "$TMP"' EXIT
bash "$TMP"
