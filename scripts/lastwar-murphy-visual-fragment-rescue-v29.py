#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

from pathlib import Path
from collections import defaultdict
import csv, json, os, subprocess, sys, zipfile

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
    if bid >= 0:
        needed.add(bid)
    if x.get('category') == 'direct-candidate':
        needed.update(as_int(v) for v in (x.get('uniqueDependencies') or []) if as_int(v) >= 0)
        needed.update(audie_deps)
    elif as_int(x.get('id')) == 5115:
        needed.update(audie_deps)

# One physical slice specification per bundle ID, taken directly from the
# authoritative path index. No name/vehicle keyword filtering occurs here.
specs = {}
with TSV.open('r', encoding='utf-8', errors='replace', newline='') as f:
    for r in csv.DictReader(f, delimiter='\t'):
        bid = as_int(r.get('bundleId'))
        if bid not in needed or bid in specs:
            continue
        off = as_int(r.get('offset'), -1)
        span = as_int(r.get('spanBytes'), -1)
        entry = str(r.get('fragmentEntry') or '').strip().replace('\\', '/')
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

fragment_names = {s['fragment'].lower() for s in specs.values() if s.get('fragment')}


def apk_paths():
    out = []
    cached = ROOT / 'frontend/lab/master-assets-v2/meta/lastwar-installed-apk-paths-v1.txt'
    if cached.is_file():
        for line in cached.read_text('utf-8', 'replace').splitlines():
            p = line.strip()
            if p and p not in out:
                out.append(p)
    for cmd in (['pm', 'path', 'com.fun.lastwar.gp'], ['cmd', 'package', 'path', 'com.fun.lastwar.gp']):
        try:
            cp = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            for line in ((cp.stdout or '') + '\n' + (cp.stderr or '')).splitlines():
                line = line.strip().rstrip('\r')
                if line.startswith('package:'):
                    p = line.split(':', 1)[1].strip()
                    if p and p not in out:
                        out.append(p)
        except Exception:
            pass
    return [p for p in out if Path(p).is_file()]


def local_fragment_paths():
    # Prefer already extracted fragments. This also covers installations where
    # Android does not allow Termux to read /data/app/*.apk directly.
    roots = [
        ROOT,
        Path.home() / '.cache',
        Path.home() / 'storage/downloads',
        Path.home() / 'storage/shared/Download',
        Path('/sdcard/Android/data/com.fun.lastwar.gp'),
        Path('/storage/emulated/0/Android/data/com.fun.lastwar.gp'),
    ]
    found = {}
    seen = set()
    for base in roots:
        try:
            key = str(base.resolve())
        except Exception:
            key = str(base)
        if key in seen or not base.exists():
            continue
        seen.add(key)
        try:
            for dp, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', 'bundle-reconstruction-data'}]
                for fn in files:
                    low = fn.lower()
                    if low in fragment_names and low not in found:
                        found[low] = Path(dp) / fn
                if len(found) == len(fragment_names):
                    return found
        except (PermissionError, OSError):
            pass
    return found

local_frags = local_fragment_paths()
apks = apk_paths()
print(
    'V29_FRAGMENT_RESCUE_START',
    f'needed={len(needed)}', f'specs={len(specs)}',
    f'localFragments={len(local_frags)}/{len(fragment_names)}', f'apks={len(apks)}',
    flush=True,
)

# Map needed archive entries to whichever installed APK/split contains them.
entries = sorted({s['entry'] for s in specs.values()})
apk_where = {}
zip_handles = {}
for apk in apks:
    try:
        z = zipfile.ZipFile(apk, 'r')
        zip_handles[apk] = z
        names = set(z.namelist())
        for e in entries:
            if e in names and e not in apk_where:
                apk_where[e] = apk
    except Exception as e:
        print('V29_APK_OPEN_FAIL', apk, type(e).__name__, e, flush=True)

by_entry = defaultdict(list)
for bid, s in specs.items():
    by_entry[s['entry']].append(s)


def good_bundle(raw):
    sig = raw[:16]
    return bool(sig.startswith(b'UnityFS') or sig.startswith(b'UnityWeb') or sig.startswith(b'UnityRaw'))


def write_slice(s, raw, source_label):
    out = CACHE / f"bundle-{s['bundleId']}.bundle"
    if len(raw) != s['span'] or not good_bundle(raw):
        print(
            'V29_SLICE_INVALID', s['bundleId'],
            f"bytes={len(raw)}/{s['span']}", 'sig=' + repr(raw[:16]),
            f'source={source_label}', flush=True,
        )
        return False
    out.write_bytes(raw)
    print(
        'V29_FRAGMENT_BUNDLE', s['bundleId'], f'source={source_label}',
        s['entry'], f"offset={s['offset']}", f"bytes={s['span']}", flush=True,
    )
    return True

made = 0
cached = 0
missing_entry = 0
bad_slice = 0
source_local = 0
source_apk = 0

for entry, rows in sorted(by_entry.items()):
    rows.sort(key=lambda r: r['offset'])
    frag_name = rows[0]['fragment'].lower() if rows else ''
    local = local_frags.get(frag_name)
    apk = apk_where.get(entry)

    # Existing valid reconstructed bundles win immediately.
    pending = []
    for s in rows:
        out = CACHE / f"bundle-{s['bundleId']}.bundle"
        try:
            if out.is_file() and out.stat().st_size == s['span'] and good_bundle(out.read_bytes()[:16]):
                cached += 1
                continue
        except Exception:
            pass
        pending.append(s)
    if not pending:
        continue

    if local and local.is_file():
        try:
            with local.open('rb') as fh:
                for s in pending:
                    try:
                        fh.seek(s['offset'])
                        raw = fh.read(s['span'])
                        if write_slice(s, raw, 'local:' + str(local)):
                            made += 1
                            source_local += 1
                        else:
                            bad_slice += 1
                    except Exception as e:
                        print('V29_LOCAL_SLICE_FAIL', s['bundleId'], type(e).__name__, e, flush=True)
                        bad_slice += 1
            continue
        except Exception as e:
            print('V29_LOCAL_FRAGMENT_FAIL', local, type(e).__name__, e, flush=True)

    if apk:
        try:
            z = zip_handles[apk]
            with z.open(entry, 'r') as fh:
                for s in pending:
                    try:
                        fh.seek(s['offset'])
                        raw = fh.read(s['span'])
                        if write_slice(s, raw, 'apk:' + Path(apk).name):
                            made += 1
                            source_apk += 1
                        else:
                            bad_slice += 1
                    except Exception as e:
                        print('V29_APK_SLICE_FAIL', s['bundleId'], type(e).__name__, e, flush=True)
                        bad_slice += 1
            continue
        except Exception as e:
            print('V29_FRAGMENT_ENTRY_FAIL', entry, type(e).__name__, e, flush=True)
            bad_slice += len(pending)
            continue

    missing_entry += len(pending)
    print('V29_FRAGMENT_MISSING', entry, f'bundles={len(pending)}', f'fragment={rows[0]["fragment"] if rows else "-"}', flush=True)

for z in zip_handles.values():
    try:
        z.close()
    except Exception:
        pass

print(
    'V29_FRAGMENT_RESCUE_READY',
    f'reconstructed={made}', f'cached={cached}',
    f'fromLocal={source_local}', f'fromAPK={source_apk}',
    f'missingEntry={missing_entry}', f'badSlice={bad_slice}',
    f'cache={CACHE}', flush=True,
)
