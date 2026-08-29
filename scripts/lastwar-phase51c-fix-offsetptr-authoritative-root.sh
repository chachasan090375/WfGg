#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 51C
# Fix Phase51B without duplicating its decoder:
# 1) unwrap UnityPy OffsetPtr<Clip>.data before reading Streamed/Dense/Constant clips;
# 2) resolve duplicate CRC paths only inside the authoritative queue-model root.
# CODE ONLY · OFFLINE ONLY · no generated motion · no Last War network.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
BASE="$ROOT/scripts/lastwar-phase51b-decode-idle-direct-avatar.sh"
TMP="$ROOT/scripts/.lastwar-phase51c-generated.sh"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$BASE" ]] || fail "Phase51B absente: $BASE"

python - "$BASE" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')

repls=[
('PHASE 51B','PHASE 51C'),
('PHASE51B','PHASE51C'),
('lastwar-current15-animation-v2','lastwar-current15-animation-v3'),
('current15-idle-keyframes-v2.json','current15-idle-keyframes-v3.json'),
('wfgg-phase51b-direct-avatar.py','wfgg-phase51c-offsetptr-root.py'),
]
for a,b in repls:
    src=src.replace(a,b)

old="""def resolver(paths,hier_hashes,tos):
    def hierarchy_from_avatar(ap):
        vals=[p for p in paths if p==ap or p.endswith('/'+ap)]
        return vals[0] if len(vals)==1 else None
    def resolve(h):
        h=int(h)&0xffffffff
        hv=sorted(hier_hashes.get(h,set()))
        if len(hv)==1:return {'path':hv[0],'source':'transform-crc','avatarPath':None}
        av=sorted(tos.get(h,set()))
        if len(av)==1:
            hp=hierarchy_from_avatar(av[0])
            return {'path':hp or av[0],'source':'avatar-tos'+('-hierarchy' if hp else ''),'avatarPath':av[0]}
        return {'path':None,'source':'ambiguous' if hv or av else 'unresolved','hierarchyCandidates':hv[:8],'avatarCandidates':av[:8]}
    return resolve
"""
new="""def resolver(paths,hier_hashes,tos,expected_root):
    def rel_under_root(p):
        parts=str(p).split('/')
        try:i=parts.index(expected_root)
        except ValueError:return None
        return '/'.join(parts[i:])
    def hierarchy_from_avatar(ap):
        vals=[p for p in paths if p==ap or p.endswith('/'+ap)]
        rooted=[p for p in vals if expected_root in p.split('/')]
        vals=rooted or vals
        rels={rel_under_root(p) or p:p for p in vals}
        return next(iter(rels.values())) if len(rels)==1 else None
    def resolve(h):
        h=int(h)&0xffffffff
        hv=sorted(hier_hashes.get(h,set()))
        rooted=[p for p in hv if expected_root in p.split('/')]
        if rooted: hv=rooted
        # Multiple physical copies of the same prefab exist in dependency bundles.
        # Collapse only byte-for-byte identical relative Transform paths under the
        # authoritative queue-model root; never fuzzy-match names.
        rels={}
        for p in hv:
            rel=rel_under_root(p)
            if rel is not None: rels.setdefault(rel,p)
        if len(rels)==1:
            p=next(iter(rels.values()))
            return {'path':p,'source':'queue-root-crc','avatarPath':None}
        if len(hv)==1:return {'path':hv[0],'source':'transform-crc','avatarPath':None}
        av=sorted(tos.get(h,set()))
        if len(av)==1:
            hp=hierarchy_from_avatar(av[0])
            return {'path':hp or av[0],'source':'avatar-tos'+('-hierarchy' if hp else ''),'avatarPath':av[0]}
        return {'path':None,'source':'ambiguous' if hv or av else 'unresolved','hierarchyCandidates':hv[:8],'avatarCandidates':av[:8]}
    return resolve
"""
if old not in src:
    raise SystemExit('Phase51C patch failed: resolver block not found')
src=src.replace(old,new,1)

old2="""    muscle=attr(c,'m_MuscleClip','MuscleClip')
    compact=attr(muscle,'m_Clip','Clip')
    if compact is None:raise ValueError('direct m_MuscleClip.m_Clip absent')
    sc=attr(compact,'m_StreamedClip','StreamedClip'); dc=attr(compact,'m_DenseClip','DenseClip'); kc=attr(compact,'m_ConstantClip','ConstantClip')
"""
new2="""    muscle=attr(c,'m_MuscleClip','MuscleClip')
    clip_holder=attr(muscle,'m_Clip','Clip')
    if clip_holder is None:raise ValueError('direct m_MuscleClip.m_Clip absent')
    # UnityPy generated classes represent Unity OffsetPtr<Clip> as a wrapper
    # whose payload is .data. Phase51B stopped on the wrapper itself, which is
    # why every real clip appeared as 0 streamed / 0 dense curves.
    compact=attr(clip_holder,'data','m_Data',default=clip_holder)
    sc=attr(compact,'m_StreamedClip','StreamedClip'); dc=attr(compact,'m_DenseClip','DenseClip'); kc=attr(compact,'m_ConstantClip','ConstantClip')
"""
if old2 not in src:
    raise SystemExit('Phase51C patch failed: compact Clip block not found')
src=src.replace(old2,new2,1)

# Patch the runtime resolver call without assuming a pre-existing expected_root variable.
needle='resolve=resolver(paths,hier_hashes,tos)'
replacement="resolve=resolver(paths,hier_hashes,tos,Path(str(h.get('queueModelPath') or '')).stem)"
if needle not in src:
    raise SystemExit('Phase51C patch failed: resolver call not found')
src=src.replace(needle,replacement,1)

# Keep Phase51B source untouched; execute a generated sibling so ROOT resolution stays valid.
Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod 700 "$TMP"
trap 'rm -f "$TMP"' EXIT
bash "$TMP"
