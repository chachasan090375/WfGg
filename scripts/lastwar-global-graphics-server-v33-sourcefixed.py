#!/usr/bin/env python3
from __future__ import annotations

"""V33 runtime-source verified server.

Fixes the semantic mismatch where render_availability='local-exact' only meant that an
index row had bundle/offset/span metadata, while the underlying BundleFragment was not
necessarily present or accessible on the current Android installation.

At startup this server:
- indexes actual BundleFragment files and entries reachable from installed APKs;
- demotes rows whose physical representative has no source on this phone;
- keeps the global catalogue intact, but makes the 'local-renderable' filter truthful.

At render time it also adds a conservative recovery path:
- exact fragmentEntry first;
- case-insensitive full entry match;
- BundleFragment basename match across installed split APKs;
- exact offset/span and UnityFS header are still mandatory.

No approximate asset substitution is introduced.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
import importlib.util
import os
import shutil
import sqlite3
import sys
import zipfile

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
CORRELATED = ROOT / 'scripts/lastwar-global-graphics-server-v33-correlated.py'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


c = load_module('wfgg_v33_correlated_sourcefixed', CORRELATED)
core = c.core
v31 = core.v31
BASE_MATERIALIZE = v31.materialize_bundle

_apk_entries = None


def _as_dict(row):
    """Normalize sqlite3.Row/dict objects before using mapping helpers such as .get()."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except Exception:
        return row


def _norm_entry(s: str) -> str:
    return str(s or '').replace('\\', '/').strip('/').casefold()


def _base(s: str) -> str:
    return _norm_entry(s).rsplit('/', 1)[-1]


def apk_entry_index():
    global _apk_entries
    if _apk_entries is not None:
        return _apk_entries
    exact = {}
    by_base = {}
    apks = list(v31.apk_paths())
    errors = []
    for apk in apks:
        try:
            with zipfile.ZipFile(apk, 'r') as z:
                for entry in z.namelist():
                    k = _norm_entry(entry)
                    exact.setdefault(k, []).append((apk, entry))
                    by_base.setdefault(_base(entry), []).append((apk, entry))
        except Exception as exc:
            errors.append(Path(apk).name + ':' + str(exc)[:160])
    _apk_entries = {'exact': exact, 'base': by_base, 'apks': apks, 'errors': errors}
    print('V33_RUNTIME_APK_INDEX', 'apks=' + str(len(apks)), 'entries=' + str(len(exact)), 'errors=' + str(len(errors)), flush=True)
    return _apk_entries


def source_candidates(row):
    """Return actual source files/ZIP entries compatible with one indexed locator."""
    row = _as_dict(row)
    seen = set()
    out = []
    table = str(row.get('table_fragment') or '')
    entry = str(row.get('fragment_entry') or '')

    # Loose BundleFragment files copied to Termux/shared storage.
    lf = v31.local_fragments()
    for key in (_base(table), _base(entry)):
        p = lf.get(key)
        if p and p.is_file():
            sig = ('file', str(p))
            if sig not in seen:
                seen.add(sig); out.append(('file', p, str(p)))

    idx = apk_entry_index()
    # Exact path (case-insensitive) first.
    if entry:
        for apk, real_entry in idx['exact'].get(_norm_entry(entry), []):
            sig = ('apk', apk, real_entry)
            if sig not in seen:
                seen.add(sig); out.append(('apk', apk, real_entry))

    # Recovery for changed prefixes/case across split APK layouts.
    for key in (_base(entry), _base(table)):
        if not key:
            continue
        for apk, real_entry in idx['base'].get(key, []):
            sig = ('apk', apk, real_entry)
            if sig not in seen:
                seen.add(sig); out.append(('apk', apk, real_entry))
    return out


def _read_slice(kind, source, entry, off, span):
    if kind == 'file':
        with Path(source).open('rb') as fh:
            fh.seek(off)
            head = fh.read(16)
            if not head.startswith((b'UnityFS', b'UnityWeb', b'UnityRaw')):
                return None, 'bad-header:' + head[:12].hex()
            fh.seek(off)
            raw = fh.read(span)
            return (raw, '') if len(raw) == span else (None, 'short-read:' + str(len(raw)))
    with zipfile.ZipFile(source, 'r') as z:
        with z.open(entry, 'r') as fh:
            fh.seek(off)
            head = fh.read(16)
            if not head.startswith((b'UnityFS', b'UnityWeb', b'UnityRaw')):
                return None, 'bad-header:' + head[:12].hex()
            fh.seek(off)
            raw = fh.read(span)
            return (raw, '') if len(raw) == span else (None, 'short-read:' + str(len(raw)))


def _physical_rows_for(a):
    rows = []
    seen = set()
    def add(d, why):
        d = _as_dict(d)
        if not d:
            return
        key = (d.get('bundle_id'), d.get('offset_bytes'), d.get('span_bytes'), d.get('table_fragment'), d.get('fragment_entry'))
        if key in seen:
            return
        seen.add(key); rows.append((dict(d), why))
    add(a, 'selected-row')
    a = _as_dict(a)
    sid = str(a.get('render_source_stable_id') or '').strip()
    if sid:
        con = core.dbcon()
        r = con.execute('SELECT * FROM assets WHERE stable_id=?', (sid,)).fetchone()
        con.close()
        add(r, 'render-source')
    return rows


def _mark_runtime_unavailable(a, reason):
    a = _as_dict(a)
    sid = str(a.get('stable_id') or '')
    if not sid:
        return
    try:
        con = core.dbcon()
        con.execute(
            "UPDATE assets SET render_availability='global-index-only', render_source_reason=? WHERE stable_id=?",
            ('runtime:' + reason[:220], sid),
        )
        con.commit(); con.close()
    except Exception:
        pass


def enhanced_materialize(a):
    a = _as_dict(a)
    # Keep every previously working path first.
    try:
        return BASE_MATERIALIZE(a)
    except Exception as first:
        first_error = str(first)

    attempts = []
    for row, why in _physical_rows_for(a):
        try:
            bid = int(row.get('bundle_id') if row.get('bundle_id') is not None else -1)
            off = int(row.get('offset_bytes') if row.get('offset_bytes') is not None else -1)
            span = int(row.get('span_bytes') if row.get('span_bytes') is not None else -1)
        except Exception:
            continue
        if bid < 0 or off < 0 or span <= 0:
            continue
        for kind, source, entry in source_candidates(row):
            label = why + ':' + kind + ':' + Path(source).name + ((':' + entry) if kind == 'apk' else '')
            try:
                raw, err = _read_slice(kind, source, entry, off, span)
            except Exception as exc:
                attempts.append(label + ':io:' + str(exc)[:160]); continue
            if raw is None:
                attempts.append(label + ':' + err); continue
            out = v31.BUNDLE_CACHE / ('bundle-' + str(bid) + '.bundle')
            out.write_bytes(raw)
            try:
                v31.BUNDLE_LRU[bid] = str(out)
                v31.BUNDLE_LRU.move_to_end(bid)
                v31.trim_lru(v31.BUNDLE_LRU, v31.MAX_BUNDLES, True)
            except Exception:
                pass
            print('V33_RUNTIME_SOURCE_RECOVERED', a.get('stable_id'), 'bundle=' + str(bid), 'via=' + label, flush=True)
            return out, 'runtime-source-recovery:' + label

    idx = apk_entry_index()
    info = (
        'first=' + first_error[:220] +
        '; fragmentEntry=' + str(a.get('fragment_entry') or '') +
        '; tableFragment=' + str(a.get('table_fragment') or '') +
        '; apkCount=' + str(len(idx['apks'])) +
        '; fallbackAttempts=' + str(len(attempts)) +
        ('; sample=' + ' || '.join(attempts[:3]) if attempts else '')
    )
    _mark_runtime_unavailable(a, 'source-not-materializable')
    raise RuntimeError('RUNTIME_SOURCE_NOT_MATERIALIZABLE: ' + info)


def _source_exists_for(row, local_keys, apk_exact, apk_base):
    row = _as_dict(row)
    entry = _norm_entry(row.get('fragment_entry') or '')
    table_base = _base(row.get('table_fragment') or '')
    entry_base = _base(entry)
    return bool(
        (table_base and table_base in local_keys) or
        (entry_base and entry_base in local_keys) or
        (entry and entry in apk_exact) or
        (entry_base and entry_base in apk_base) or
        (table_base and table_base in apk_base)
    )


def runtime_availability_audit():
    """Fast source-presence audit; it does not decode every bundle at startup."""
    idx = apk_entry_index()
    local_keys = set(v31.local_fragments().keys())
    apk_exact = set(idx['exact'].keys())
    apk_base = set(idx['base'].keys())
    con = core.dbcon(); con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT stable_id,render_availability,render_source_stable_id,fragment_entry,table_fragment,bundle_id,offset_bytes,span_bytes "
        "FROM assets WHERE render_availability IN ('local-exact','local-resolved')"
    ).fetchall()
    source_ids = {str(r['render_source_stable_id']) for r in rows if r['render_source_stable_id']}
    source_map = {}
    if source_ids:
        ids = list(source_ids)
        for pos in range(0, len(ids), 800):
            chunk = ids[pos:pos+800]
            ph = ','.join('?' for _ in chunk)
            for sr in con.execute('SELECT * FROM assets WHERE stable_id IN (' + ph + ')', chunk):
                # sqlite3.Row intentionally has no .get(); normalize immediately.
                source_map[sr['stable_id']] = dict(sr)
    updates = []
    keep = demote = 0
    for raw in rows:
        r = dict(raw)
        rep = r
        if r['render_availability'] == 'local-resolved' and r['render_source_stable_id']:
            rep = source_map.get(r['render_source_stable_id']) or r
        if _source_exists_for(rep, local_keys, apk_exact, apk_base):
            keep += 1
        else:
            demote += 1
            updates.append(('global-index-only', 'runtime-fragment-source-absent', r['stable_id']))
    if updates:
        con.executemany('UPDATE assets SET render_availability=?,render_source_reason=? WHERE stable_id=?', updates)
        con.execute("DELETE FROM facets WHERE axis='render_availability'")
        for value, count in con.execute("SELECT coalesce(render_availability,'unknown'),count(*) FROM assets GROUP BY coalesce(render_availability,'unknown')"):
            con.execute('INSERT INTO facets(axis,value,count) VALUES(?,?,?)', ('render_availability', value, count))
        con.commit()
    con.close()
    print('V33_RUNTIME_AVAIL_AUDIT', 'checked=' + str(len(rows)), 'kept=' + str(keep), 'demoted=' + str(demote), 'localFragments=' + str(len(local_keys)), 'apkEntries=' + str(len(apk_exact)), flush=True)
    return {'checked': len(rows), 'kept': keep, 'demoted': demote}


v31.materialize_bundle = enhanced_materialize
AUDIT = runtime_availability_audit()


if __name__ == '__main__':
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V33 — RUNTIME SOURCE VERIFIED ===', flush=True)
    print('V33_RUNTIME_SOURCE exact-entry + casefold-entry + fragment-basename recovery=ON', flush=True)
    print('V33_RUNTIME_AVAIL local-renderable=SOURCE-PRESENCE-VERIFIED audit=' + repr(AUDIT), flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', core.PORT), c.CorrelatedHandler).serve_forever()
