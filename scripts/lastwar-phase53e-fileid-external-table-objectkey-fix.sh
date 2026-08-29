#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 53E
# EXACT PPtr RESOLUTION THROUGH m_FileID + m_PathID
# CODE ONLY · OFFLINE ONLY · no fuzzy matching · no generated assets.
#
# Phase53D proved that the authoritative transform hierarchy is correct, but
# every Mesh/Material PPtr remained unresolved. Unity PPtr identity is encoded
# by (owner serialized file, m_FileID, m_PathID):
#   m_FileID == 0 -> same serialized file as the owner
#   m_FileID > 0  -> owner.externals[m_FileID-1]
# This wrapper resolves that identity directly against serialized files already
# loaded in the UnityPy environment. Dereferencing is only a secondary fallback.

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
 ('wfgg-phase53b-objectkey-scene-links.py','wfgg-phase53e-fileid-external-table.py'),
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

def assets_file_name(af):
    if af is None:return ''
    for a in ('name','path'):
        try:
            n=str(getattr(af,a,'') or '')
            if n:return n
        except Exception:pass
    return ''

def pptr_file_id(p):
    if p is None:return None
    for a in ('m_FileID','file_id','fileID'):
        try:
            v=getattr(p,a,None)
            if v is not None:return int(v)
        except Exception:pass
    return None

def pptr_owner_assets_file(p):
    if p is None:return None
    for a in ('assets_file','assetsfile','_assets_file'):
        try:
            af=getattr(p,a,None)
            if af is not None:return af
        except Exception:pass
    # Some generated PPtr classes keep the serialized owner through a reader.
    for rel in ('reader','object_reader'):
        try:r=getattr(p,rel,None)
        except Exception:r=None
        if r is None:continue
        for a in ('assets_file','assetsfile'):
            try:
                af=getattr(r,a,None)
                if af is not None:return af
            except Exception:pass
    return None

def norm_asset_ref(s):
    s=str(s or '').replace('\\\\','/').strip().lower()
    if not s:return ''
    while '//' in s:s=s.replace('//','/')
    if s.startswith('archive:/'):s=s[len('archive:/'):]
    return s

def asset_ref_tokens(s):
    s=norm_asset_ref(s)
    if not s:return set()
    parts=[x for x in s.split('/') if x]
    toks={s}
    if parts:
        toks.add(parts[-1])
        if len(parts)>=2:toks.add('/'.join(parts[-2:]))
    return {x for x in toks if x}

ACTIVE_LOADED_FILES={}
ACTIVE_AMBIGUOUS_FILES=set()

def set_loaded_file_lookup(readers):
    global ACTIVE_LOADED_FILES,ACTIVE_AMBIGUOUS_FILES
    tmp={}
    for r in readers:
        n=assets_name_from_reader(r)
        if not n:continue
        for tok in asset_ref_tokens(n):tmp.setdefault(tok,set()).add(n)
    ACTIVE_LOADED_FILES={}
    ACTIVE_AMBIGUOUS_FILES=set()
    for tok,names in tmp.items():
        if len(names)==1:ACTIVE_LOADED_FILES[tok]=next(iter(names))
        else:ACTIVE_AMBIGUOUS_FILES.add(tok)

def external_ref_name(owner,file_id):
    if owner is None or file_id is None or file_id<=0:return ''
    exts=None
    for a in ('externals','m_Externals'):
        try:
            exts=getattr(owner,a,None)
            if exts is not None:break
        except Exception:pass
    if exts is None:return ''
    try:ext=exts[file_id-1]
    except Exception:return ''
    if isinstance(ext,dict):
        vals=[ext.get(k) for k in ('path','name','asset_path','m_PathName')]
    else:
        vals=[]
        for a in ('path','name','asset_path','m_PathName'):
            try:vals.append(getattr(ext,a,None))
            except Exception:pass
    for v in vals:
        if v:return str(v)
    return ''

def resolve_loaded_external_name(ref):
    for tok in sorted(asset_ref_tokens(ref),key=len,reverse=True):
        if tok in ACTIVE_LOADED_FILES:return ACTIVE_LOADED_FILES[tok]
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
    if p is None:return None
    raw=pid_raw(p)
    if raw in (None,0):return None
    try:
        if hasattr(p,'type') and assets_name_from_reader(p):return p
    except Exception:pass
    for fn in ('get_obj','get_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):
                r=f()
                if r is not None:return r
        except Exception:pass
    try:r=getattr(p,'reader',None)
    except Exception:r=None
    if r is not None:
        try:
            if hasattr(r,'type') and pid_raw(r) is not None:return r
        except Exception:pass
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):
                o=f()
                try:rr=getattr(o,'object_reader',None) or getattr(o,'reader',None)
                except Exception:rr=None
                if rr is not None and pid_raw(rr) is not None:return rr
        except Exception:pass
    return None
"""
if old_ptr not in src: raise SystemExit('Phase53E patch failed: ptr_reader block not found')
src=src.replace(old_ptr,new_ptr,1)

old_pkey="""def pkey(p):
    return rkey(ptr_reader(p))
"""
new_pkey="""def pkey(p):
    if p is None:return None
    raw=pid_raw(p)
    if raw in (None,0):return None
    owner=pptr_owner_assets_file(p)
    owner_name=assets_file_name(owner)
    fid=pptr_file_id(p)
    # Native Unity semantics: fileID 0 points inside the owner serialized file.
    if fid==0 and owner_name:
        return (owner_name,raw)
    # fileID N points to externals[N-1]. Resolve only to a serialized file that
    # is already resident in this exact UnityPy environment.
    if fid is not None and fid>0:
        ref=external_ref_name(owner,fid)
        target=resolve_loaded_external_name(ref)
        if target:
            return (target,raw)
    # Secondary verification/fallback through UnityPy if it can resolve safely.
    return rkey(ptr_reader(p))
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
    if p is None:return None
    raw=pid_raw(p)
    if raw in (None,0):return None
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):return f()
        except Exception:pass
    rr=ptr_reader(p)
    if rr is not None:return robj(rr)
    return None
"""
if old_pobj not in src: raise SystemExit('Phase53E patch failed: pobj block not found')
src=src.replace(old_pobj,new_pobj,1)

needle="""        env=UnityPy.load(*[str(x) for x in files]);readers=list(env.objects);row['parseOk']=True
        export_mesh,export_tex=phase49_identity(readers,e49)
"""
replacement="""        env=UnityPy.load(*[str(x) for x in files]);readers=list(env.objects);row['parseOk']=True
        set_loaded_file_lookup(readers)
        export_mesh,export_tex=phase49_identity(readers,e49)
"""
if needle not in src: raise SystemExit('Phase53E patch failed: environment init block not found')
src=src.replace(needle,replacement,1)

Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod 700 "$TMP"
trap 'rm -f "$TMP"' EXIT
bash "$TMP"
