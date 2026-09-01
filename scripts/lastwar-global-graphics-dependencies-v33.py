#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from collections import defaultdict
import csv, sqlite3, sys, time

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
TSV = ROOT / 'frontend/lab/master-assets-v2/index/lastwar-graphics-asset-path-index-v1.tsv'
DB = Path.home() / '.cache/wfgg-lastwar-v31/graphics-catalog-v31.sqlite3'

if not TSV.is_file():
    raise SystemExit(f'Index TSV absent: {TSV}')
if not DB.is_file():
    raise SystemExit(f'Catalogue SQLite absent: {DB}')


def parse_dep_ids(raw: str) -> list[int]:
    out=[]; seen=set()
    for tok in str(raw or '').replace(',', '|').replace(';', '|').split('|'):
        tok=tok.strip()
        if not tok or not tok.isdigit():
            continue
        n=int(tok)
        if n < 0 or n in seen:
            continue
        seen.add(n); out.append(n)
    return out


def main():
    started=time.time(); deps=defaultdict(list); rows=0; source_bundles=set()
    with TSV.open('r',encoding='utf-8',errors='replace',newline='') as fh:
        rd=csv.DictReader(fh,delimiter='\t')
        if 'bundleId' not in (rd.fieldnames or []) or 'dependencies' not in (rd.fieldnames or []):
            raise SystemExit('Colonnes bundleId/dependencies absentes du TSV')
        for r in rd:
            rows += 1
            try: src=int((r.get('bundleId') or '').strip())
            except Exception: continue
            source_bundles.add(src)
            if src not in deps:
                deps[src]=parse_dep_ids(r.get('dependencies') or '')
            elif not deps[src]:
                got=parse_dep_ids(r.get('dependencies') or '')
                if got: deps[src]=got
            if rows % 30000 == 0:
                print('V33_DEP_PROGRESS',rows,flush=True)

    con=sqlite3.connect(DB)
    con.executescript('''
    DROP TABLE IF EXISTS bundle_dependencies_v33;
    CREATE TABLE bundle_dependencies_v33(
      source_bundle_id INTEGER NOT NULL,
      target_bundle_id INTEGER NOT NULL,
      ordinal INTEGER NOT NULL,
      relation TEXT NOT NULL DEFAULT 'depends_on',
      confidence TEXT NOT NULL DEFAULT 'exact',
      PRIMARY KEY(source_bundle_id,target_bundle_id)
    );
    CREATE INDEX idx_bundle_deps_v33_target ON bundle_dependencies_v33(target_bundle_id);
    ''')
    cols={r[1] for r in con.execute('PRAGMA table_info(assets)')}
    if 'dependency_count' not in cols:
        con.execute('ALTER TABLE assets ADD COLUMN dependency_count INTEGER')
    batch=[]
    for src,targets in deps.items():
        for pos,target in enumerate(targets):
            batch.append((src,target,pos,'depends_on','exact'))
            if len(batch)>=5000:
                con.executemany('INSERT OR IGNORE INTO bundle_dependencies_v33 VALUES(?,?,?,?,?)',batch); batch=[]
    if batch: con.executemany('INSERT OR IGNORE INTO bundle_dependencies_v33 VALUES(?,?,?,?,?)',batch)
    con.execute('UPDATE assets SET dependency_count=coalesce((SELECT count(*) FROM bundle_dependencies_v33 d WHERE d.source_bundle_id=assets.bundle_id),0)')
    con.commit()
    edge_count=con.execute('SELECT count(*) FROM bundle_dependencies_v33').fetchone()[0]
    sources_with_deps=con.execute('SELECT count(distinct source_bundle_id) FROM bundle_dependencies_v33').fetchone()[0]
    con.close()
    print('V33_DEP_READY',f'rows={rows}',f'bundles={len(source_bundles)}',f'sourcesWithDeps={sources_with_deps}',f'edges={edge_count}',f'seconds={time.time()-started:.2f}',flush=True)

if __name__=='__main__': main()
