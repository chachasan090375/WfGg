#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 53D
# NON-RESIDENT EXTERNAL PPtr GUARD FOR EXACT OBJECT-KEY SCENE LINKS
# CODE ONLY · OFFLINE ONLY · no fuzzy matching · no generated assets.
#
# Phase53C proved that null PPtrs are handled, then exposed a second class of
# references: non-null external PPtrs whose CAB is not resident in the staged
# local directory. Those references must remain explicit/unresolved, not abort
# the whole authoritative scene graph.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
BASE="$ROOT/scripts/lastwar-phase53b-build-exact-objectkey-scene-links.sh"
TMP="$ROOT/scripts/.lastwar-phase53d-generated.sh"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$BASE" ]] || fail "Phase53B absente: $BASE"

python - "$BASE" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')

repls=[
 ('PHASE 53B','PHASE 53D'),
 ('PHASE53B','PHASE53D'),
 ('lastwar-current15-runtime-v3-scene','lastwar-current15-runtime-v5-scene'),
 ('current15-runtime-scene-links-v2.json','current15-runtime-scene-links-v4.json'),
 ('WFGG_LASTWAR_PHASE53B_CURRENT15_EXACT_OBJECTKEY_SCENE_LINKS.txt','WFGG_LASTWAR_PHASE53D_CURRENT15_EXACT_OBJECTKEY_SCENE_LINKS.txt'),
 ('wfgg-phase53b-objectkey-scene-links.py','wfgg-phase53d-nonresident-external-pptr.py'),
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
    # Read the PPtr's own path id first. Never resolve .reader just to discover
    # that a pointer is null or external/non-resident.
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
if old_pid not in src: raise SystemExit('Phase53D patch failed: pid_raw block not found')
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
if old_assets not in src: raise SystemExit('Phase53D patch failed: assets_name block not found')
src=src.replace(old_assets,new_assets,1)

old_ptr="""def ptr_reader(p):
    if p is None:return None
    # ObjectReader itself.
    if hasattr(p,'type') and pid_raw(p) is not None and assets_name_from_reader(p):return p
    for fn in ('get_obj','get_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):
                r=f()
                if r is not None:return r
        except:pass
    # Some UnityPy PPtrs expose a resolved ObjectReader through .reader.
    r=getattr(p,'reader',None)
    if r is not None and hasattr(r,'type') and pid_raw(r) is not None:return r
    # Last exact route: dereference object then recover its object_reader.
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):
                o=f()
                rr=getattr(o,'object_reader',None) or getattr(o,'reader',None)
                if rr is not None and pid_raw(rr) is not None:return rr
        except:pass
    return None
"""
new_ptr="""def ptr_reader(p):
    if p is None:return None
    raw=pid_raw(p)
    if raw in (None,0):return None
    # ObjectReader itself.
    try:
        if hasattr(p,'type') and assets_name_from_reader(p):return p
    except Exception:pass
    # Resolve only when the referenced serialized file is already resident in
    # UnityPy's loaded environment. Missing external CABs are explicitly allowed
    # to remain unresolved here; they are not fetched and do not trigger fallback.
    for fn in ('get_obj','get_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):
                r=f()
                if r is not None:return r
        except (FileNotFoundError,KeyError,ValueError,OSError):
            pass
        except Exception:
            pass
    try:r=getattr(p,'reader',None)
    except (FileNotFoundError,KeyError,ValueError,OSError):r=None
    except Exception:r=None
    if r is not None:
        try:
            if hasattr(r,'type') and pid_raw(r) is not None:return r
        except Exception:pass
    # Last exact route, still non-fatal for a non-resident external CAB.
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):
                o=f()
                try:rr=getattr(o,'object_reader',None) or getattr(o,'reader',None)
                except Exception:rr=None
                if rr is not None and pid_raw(rr) is not None:return rr
        except (FileNotFoundError,KeyError,ValueError,OSError):
            pass
        except Exception:
            pass
    return None
"""
if old_ptr not in src: raise SystemExit('Phase53D patch failed: ptr_reader block not found')
src=src.replace(old_ptr,new_ptr,1)

old_pkey="""def pkey(p):
    return rkey(ptr_reader(p))
"""
new_pkey="""def pkey(p):
    if p is None:return None
    raw=pid_raw(p)
    if raw in (None,0):return None
    return rkey(ptr_reader(p))
"""
if old_pkey not in src: raise SystemExit('Phase53D patch failed: pkey block not found')
src=src.replace(old_pkey,new_pkey,1)

old_pobj="""def pobj(p):
    if p is None:return None
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):return f()
        except:pass
    rr=ptr_reader(p)
    if rr is not None:return robj(rr)
    return None
"""
new_pobj="""def pobj(p):
    if p is None:return None
    raw=pid_raw(p)
    if raw in (None,0):return None
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):return f()
        except (FileNotFoundError,KeyError,ValueError,OSError):
            pass
        except Exception:
            pass
    rr=ptr_reader(p)
    if rr is not None:return robj(rr)
    return None
"""
if old_pobj not in src: raise SystemExit('Phase53D patch failed: pobj block not found')
src=src.replace(old_pobj,new_pobj,1)

Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod 700 "$TMP"
trap 'rm -f "$TMP"' EXIT
bash "$TMP"
