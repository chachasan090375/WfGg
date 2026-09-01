#!/usr/bin/env python3
from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path
import importlib.util, sqlite3, sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / 'scripts/lastwar-global-graphics-server-v33.py'

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
    # Fast path: keep the original exact coordinates when present.
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


# Patch once. v31.render_asset() and the V33 3D builder both call this symbol,
# so the resolver fixes both direct 2D rendering and multi-bundle 3D assembly.
core.v31.materialize_bundle = resolved_materialize_bundle


if __name__ == '__main__':
    url = f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html'
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V33 — 2D / 3D + PHYSICAL RESOLVER ===', flush=True)
    print(url, flush=True)
    ThreadingHTTPServer(('127.0.0.1', core.PORT), core.Handler).serve_forever()
