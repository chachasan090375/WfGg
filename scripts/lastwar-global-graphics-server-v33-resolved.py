#!/usr/bin/env python3
from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path
from collections import Counter
import importlib.util, os, re, sqlite3, sys, zipfile

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / 'scripts/lastwar-global-graphics-server-v33.py'
CACHE = Path.home() / '.cache/wfgg-lastwar-v31'
UNITY_VERSION_CACHE = CACHE / 'unity-version-v33.txt'
UNITY_VERSION_RE = re.compile(rb'(?<![0-9])20(?:1[7-9]|2[0-9])\.[0-9]{1,2}\.[0-9]{1,3}[abfp]\d+(?![0-9])')
UNITY_VERSION_TEXT_RE = re.compile(r'^20(?:1[7-9]|2[0-9])\.[0-9]{1,2}\.[0-9]{1,3}[abfp]\d+$')

spec = importlib.util.spec_from_file_location('wfgg_v33_core', CORE_PATH)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

_original_materialize = core.v31.materialize_bundle
PHYSICAL_FIELDS = ('bundle_id','offset_bytes','span_bytes','fragment_entry','table_fragment')


def _valid_physical(a):
    try:
        return int(a.get('bundle_id') or -1) >= 0 and int(a.get('offset_bytes') or -1) >= 0 and int(a.get('span_bytes') or -1) > 0
    except Exception:
        return False


def _candidate_rows(a):
    """Return only exact/near-exact bundle representatives with physical slice data.

    Priority is deliberately conservative:
      1) same numeric bundle_id;
      2) same logical bundle filename;
      3) same alias bundle filename.
    We never guess from a neighbouring folder here.
    """
    con = core.dbcon()
    con.row_factory = sqlite3.Row
    seen = set()
    out = []
    base = "bundle_id>=0 AND offset_bytes>=0 AND span_bytes>0 AND coalesce(table_fragment,'')<>''"

    def add(sql, params, why):
        for r in con.execute(sql, params).fetchall():
            key = (r['bundle_id'], r['offset_bytes'], r['span_bytes'], r['table_fragment'], r['fragment_entry'])
            if key in seen:
                continue
            seen.add(key)
            out.append((dict(r), why))
            if len(out) >= 12:
                return

    try:
        bid = int(a.get('bundle_id') or -1)
    except Exception:
        bid = -1
    if bid >= 0:
        add(f"SELECT * FROM assets WHERE {base} AND bundle_id=? ORDER BY row_no LIMIT 4", (bid,), 'same-bundle-id')

    logical = str(a.get('logical_name') or '').strip()
    if logical:
        add(f"SELECT * FROM assets WHERE {base} AND lower(logical_name)=lower(?) ORDER BY row_no LIMIT 4", (logical,), 'same-logical-bundle-name')

    alias = str(a.get('alias_name') or '').strip()
    if alias:
        add(f"SELECT * FROM assets WHERE {base} AND lower(alias_name)=lower(?) ORDER BY row_no LIMIT 4", (alias,), 'same-alias-bundle-name')

    con.close()
    return out


def resolved_materialize_bundle(a):
    if _valid_physical(a):
        return _original_materialize(a)

    first_error = None
    try:
        return _original_materialize(a)
    except Exception as e:
        first_error = e

    for rep, why in _candidate_rows(a):
        merged = dict(a)
        for k in PHYSICAL_FIELDS:
            merged[k] = rep.get(k)
        try:
            p, source = _original_materialize(merged)
            return p, source + '|physical-resolver:' + why
        except Exception:
            continue

    raise RuntimeError('Position physique du bundle absente et aucun représentant exact résoluble') from first_error


def _read_version_cache():
    try:
        value = UNITY_VERSION_CACHE.read_text('utf-8').strip()
        if UNITY_VERSION_TEXT_RE.fullmatch(value):
            return value, 'cache'
    except Exception:
        pass
    return '', ''


def _scan_stream_for_versions(fh, max_bytes=48 * 1024 * 1024):
    found = Counter()
    read = 0
    tail = b''
    while read < max_bytes:
        chunk = fh.read(min(1024 * 1024, max_bytes - read))
        if not chunk:
            break
        read += len(chunk)
        data = tail + chunk
        for m in UNITY_VERSION_RE.finditer(data):
            found[m.group(0).decode('ascii', 'ignore')] += 1
        tail = data[-64:]
    return found


def _scan_apk_for_unity_version(apk):
    """Read likely Unity metadata entries from installed APK/splits.

    Last War bundles often strip the engine version from individual UnityFS files,
    while application metadata still contains it. This avoids hard-coding a guess.
    """
    counts = Counter()
    try:
        with zipfile.ZipFile(apk, 'r') as z:
            priority = []
            secondary = []
            for name in z.namelist():
                low = name.lower()
                if 'globalgamemanagers' in low or low.endswith('/boot.config') or low.endswith('boot.config'):
                    priority.append(name)
                elif (
                    'resources.assets' in low or 'sharedassets' in low or low.endswith('/level0') or
                    low.endswith('data.unity3d') or low.endswith('/libunity.so')
                ):
                    secondary.append(name)
            for group, limit in ((priority, 16 * 1024 * 1024), (secondary[:12], 48 * 1024 * 1024)):
                for name in group:
                    try:
                        with z.open(name, 'r') as fh:
                            counts.update(_scan_stream_for_versions(fh, limit))
                    except Exception:
                        continue
                if counts:
                    break
    except Exception:
        pass
    return counts


def detect_unity_version():
    explicit = os.environ.get('WFGG_UNITY_VERSION', '').strip()
    if UNITY_VERSION_TEXT_RE.fullmatch(explicit):
        return explicit, 'env:WFGG_UNITY_VERSION'

    cached, source = _read_version_cache()
    if cached:
        return cached, source

    counts = Counter()
    sources = []
    for apk in core.v31.apk_paths():
        c = _scan_apk_for_unity_version(apk)
        if c:
            counts.update(c)
            sources.append(Path(apk).name)
    if counts:
        version, _ = counts.most_common(1)[0]
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            UNITY_VERSION_CACHE.write_text(version + '\n', 'utf-8')
        except Exception:
            pass
        return version, 'apk:' + ','.join(sources[:4])

    return '', 'not-found'


def configure_unitypy():
    try:
        import UnityPy
        import UnityPy.config
    except Exception as e:
        print('V33_UNITYPY_UNAVAILABLE', str(e), flush=True)
        return ''

    version, source = detect_unity_version()
    if version:
        UnityPy.config.FALLBACK_UNITY_VERSION = version
        print('V33_UNITY_VERSION', 'version=' + version, 'source=' + source, flush=True)
        return version

    print(
        'V33_UNITY_VERSION_NOT_FOUND',
        'Aucune version Unity détectée dans les APK. Définir WFGG_UNITY_VERSION si nécessaire.',
        flush=True,
    )
    return ''


# Physical resolver used by both direct 2D rendering and multi-bundle 3D assembly.
core.v31.materialize_bundle = resolved_materialize_bundle

# Critical for Last War: many UnityFS bundles have a stripped/invalid engine version.
# UnityPy requires FALLBACK_UNITY_VERSION in that case; derive it from installed APK metadata.
DETECTED_UNITY_VERSION = configure_unitypy()


if __name__ == '__main__':
    url = f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html'
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V33 — 2D / 3D + PHYSICAL RESOLVER + UNITY VERSION ===', flush=True)
    print(url, flush=True)
    ThreadingHTTPServer(('127.0.0.1', core.PORT), core.Handler).serve_forever()
