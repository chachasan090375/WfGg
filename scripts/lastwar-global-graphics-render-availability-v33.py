#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from pathlib import Path
import sqlite3
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
DB = Path.home() / '.cache/wfgg-lastwar-v31/graphics-catalog-v31.sqlite3'
BATCH = 5000

if not DB.is_file():
    raise SystemExit(f'Catalogue absent: {DB}')


def textkey(value) -> str:
    return str(value or '').strip().casefold()


def valid_physical(row) -> bool:
    try:
        return (
            int(row['bundle_id'] if row['bundle_id'] is not None else -1) >= 0
            and int(row['offset_bytes'] if row['offset_bytes'] is not None else -1) >= 0
            and int(row['span_bytes'] if row['span_bytes'] is not None else -1) > 0
            and bool(str(row['table_fragment'] or '').strip())
        )
    except Exception:
        return False


def ensure_schema(con: sqlite3.Connection) -> None:
    cols = {r[1] for r in con.execute('PRAGMA table_info(assets)')}
    additions = {
        'render_availability': 'TEXT',
        'render_source_stable_id': 'TEXT',
        'render_source_reason': 'TEXT',
    }
    for name, typ in additions.items():
        if name not in cols:
            con.execute(f'ALTER TABLE assets ADD COLUMN {name} {typ}')
    con.execute('CREATE INDEX IF NOT EXISTS idx_assets_render_avail_v33 ON assets(render_availability)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_assets_render_source_v33 ON assets(render_source_stable_id)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_assets_bundle_v33 ON assets(bundle_id)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_assets_logical_v33 ON assets(logical_name COLLATE NOCASE)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_assets_alias_v33 ON assets(alias_name COLLATE NOCASE)')


def rebuild_facet(con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM facets WHERE axis='render_availability'")
    for value, count in con.execute(
        "SELECT coalesce(render_availability,'unknown'),count(*) FROM assets GROUP BY coalesce(render_availability,'unknown')"
    ):
        con.execute('INSERT INTO facets(axis,value,count) VALUES(?,?,?)', ('render_availability', value, count))


def main() -> None:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    ensure_schema(con)

    # Build a compact authoritative lookup only from rows that already carry an exact
    # installed fragment location. Global aliases are never promoted merely because they
    # occur near another asset in the same folder.
    physical_rows = con.execute(
        """
        SELECT stable_id,bundle_id,logical_name,alias_name,offset_bytes,span_bytes,table_fragment,fragment_entry,row_no
        FROM assets
        WHERE bundle_id>=0 AND offset_bytes>=0 AND span_bytes>0 AND coalesce(table_fragment,'')<>''
        ORDER BY row_no
        """
    ).fetchall()

    by_sid = {r['stable_id']: r for r in physical_rows}
    by_bundle = {}
    by_logical = {}
    by_alias = {}
    for r in physical_rows:
        try:
            bid = int(r['bundle_id'])
            by_bundle.setdefault(bid, r)
        except Exception:
            pass
        lk = textkey(r['logical_name'])
        if lk:
            by_logical.setdefault(lk, r)
        ak = textkey(r['alias_name'])
        if ak:
            by_alias.setdefault(ak, r)

    counts = Counter()
    reasons = Counter()
    updates = []
    total = 0

    rows = con.execute(
        'SELECT stable_id,bundle_id,logical_name,alias_name,offset_bytes,span_bytes,table_fragment,fragment_entry FROM assets ORDER BY row_no'
    )
    for r in rows:
        sid = r['stable_id']
        source = None
        availability = 'global-index-only'
        reason = 'no-installed-physical-representative'

        if sid in by_sid and valid_physical(r):
            source = by_sid[sid]
            availability = 'local-exact'
            reason = 'direct-physical-slice'
        else:
            try:
                bid = int(r['bundle_id']) if r['bundle_id'] is not None else -1
            except Exception:
                bid = -1
            if bid >= 0 and bid in by_bundle:
                source = by_bundle[bid]
                availability = 'local-resolved'
                reason = 'same-bundle-id'
            else:
                lk = textkey(r['logical_name'])
                if lk and lk in by_logical:
                    source = by_logical[lk]
                    availability = 'local-resolved'
                    reason = 'same-logical-bundle-name'
                else:
                    ak = textkey(r['alias_name'])
                    if ak and ak in by_alias:
                        source = by_alias[ak]
                        availability = 'local-resolved'
                        reason = 'same-alias-bundle-name'

        source_sid = source['stable_id'] if source is not None else None
        updates.append((availability, source_sid, reason, sid))
        counts[availability] += 1
        reasons[reason] += 1
        total += 1

        if len(updates) >= BATCH:
            con.executemany(
                'UPDATE assets SET render_availability=?,render_source_stable_id=?,render_source_reason=? WHERE stable_id=?',
                updates,
            )
            updates.clear()
            if total % 20000 < BATCH:
                print('V33_RENDER_AVAIL_PROGRESS', total, flush=True)

    if updates:
        con.executemany(
            'UPDATE assets SET render_availability=?,render_source_stable_id=?,render_source_reason=? WHERE stable_id=?',
            updates,
        )

    rebuild_facet(con)
    con.commit()
    con.close()

    print(
        'V33_RENDER_AVAIL_READY',
        f'assets={total}',
        f'physicalRows={len(physical_rows)}',
        'counts=' + repr(dict(counts)),
        'reasons=' + repr(dict(reasons)),
        flush=True,
    )


if __name__ == '__main__':
    main()
