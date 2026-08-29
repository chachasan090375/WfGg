#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$ROOT/scripts/lastwar-phase45-authoritative-bundle-map-31.sh"
BRANCH="portal-auth-lastwar-lab-v1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
[[ -s "$TARGET" ]] || fail "Phase45 absente: $TARGET"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"

python - "$TARGET" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')
start=s.find("cache_roots=[]\nfor p in (\n")
end=s.find("\nout={\n", start)
if start < 0 or end < 0:
    raise SystemExit('bloc cache Phase45 introuvable; patch refuse')
new=r'''cache_roots=[]
for p in (
    f'/storage/emulated/0/Android/data/{pkg}/files',
    f'/sdcard/Android/data/{pkg}/files',
    f'/storage/emulated/0/Android/obb/{pkg}',
    f'/sdcard/Android/obb/{pkg}',
):
    row={
      'path':p,
      'exists':None,
      'readable':False,
      'permissionDenied':False,
      'sampleFiles':[]
    }
    # Android 11+ scoped storage can raise PermissionError even for stat()/exists().
    # Never let visibility probing abort the authoritative manifest mapping.
    try:
        st=os.stat(p)
        row['exists']=True
    except FileNotFoundError:
        row['exists']=False
    except PermissionError as e:
        row['exists']=None
        row['permissionDenied']=True
        row['probeError']=repr(e)
    except OSError as e:
        row['exists']=None
        row['probeError']=repr(e)

    if row['exists'] is True and not row['permissionDenied']:
        try:
            row['readable']=bool(os.access(p,os.R_OK))
        except Exception as e:
            row['readable']=False
            row['probeError']=repr(e)

    if row['exists'] is True and row['readable']:
        try:
            count=0
            for root,dirs,files in os.walk(p,topdown=True):
                # Bound the probe: metadata only, no large file reads.
                for fn in files:
                    low=fn.lower()
                    if any(x in low for x in ('bundle','gameres','fragment','asset')) or low.endswith(('.bytes','.dat','.data')):
                        full=os.path.join(root,fn)
                        try: sz=os.path.getsize(full)
                        except PermissionError:
                            sz=None
                        except OSError:
                            sz=None
                        row['sampleFiles'].append({'path':full,'bytes':sz});count+=1
                        if count>=80:break
                if count>=80:break
        except PermissionError as e:
            row['permissionDenied']=True
            row['readable']=False
            row['probeError']=repr(e)
        except Exception as e:
            row['probeError']=repr(e)
    cache_roots.append(row)
'''
s=s[:start]+new+s[end:]
p.write_text(s,encoding='utf-8')
print('PHASE45_PERMISSION_SAFE_PATCH_OK')
PY

chmod +x "$TARGET"
exec bash "$TARGET"
