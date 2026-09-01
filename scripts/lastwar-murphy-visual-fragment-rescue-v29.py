#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

from pathlib import Path
from collections import defaultdict
import csv, io, json, subprocess, sys, zipfile

ROOT = Path(sys.argv[1]).resolve()
RET = ROOT / 'frontend/lab/manual-review-v27/index/retained.json'
TSV = ROOT / 'frontend/lab/master-assets-v2/index/lastwar-graphics-asset-path-index-v1.tsv'
CACHE = Path.home() / '.cache/wfgg-v29-fragment-bundles'
CACHE.mkdir(parents=True, exist_ok=True)


def as_int(v, d=-1):
    try: return int(v)
    except Exception: return d

D = json.loads(RET.read_text('utf-8'))
items = list(D.get('items') or [])
audie = next((x for x in items if as_int(x.get('id')) == 5115), {})
audie_deps = [as_int(x) for x in (audie.get('dependencies') or []) if as_int(x) >= 0]
needed = set()
for x in items:
    bid = as_int(x.get('bundleId'))
    if bid >= 0: needed.add(bid)
    if x.get('category') == 'direct-candidate':
        needed.update(as_int(v) for v in (x.get('uniqueDependencies') or []) if as_int(v) >= 0)
        needed.update(audie_deps)
    elif as_int(x.get('id')) == 5115:
        needed.update(audie_deps)

specs = {}
with TSV.open('r', encoding='utf-8', errors='replace', newline='') as f:
    for r in csv.DictReader(f, delimiter='\t'):
        bid = as_int(r.get('bundleId'))
        if bid not in needed or bid in specs: continue
        off = as_int(r.get('offset'), -1)
        span = as_int(r.get('spanBytes'), -1)
        entry = str(r.get('fragmentEntry') or '').strip().replace('\\','/')
        frag = str(r.get('tableFragment') or '').strip()
        if off >= 0 and span > 0 and (entry or frag):
            specs[bid] = {
                'bundleId': bid,
                'entry': entry or ('assets/AssetBundles/' + frag),
                'fragment': frag or Path(entry).name,
                'offset': off,
                'span': span,
                'logical': str(r.get('logicalName') or ''),
                'alias': str(r.get('aliasName') or ''),
            }


def apk_paths():
    out = []
    cached = ROOT / 'frontend/lab/master-assets-v2/meta/lastwar-installed-apk-paths-v1.txt'
    if cached.is_file():
        for line in cached.read_text('utf-8', 'replace').splitlines():
            p = line.strip()
            if p and p not in out: out.append(p)
    for cmd in (['pm','path','com.fun.lastwar.gp'], ['cmd','package','path','com.fun.lastwar.gp']):
        try:
            cp = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            for line in ((cp.stdout or '') + '\n' + (cp.stderr or '')).splitlines():
                line = line.strip().rstrip('\r')
                if line.startswith('package:'):
                    p = line.split(':',1)[1].strip()
                    if p and p not in out: out.append(p)
        except Exception:
            pass
    return [p for p in out if Path(p).is_file()]

apks = apk_paths()
print('V29_FRAGMENT_RESCUE_START', f'needed={len(needed)}', f'specs={len(specs)}', f'apks={len(apks)}', flush=True)
if not apks:
    print('V29_FRAGMENT_RESCUE_NO_APK_PATHS', flush=True)
    raise SystemExit(0)

# Map every needed fragment entry to the APK/split that contains it.
entries = sorted({s['entry'] for s in specs.values()})
where = {}
zip_handles = {}
for apk in apks:
    try:
        z = zipfile.ZipFile(apk, 'r')
        zip_handles[apk] = z
        names = set(z.namelist())
        for e in entries:
            if e in names and e not in where:
                where[e] = apk
    except Exception as e:
        print('V29_APK_OPEN_FAIL', apk, type(e).__name__, e, flush=True)

by_entry = defaultdict(list)
for bid, s in specs.items():
    by_entry[s['entry']].append(s)

made = 0
missing_entry = 0
bad_slice = 0
for entry, rows in sorted(by_entry.items()):
    apk = where.get(entry)
    if not apk:
        missing_entry += len(rows)
        print('V29_FRAGMENT_MISSING', entry, f'bundles={len(rows)}', flush=True)
        continue
    z = zip_handles[apk]
    rows.sort(key=lambda r: r['offset'])
    try:
        with z.open(entry, 'r') as fh:
            for s in rows:
                out = CACHE / f"bundle-{s['bundleId']}.bundle"
                if out.is_file() and out.stat().st_size == s['span']:
                    made += 1
                    continue
                try:
                    fh.seek(s['offset'])
                    raw = fh.read(s['span'])
                except Exception as e:
                    print('V29_SLICE_READ_FAIL', s['bundleId'], type(e).__name__, e, flush=True)
                    bad_slice += 1
                    continue
                sig = raw[:16]
                if len(raw) != s['span'] or not (sig.startswith(b'UnityFS') or sig.startswith(b'UnityWeb') or sig.startswith(b'UnityRaw')):
                    print('V29_SLICE_INVALID', s['bundleId'], f"bytes={len(raw)}/{s['span']}", 'sig='+repr(sig), flush=True)
                    bad_slice += 1
                    continue
                out.write_bytes(raw)
                made += 1
                print('V29_FRAGMENT_BUNDLE', s['bundleId'], Path(apk).name, entry, f"offset={s['offset']}", f"bytes={s['span']}", flush=True)
    except Exception as e:
        print('V29_FRAGMENT_ENTRY_FAIL', entry, type(e).__name__, e, flush=True)
        bad_slice += len(rows)

for z in zip_handles.values():
    try: z.close()
    except Exception: pass

print('V29_FRAGMENT_RESCUE_READY', f'reconstructed={made}', f'missingEntry={missing_entry}', f'badSlice={bad_slice}', f'cache={CACHE}', flush=True)
