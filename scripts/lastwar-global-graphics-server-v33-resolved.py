#!/usr/bin/env python3
from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path
from collections import Counter
import importlib.util, os, re, sqlite3, subprocess, sys, zipfile

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / 'scripts/lastwar-global-graphics-server-v33.py'
AVAIL_PATH = ROOT / 'scripts/lastwar-global-graphics-render-availability-v33.py'
CACHE = Path.home() / '.cache/wfgg-lastwar-v31'
UNITY_VERSION_CACHE = CACHE / 'unity-version-v33.txt'
UNITY_VERSION_RE = re.compile(rb'(?<![0-9])20(?:1[7-9]|2[0-9])\.[0-9]{1,2}\.[0-9]{1,3}[abfp]\d+(?![0-9])')
UNITY_VERSION_TEXT_RE = re.compile(r'^20(?:1[7-9]|2[0-9])\.[0-9]{1,2}\.[0-9]{1,3}[abfp]\d+$')

spec = importlib.util.spec_from_file_location('wfgg_v33_core', CORE_PATH)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

_original_materialize = core.v31.materialize_bundle
PHYSICAL_FIELDS = ('bundle_id','offset_bytes','span_bytes','fragment_entry','table_fragment')


def _ensure_render_availability():
    con = core.dbcon()
    cols = {r[1] for r in con.execute('PRAGMA table_info(assets)')}
    con.close()
    required = {'render_availability','render_source_stable_id','render_source_reason'}
    if not required.issubset(cols):
        print('V33_RENDER_AVAIL_MISSING construction...', flush=True)
        subprocess.run([sys.executable, str(AVAIL_PATH), str(ROOT)], check=True)


_ensure_render_availability()


def _valid_physical(a):
    try:
        return (
            int(a.get('bundle_id') if a.get('bundle_id') is not None else -1) >= 0
            and int(a.get('offset_bytes') if a.get('offset_bytes') is not None else -1) >= 0
            and int(a.get('span_bytes') if a.get('span_bytes') is not None else -1) > 0
            and bool(str(a.get('table_fragment') or '').strip())
        )
    except Exception:
        return False


def _source_row_from_catalog(a):
    sid = str(a.get('render_source_stable_id') or '').strip()
    if not sid:
        return None
    con = core.dbcon()
    row = con.execute(
        "SELECT * FROM assets WHERE stable_id=? AND bundle_id>=0 AND offset_bytes>=0 AND span_bytes>0 AND coalesce(table_fragment,'')<>''",
        (sid,),
    ).fetchone()
    con.close()
    return dict(row) if row else None


def _candidate_rows(a):
    """Return only proven physical representatives.

    First use the precomputed render-source mapping. Legacy exact-name lookups are kept as
    a conservative fallback for databases made before the availability pass.
    """
    source = _source_row_from_catalog(a)
    if source:
        return [(source, 'availability-map:' + str(a.get('render_source_reason') or 'precomputed'))]

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
        bid = int(a.get('bundle_id') if a.get('bundle_id') is not None else -1)
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
    availability = str(a.get('render_availability') or '')
    if availability == 'global-index-only':
        raise RuntimeError(
            "Asset du catalogue global : son bundle n'est pas présent dans l'installation Last War actuelle. "
            "Choisir 'Rendu local disponible' pour ne voir que les assets matérialisables."
        )

    if _valid_physical(a):
        return _original_materialize(a)

    first_error = None
    for rep, why in _candidate_rows(a):
        merged = dict(a)
        for k in PHYSICAL_FIELDS:
            merged[k] = rep.get(k)
        try:
            p, source = _original_materialize(merged)
            return p, source + '|physical-resolver:' + why
        except Exception as e:
            if first_error is None:
                first_error = e
            continue

    try:
        return _original_materialize(a)
    except Exception as e:
        if first_error is None:
            first_error = e

    raise RuntimeError('Position physique locale introuvable malgré le catalogue de disponibilité') from first_error


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


def search_assets_with_availability(qs):
    q = core.q1(qs, 'q').strip()
    limit = max(1, min(250, int(core.q1(qs, 'limit', '100') or 100)))
    offset = max(0, int(core.q1(qs, 'offset', '0') or 0))
    conditions = []
    params = []
    for key in ['family','subfamily','visual_role','context','tech_kind','scope_kind','scope_id','language','graphic_class','dimension_class','model_role']:
        val = core.q1(qs, key).strip()
        if val and val != 'all':
            conditions.append('a.' + key + '=?')
            params.append(val)

    availability = core.q1(qs, 'render_availability').strip()
    if availability == 'local-renderable':
        conditions.append("a.render_availability IN ('local-exact','local-resolved')")
    elif availability and availability != 'all':
        conditions.append('a.render_availability=?')
        params.append(availability)

    mc = core.q1(qs, 'min_confidence').strip()
    if mc:
        try:
            conditions.append('a.confidence>=?')
            params.append(float(mc))
        except Exception:
            pass

    event_id = core.q1(qs, 'event_id').strip()
    relation = core.q1(qs, 'event_relation').strip()
    if (event_id and event_id != 'all') or (relation and relation != 'all'):
        sub = ['l.stable_id=a.stable_id']
        subp = []
        if event_id and event_id != 'all':
            sub.append('l.event_id=?')
            subp.append(event_id)
        if relation and relation != 'all':
            sub.append('l.relation=?')
            subp.append(relation)
        conditions.append('EXISTS (SELECT 1 FROM event_asset_links_v32 l WHERE ' + ' AND '.join(sub) + ')')
        params += subp

    con = core.dbcon()
    fts = core.v31.fts_expr(q)
    if fts:
        sql = 'SELECT a.* FROM asset_fts f JOIN assets a ON a.stable_id=f.stable_id WHERE asset_fts MATCH ?'
        p = [fts]
        if conditions:
            sql += ' AND ' + ' AND '.join(conditions)
            p += params
        sql += ' ORDER BY a.confidence DESC,a.row_no LIMIT ? OFFSET ?'
        p += [limit, offset]
        try:
            rows = con.execute(sql, p).fetchall()
        except sqlite3.OperationalError:
            c2 = list(conditions) + ['lower(a.search_text) LIKE ?']
            p2 = params + ['%' + q.lower() + '%']
            rows = con.execute(
                'SELECT a.* FROM assets a WHERE ' + ' AND '.join(c2) + ' ORDER BY a.confidence DESC,a.row_no LIMIT ? OFFSET ?',
                p2 + [limit, offset],
            ).fetchall()
    else:
        sql = 'SELECT a.* FROM assets a'
        if conditions:
            sql += ' WHERE ' + ' AND '.join(conditions)
        # For local rendering put true physical rows first, then exact resolved representatives.
        sql += " ORDER BY CASE a.render_availability WHEN 'local-exact' THEN 0 WHEN 'local-resolved' THEN 1 ELSE 2 END,a.row_no LIMIT ? OFFSET ?"
        rows = con.execute(sql, params + [limit, offset]).fetchall()

    out = []
    for r in rows:
        d = core.rowdict(r)
        d['event_links'] = core.event_links(con, d['stable_id'])
        out.append(d)
    con.close()
    return out


def facets_with_availability():
    out = core._facets_v33_original()
    labels = {
        'local-exact': 'Local — position exacte',
        'local-resolved': 'Local — représentant exact',
        'global-index-only': 'Index global — bundle absent localement',
        'unknown': 'Indéterminé',
    }
    for item in out.get('render_availability', []):
        item['label'] = labels.get(item.get('value'), item.get('label') or item.get('value'))
    return out


# Physical resolver used by both direct 2D rendering and multi-bundle 3D assembly.
core.v31.materialize_bundle = resolved_materialize_bundle

# Add the render-availability axis without changing the V31/V32 database contract.
core._facets_v33_original = core.facets_v33
core.search_assets = search_assets_with_availability
core.facets_v33 = facets_with_availability

# Last War often strips the engine version from individual UnityFS bundles.
DETECTED_UNITY_VERSION = configure_unitypy()


if __name__ == '__main__':
    con = core.dbcon()
    availability_counts = dict(con.execute("SELECT render_availability,count(*) FROM assets GROUP BY render_availability"))
    con.close()
    url = f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html'
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V33 — LOCAL RENDER + 2D / 3D ===', flush=True)
    print('V33_RENDER_AVAIL_COUNTS', availability_counts, flush=True)
    print(url, flush=True)
    ThreadingHTTPServer(('127.0.0.1', core.PORT), core.Handler).serve_forever()
