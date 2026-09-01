#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json, re, sqlite3, sys, time

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
MASTER = ROOT / 'frontend/lab/master-assets-v2/index/lastwar-graphics-master-index-v1.json'
DB = Path.home() / '.cache/wfgg-lastwar-v31/graphics-catalog-v31.sqlite3'

if not MASTER.is_file():
    raise SystemExit(f'Index maître absent: {MASTER}')
if not DB.is_file():
    raise SystemExit(f'Catalogue SQLite absent: {DB}')


def iter_array_objects(path: Path, key: str, chunk_size: int = 1 << 20):
    """Stream objects from a top-level JSON array without loading the 90 MB master index."""
    dec = json.JSONDecoder()
    pattern = re.compile(r'"' + re.escape(key) + r'"\s*:\s*\[')
    buf = ''
    started = False
    keep = max(512, len(key) + 128)
    with path.open('r', encoding='utf-8', errors='strict') as fh:
        while not started:
            chunk = fh.read(chunk_size)
            if not chunk:
                return
            buf += chunk
            m = pattern.search(buf)
            if not m:
                buf = buf[-keep:]
                continue
            buf = buf[m.end():]
            started = True
        while True:
            i = 0
            while i < len(buf) and (buf[i].isspace() or buf[i] == ','):
                i += 1
            if i < len(buf) and buf[i] == ']':
                return
            if i:
                buf = buf[i:]
            try:
                obj, end = dec.raw_decode(buf)
                if isinstance(obj, dict):
                    yield obj
                buf = buf[end:]
            except json.JSONDecodeError:
                chunk = fh.read(chunk_size)
                if not chunk:
                    return
                buf += chunk


def valid_location(x):
    if not isinstance(x, dict):
        return False
    try:
        return int(x.get('offset', -1)) >= 0 and int(x.get('spanBytes', 0)) > 0 and bool(x.get('fragmentEntry'))
    except Exception:
        return False


def choose_location(bundle):
    # The canonical master explicitly defines preferredExtraction. Respect it first.
    p = bundle.get('preferredExtraction')
    if valid_location(p):
        return p, 'preferredExtraction'
    loc = bundle.get('locations') or {}
    # Master reconstructionRecipe identityPriority is alias, then logical.
    for identity in ('alias', 'logical'):
        for x in loc.get(identity) or []:
            if valid_location(x):
                return x, 'locations.' + identity
    return None, 'unresolved'


def main():
    start = time.time()
    con = sqlite3.connect(DB)
    con.executescript('''
    CREATE TABLE IF NOT EXISTS bundle_physical_v33(
      bundle_id INTEGER PRIMARY KEY,
      logical_name TEXT,
      alias_name TEXT,
      identity TEXT,
      table_fragment TEXT,
      fragment_entry TEXT,
      offset_bytes INTEGER,
      span_bytes INTEGER,
      physical_apk TEXT,
      physical_confidence REAL,
      source_kind TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_bundle_physical_v33_logical ON bundle_physical_v33(logical_name);
    CREATE INDEX IF NOT EXISTS idx_bundle_physical_v33_alias ON bundle_physical_v33(alias_name);
    ''')
    con.execute('DELETE FROM bundle_physical_v33')

    batch = []
    total = resolved = unresolved = 0
    for b in iter_array_objects(MASTER, 'bundles'):
        total += 1
        try:
            bid = int(b.get('bundleId'))
        except Exception:
            continue
        loc, source_kind = choose_location(b)
        if loc is None:
            unresolved += 1
            continue
        resolved += 1
        try:
            conf = float(loc.get('physicalMatchConfidence', 0)) / 100.0
        except Exception:
            conf = 0.0
        batch.append((
            bid, str(b.get('logicalName') or ''), str(b.get('aliasName') or ''),
            str(loc.get('identity') or ''), str(loc.get('tableFragment') or ''),
            str(loc.get('fragmentEntry') or ''), int(loc['offset']), int(loc['spanBytes']),
            str(loc.get('physicalApk') or loc.get('tableApk') or ''), conf, source_kind
        ))
        if len(batch) >= 2000:
            con.executemany('''INSERT OR REPLACE INTO bundle_physical_v33
              (bundle_id,logical_name,alias_name,identity,table_fragment,fragment_entry,offset_bytes,span_bytes,physical_apk,physical_confidence,source_kind)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)''', batch)
            con.commit(); batch.clear()
        if total % 10000 == 0:
            print('V33_PHYSICAL_INDEX_PROGRESS', total, 'resolved=', resolved, flush=True)
    if batch:
        con.executemany('''INSERT OR REPLACE INTO bundle_physical_v33
          (bundle_id,logical_name,alias_name,identity,table_fragment,fragment_entry,offset_bytes,span_bytes,physical_apk,physical_confidence,source_kind)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)''', batch)

    # Backfill all catalog rows from the canonical per-bundle extraction coordinates.
    # This is the missing link in V31/V33: asset rows identify bundleId but don't all carry physical offsets.
    updated = 0
    cur = con.execute('SELECT bundle_id,table_fragment,fragment_entry,offset_bytes,span_bytes FROM bundle_physical_v33')
    for bid, table_fragment, fragment_entry, offset_bytes, span_bytes in cur:
        r = con.execute('''UPDATE assets
            SET table_fragment=?, fragment_entry=?, offset_bytes=?, span_bytes=?
            WHERE bundle_id=? AND (
              offset_bytes IS NULL OR offset_bytes<0 OR span_bytes IS NULL OR span_bytes<=0 OR
              coalesce(fragment_entry,'')='' OR coalesce(table_fragment,'')=''
            )''', (table_fragment, fragment_entry, offset_bytes, span_bytes, bid))
        updated += max(0, r.rowcount)
    con.commit()

    physical_assets = con.execute('''SELECT count(*) FROM assets
      WHERE bundle_id>=0 AND offset_bytes>=0 AND span_bytes>0 AND coalesce(fragment_entry,'')<>'' ''').fetchone()[0]
    all_assets = con.execute('SELECT count(*) FROM assets').fetchone()[0]
    physical_bundles = con.execute('SELECT count(*) FROM bundle_physical_v33').fetchone()[0]
    con.close()
    print('V33_PHYSICAL_INDEX_READY', json.dumps({
        'masterBundles': total,
        'physicalBundles': physical_bundles,
        'unresolvedBundles': unresolved,
        'assetRowsBackfilled': updated,
        'assetsWithPhysicalSlice': physical_assets,
        'assetsTotal': all_assets,
        'seconds': round(time.time()-start, 3)
    }, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
