#!/usr/bin/env python3
from __future__ import annotations

"""Restore the source `identity` column from the canonical TSV into the V33 SQLite catalogue.

V31 intentionally started from a small semantic schema and did not persist the TSV identity field.
For exact Sprite -> Texture2D resolution that omission is costly because Unity external PPtrs often
refer to a CAB/serialized-file identity rather than to the display asset name.  This enrichment is
lossless: stable IDs are recomputed with the exact V31 recipe and the original TSV identity string is
stored verbatim in `source_identity`.
"""

from pathlib import Path
import csv, hashlib, sqlite3, sys, time

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
TSV=ROOT/'frontend/lab/master-assets-v2/index/lastwar-graphics-asset-path-index-v1.tsv'
DB=Path.home()/'.cache/wfgg-lastwar-v31/graphics-catalog-v31.sqlite3'


def first_field(r,*names):
    for n in names:
        v=r.get(n)
        if v is not None and str(v).strip():return str(v).strip()
    return ''


def stable_id(r):
    asset_path=first_field(r,'assetPath','asset_path','path')
    logical=first_field(r,'logicalName','logical_name','bundleName')
    alias=first_field(r,'aliasName','alias_name','name')
    key='|'.join([
        first_field(r,'tableFragment','fragment','fragmentEntry'),
        first_field(r,'bundleId','bundle_id'),
        first_field(r,'offset'),asset_path,logical,alias,
    ])
    return 'LWGA-'+hashlib.sha1(key.encode('utf-8','replace')).hexdigest()[:14].upper()


def main():
    if not TSV.is_file():raise SystemExit('TSV absent: '+str(TSV))
    if not DB.is_file():raise SystemExit('Catalogue absent: '+str(DB))
    started=time.time();con=sqlite3.connect(DB)
    cols={r[1] for r in con.execute('PRAGMA table_info(assets)')}
    if 'source_identity' not in cols:con.execute('ALTER TABLE assets ADD COLUMN source_identity TEXT')
    con.execute('CREATE INDEX IF NOT EXISTS idx_assets_source_identity ON assets(source_identity)')
    batch=[];rows=matched=with_identity=0
    with TSV.open('r',encoding='utf-8',errors='replace',newline='') as fh:
        rd=csv.DictReader(fh,delimiter='\t')
        if 'identity' not in (rd.fieldnames or []):raise SystemExit('Colonne identity absente du TSV')
        for r in rd:
            rows+=1;identity=str(r.get('identity') or '').strip()
            if identity:with_identity+=1
            batch.append((identity,stable_id(r)))
            if len(batch)>=4000:
                before=con.total_changes
                con.executemany('UPDATE assets SET source_identity=? WHERE stable_id=?',batch)
                matched+=con.total_changes-before;batch=[]
            if rows%30000==0:print('V33_IDENTITY_PROGRESS',rows,flush=True)
    if batch:
        before=con.total_changes;con.executemany('UPDATE assets SET source_identity=? WHERE stable_id=?',batch);matched+=con.total_changes-before
    con.commit()
    cab=con.execute("SELECT count(*) FROM assets WHERE lower(coalesce(source_identity,'')) LIKE '%cab-%'").fetchone()[0]
    nonempty=con.execute("SELECT count(*) FROM assets WHERE coalesce(source_identity,'')<>''").fetchone()[0]
    con.close()
    print('V33_IDENTITY_READY',f'rows={rows}',f'withIdentity={with_identity}',f'matched={matched}',f'nonempty={nonempty}',f'cabIdentities={cab}',f'seconds={time.time()-started:.2f}',flush=True)


if __name__=='__main__':main()
