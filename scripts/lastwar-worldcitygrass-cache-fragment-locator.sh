#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — locate/extract WorldCityGrass from DOWNLOADED cache fragments.
# Read-only against Last War storage. No Last War network. main untouched.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
TARGET_LOGICAL="gameres_main_file_prefabs_world_worldcitygrass_57011ddf6417bd1e4c5b15c4767faa33.bundle"
TARGET_ALIAS="4fb00983cfffc6d086a6e621124ce4fe9b0ec26440a7799c7d86f8b83506e805.bundle"
BASE="/sdcard/Android/data/$PKG/files"
OUTDIR="$ROOT/frontend/lab/local_assets/lastwar-worldcitygrass-cache-fragment-v1"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_WORLDCITYGRASS_CACHE_FRAGMENT.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-worldcitygrass-cache-fragment.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v adb >/dev/null 2>&1 || fail "adb absent"
command -v python >/dev/null 2>&1 || fail "python absent"
SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
[[ -n "$SERIAL" ]] || fail "aucun appareil ADB connecté"
mkdir -p "$OUTDIR" "$(dirname "$REPORT")" "$(dirname "$PY")"
rm -rf "$OUTDIR/tables" "$OUTDIR/extracted"; mkdir -p "$OUTDIR/tables" "$OUTDIR/extracted"

# List only relevant metadata/fragments from the whole app external files tree.
LIST="$OUTDIR/cache-file-list.txt"
adb -s "$SERIAL" shell "find '$BASE' -type f 2>/dev/null | grep -E '(BundleOffsetTable|AliasOffsetTable|BundleFragment|gameres)'" | tr -d '\r' > "$LIST" || true
COUNT="$(wc -l < "$LIST" | tr -d ' ')"
echo "CACHE_METADATA_FILES count=$COUNT"
[[ "$COUNT" -gt 0 ]] || { echo "WORLDCITYGRASS_CACHE_NOT_DOWNLOADED reason=no-cache-metadata"; exit 0; }

# Pull all offset tables (small files). Keep original remote path in index.
INDEX="$OUTDIR/table-index.tsv"; : > "$INDEX"
N=0
while IFS= read -r REMOTE; do
  case "$REMOTE" in
    *BundleOffsetTable.bytes|*AliasOffsetTable.bytes)
      N=$((N+1)); LOCAL="$OUTDIR/tables/$(printf '%03d' "$N")_$(basename "$REMOTE")"
      if adb -s "$SERIAL" pull "$REMOTE" "$LOCAL" >/dev/null 2>&1; then
        printf '%s\t%s\n' "$LOCAL" "$REMOTE" >> "$INDEX"
      fi
      ;;
  esac
done < "$LIST"

echo "OFFSET_TABLES pulled=$(wc -l < "$INDEX" | tr -d ' ')"

cat > "$PY" <<'PYEOF'
from pathlib import Path
import sys,struct,json,subprocess,os
idx=Path(sys.argv[1]); outdir=Path(sys.argv[2]); report=Path(sys.argv[3]); serial=sys.argv[4]; target_logical=sys.argv[5]; target_alias=sys.argv[6]; listp=Path(sys.argv[7])

def read7(buf,pos):
    out=0;shift=0
    while True:
        if pos>=len(buf): raise ValueError('7bit eof')
        x=buf[pos];pos+=1;out|=(x&0x7f)<<shift
        if not x&0x80:return out,pos
        shift+=7

def parse(buf):
    pos=0
    if len(buf)<4:return []
    fc=struct.unpack_from('<I',buf,pos)[0];pos+=4; groups=[]
    for _ in range(fc):
        ln,pos=read7(buf,pos);frag=buf[pos:pos+ln].decode('utf-8','replace');pos+=ln
        payload=struct.unpack_from('<I',buf,pos)[0];pos+=4
        cnt=struct.unpack_from('<I',buf,pos)[0];pos+=4; rows=[]
        for _ in range(cnt):
            ln,pos=read7(buf,pos);name=buf[pos:pos+ln].decode('utf-8','replace');pos+=ln
            off=struct.unpack_from('<Q',buf,pos)[0];pos+=8;rows.append((name,off))
        groups.append({'fragment':frag,'payload':payload,'rows':rows})
    return groups

entries=[]
if idx.exists():
    for line in idx.read_text('utf-8').splitlines():
        if not line.strip():continue
        local,remote=line.split('\t',1)
        try: groups=parse(Path(local).read_bytes())
        except Exception as e:
            entries.append({'table':remote,'error':repr(e)});continue
        kind='alias' if remote.endswith('AliasOffsetTable.bytes') else 'logical'
        for gi,g in enumerate(groups):
            for ri,(name,off) in enumerate(g['rows']):
                if name in (target_logical,target_alias):
                    rows=g['rows']; nextoff=rows[ri+1][1] if ri+1<len(rows) else None
                    entries.append({'table':remote,'kind':kind,'group':gi,'fragment':g['fragment'],'name':name,'offset':off,'nextOffset':nextoff,'payload':g['payload']})

files=[x.strip() for x in listp.read_text('utf-8').splitlines() if x.strip()]
fragments=[x for x in files if 'BundleFragment' in os.path.basename(x)]

def candidates_for(hit):
    frag=hit.get('fragment',''); td=os.path.dirname(hit['table']); out=[]
    # Exact fragment name next to table first.
    if frag:
        out += [f'{td}/{frag}', f'{td}/{os.path.basename(frag)}']
    # Then any listed physical fragment with matching basename/substring.
    for f in fragments:
        if frag and (os.path.basename(f)==os.path.basename(frag) or os.path.basename(frag) in os.path.basename(f)):
            out.append(f)
    # If there is only one fragment next to this table, allow it.
    near=[f for f in fragments if os.path.dirname(f)==td]
    if len(near)==1:out.append(near[0])
    seen=[]
    for x in out:
        if x not in seen:seen.append(x)
    return seen

def remote_size(path):
    cp=subprocess.run(['adb','-s',serial,'shell',f'wc -c < {path!r} 2>/dev/null'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    try:return int(cp.stdout.strip())
    except:return None

extracted=None
for h in entries:
    if 'offset' not in h:continue
    for remote in candidates_for(h):
        sz=remote_size(remote)
        if not sz or h['offset']>=sz:continue
        end=h.get('nextOffset')
        if end is None or end<=h['offset'] or end>sz:end=sz
        n=end-h['offset']
        if n<=0:continue
        dest=outdir/'extracted'/'WorldCityGrass.bundle'
        # dd byte-precise from remote fragment; stdout redirected to local file.
        with dest.open('wb') as fo:
            cp=subprocess.run(['adb','-s',serial,'exec-out','dd',f'if={remote}',f'bs=1',f'skip={h["offset"]}',f'count={n}','status=none'],stdout=fo,stderr=subprocess.PIPE)
        if cp.returncode==0 and dest.stat().st_size==n:
            extracted={'hit':h,'remoteFragment':remote,'fragmentBytes':sz,'bytes':n,'local':str(dest)};break
        try:dest.unlink()
        except:pass
    if extracted:break

lines=['WfGg Last War — WORLDCITYGRASS CACHE FRAGMENT LOCATOR','',f'targetLogical={target_logical}',f'targetAlias={target_alias}',f'matches={len([e for e in entries if "offset" in e])}',f'extracted={bool(extracted)}','']
for e in entries:
    lines.append('MATCH '+json.dumps(e,ensure_ascii=False))
if extracted:lines += ['', 'EXTRACTED '+json.dumps(extracted,ensure_ascii=False)]
else:lines += ['', 'RESULT WorldCityGrass not present in any downloaded offset table/fragment currently visible under app external files.']
report.write_text('\n'.join(lines)+'\n','utf-8')
print('WORLDCITYGRASS_CACHE_SCAN',f'matches={len([e for e in entries if "offset" in e])}',f'extracted={1 if extracted else 0}')
for e in entries:
    if 'offset' in e: print('CACHE_OFFSET_MATCH',e['kind'],e['fragment'],e['offset'],e['name'])
if extracted:
    print('WORLDCITYGRASS_CACHE_EXTRACTED',extracted['bytes'],extracted['remoteFragment'])
else:
    print('WORLDCITYGRASS_CACHE_NOT_DOWNLOADED')
print('REPORT',report)
PYEOF

python "$PY" "$INDEX" "$OUTDIR" "$REPORT" "$SERIAL" "$TARGET_LOGICAL" "$TARGET_ALIAS" "$LIST"
rm -f "$PY"

echo "=== WORLDCITYGRASS CACHE FRAGMENT LOCATOR TERMINE ==="
echo "Rapport: $REPORT"
echo "main non modifiée."
