#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 53E
# RAW m_FileID/m_PathID OBJECT-KEY RESOLUTION
# CODE ONLY · OFFLINE ONLY · no fuzzy matching · no generated assets.
#
# Phase53D rebuilt all authoritative hierarchies correctly but still tried to
# dereference external PPtrs to discover their target object identity. Unity's
# PPtr already contains enough exact information:
#   m_FileID == 0 -> current SerializedFile + m_PathID
#   m_FileID > 0  -> assetsfile.externals[m_FileID-1].path + m_PathID
# This phase computes that target key directly and never dereferences a PPtr for
# Mesh/Material/Texture/Transform identity.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
BASE="$ROOT/scripts/lastwar-phase53b-build-exact-objectkey-scene-links.sh"
TMP="$ROOT/scripts/.lastwar-phase53e-generated.sh"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$BASE" ]] || fail "Phase53B absente: $BASE"

python - "$BASE" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')

repls=[
 ('PHASE 53B','PHASE 53E'),
 ('PHASE53B','PHASE53E'),
 ('lastwar-current15-runtime-v3-scene','lastwar-current15-runtime-v6-scene'),
 ('current15-runtime-scene-links-v2.json','current15-runtime-scene-links-v5.json'),
 ('WFGG_LASTWAR_PHASE53B_CURRENT15_EXACT_OBJECTKEY_SCENE_LINKS.txt','WFGG_LASTWAR_PHASE53E_CURRENT15_EXACT_OBJECTKEY_SCENE_LINKS.txt'),
 ('wfgg-phase53b-objectkey-scene-links.py','wfgg-phase53e-raw-fileid-objectkey.py'),
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
    # PPtr.m_PathID is authoritative. Read it before touching any property which
    # could attempt dereference.
    for a in ('m_PathID','path_id'):
        try:
            v=getattr(x,a,None)
            if v is not None:return int(v)
        except Exception:pass
    # ObjectReader path id (safe local object identity).
    for rel in ('object_reader','reader'):
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
if old_pid not in src: raise SystemExit('Phase53E patch failed: pid_raw block not found')
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
new_assets="""def canonical_assets_name(v):
    s=str(v or '').replace('\\\\','/')
    if s.startswith('archive:/'):s=s[9:]
    if s.startswith('assets/'):s=s[7:]
    s=s.rsplit('/',1)[-1]
    return s.lower()

def serialized_name(af):
    if af is None:return ''
    try:n=str(getattr(af,'name','') or getattr(af,'path','') or '')
    except Exception:n=''
    return canonical_assets_name(n)

def assets_name_from_reader(r):
    if r is None:return ''
    # ObjectReader exposes its owning SerializedFile directly as assets_file.
    try:
        af=getattr(r,'assets_file',None)
        n=serialized_name(af)
        if n:return n
    except Exception:pass
    try:
        rr=getattr(r,'object_reader',None)
        if rr is not None:
            n=serialized_name(getattr(rr,'assets_file',None))
            if n:return n
    except Exception:pass
    return ''
"""
if old_assets not in src: raise SystemExit('Phase53E patch failed: assets_name block not found')
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
    # Diagnostic-name helper only. Binding identity NEVER depends on this function.
    if p is None:return None
    raw=pid_raw(p)
    if raw in (None,0):return None
    try:
        if hasattr(p,'type') and assets_name_from_reader(p):return p
    except Exception:pass
    for fn in ('deref','get_obj','get_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):
                r=f()
                if r is not None:return r
        except Exception:pass
    return None
"""
if old_ptr not in src: raise SystemExit('Phase53E patch failed: ptr_reader block not found')
src=src.replace(old_ptr,new_ptr,1)

old_pkey="""def pkey(p):
    return rkey(ptr_reader(p))
"""
new_pkey="""def pkey(p):
    # Exact raw PPtr resolution, equivalent to Unity's/UnityPy's FileID semantics
    # but without dereferencing or requiring the external CAB to be resident.
    if p is None:return None
    try:path_id=int(getattr(p,'m_PathID'))
    except Exception:
        try:path_id=int(getattr(p,'path_id'))
        except Exception:return None
    if path_id==0:return None
    try:file_id=int(getattr(p,'m_FileID'))
    except Exception:
        try:file_id=int(getattr(p,'file_id'))
        except Exception:file_id=0
    try:af=getattr(p,'assetsfile',None) or getattr(p,'assets_file',None)
    except Exception:af=None
    if af is None:return None
    if file_id==0:
        n=serialized_name(af)
        return (n,path_id) if n else None
    try:exts=getattr(af,'externals',[]) or []
    except Exception:exts=[]
    idx=file_id-1
    if idx<0 or idx>=len(exts):return None
    ext=exts[idx]
    try:ep=getattr(ext,'path','') or getattr(ext,'name','') or ''
    except Exception:ep=''
    n=canonical_assets_name(ep)
    return (n,path_id) if n else None
"""
if old_pkey not in src: raise SystemExit('Phase53E patch failed: pkey block not found')
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
    # Names are optional diagnostics. Never make a scene fail because an external
    # object is not resident.
    if p is None:return None
    try:
        if int(getattr(p,'m_PathID',getattr(p,'path_id',0)) or 0)==0:return None
    except Exception:pass
    for fn in ('deref_parse_as_object','read','parse_as_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):return f()
        except Exception:pass
    rr=ptr_reader(p)
    if rr is not None:
        try:return robj(rr)
        except Exception:return None
    return None
"""
if old_pobj not in src: raise SystemExit('Phase53E patch failed: pobj block not found')
src=src.replace(old_pobj,new_pobj,1)

# Make the report explicitly state the new binding source.
src=src.replace("'object_key=assets_file+path_id'","'object_key=raw_fileid_external_path+path_id'")
src=src.replace("'objectKeyUsesAssetsFileAndPathId':True","'objectKeyUsesAssetsFileAndPathId':True,'rawPPtrFileIdResolution':True")

Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod 700 "$TMP"
trap 'rm -f "$TMP"' EXIT
bash "$TMP"
