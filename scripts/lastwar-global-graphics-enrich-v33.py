#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from collections import Counter
import json, re, sqlite3, sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
DB = Path.home() / '.cache/wfgg-lastwar-v31/graphics-catalog-v31.sqlite3'

if not DB.is_file():
    raise SystemExit(f'Catalogue absent: {DB}')

DIRECT_2D_TECH = {'sprite','texture2d','atlas','render-target'}
GEOMETRY_3D_TECH = {'mesh'}
THREE_D_COMPONENT_TECH = {'material','shader'}
PREFAB_TECH = {'prefab'}
ANIM_TECH = {'animation','animator'}

TWO_D_TOKENS = (
    '/ui/','/gui/','/sprites/','/sprite/','/icons/','/icon/','/texture/','/textures/',
    'portrait','heroicon','activityicons','button','btn_','_btn','badge','frame','background','banner','loading','illustration'
)
THREE_D_TOKENS = (
    '/mesh/','/meshes/','/model/','/models/','/geometry/','/character/','/characters/','/vehicle/','/vehicles/',
    '/building/','/buildings/','/weapon/','/weapons/','/unit/','/units/','/scene/','/world/','skinnedmesh','meshrenderer',
    'lod0','lod1','lod2','lod3','skeleton','rig','bone','bodymesh','headmesh'
)
THREE_D_COMPONENT_TOKENS = (
    '/material/','/materials/','/shader/','/shaders/','/prefab/','/prefabs/','/animation/','/animations/','/animator/',
    '/vx/','/fx/','/vfx/'
)
NON_VISUAL_TOKENS = ('/audio/','/sound/','/sounds/','/music/','/lua/','/script/','/scripts/','/config/','/localization/')

ROLE_2D = {'portrait','icon','background','frame','button','badge','loading','illustration','sprite-atlas','texture'}
FAMILY_3D = {'characters','vehicles','buildings','weapons-equipment','units','world-environment'}


def lowtext(row: sqlite3.Row) -> str:
    return ' '.join(str(row[k] or '') for k in ('asset_path','logical_name','alias_name','visual_role','family','tech_kind')).lower().replace('\\','/')


def parent_folder(path: str) -> str:
    p=(path or '').replace('\\','/').strip()
    if '/' not in p:return ''
    return p.rsplit('/',1)[0]


def has_any(text: str, toks) -> list[str]:
    return [t for t in toks if t in text]


def classify(row: sqlite3.Row):
    tech=(row['tech_kind'] or '').lower()
    role=(row['visual_role'] or '').lower()
    family=(row['family'] or '').lower()
    text=lowtext(row)
    h2=has_any(text,TWO_D_TOKENS)
    h3=has_any(text,THREE_D_TOKENS)
    hc=has_any(text,THREE_D_COMPONENT_TOKENS)
    hn=has_any(text,NON_VISUAL_TOKENS)

    # The asset itself is an image/texture, even if later used on a 3D model.
    if tech in DIRECT_2D_TECH:
        role3='texture' if tech=='texture2d' and h3 else '2d-image'
        return '2D',0.99,['technical-kind:'+tech]+(['3d-context:'+h3[0]] if h3 else []),role3
    if role in ROLE_2D:
        return '2D',0.96,['visual-role:'+role], '2d-image'
    if h2 and not h3 and tech not in GEOMETRY_3D_TECH:
        return '2D',0.90,['2d-path:'+x for x in h2[:4]], '2d-image'

    if tech in GEOMETRY_3D_TECH:
        return '3D',0.995,['technical-kind:'+tech], 'geometry'
    if h3 and tech not in DIRECT_2D_TECH:
        if tech in PREFAB_TECH:
            return 'Composant 3D',0.95,['3d-path:'+x for x in h3[:4],'technical-kind:prefab'], 'prefab'
        if tech in THREE_D_COMPONENT_TECH:
            role3='material' if tech=='material' else 'shader'
            return 'Composant 3D',0.96,['3d-path:'+x for x in h3[:4],'technical-kind:'+tech], role3
        if tech in ANIM_TECH:
            return 'Composant 3D',0.93,['3d-path:'+x for x in h3[:4],'technical-kind:'+tech], 'animation'
        if tech in {'unknown',''} and (family in FAMILY_3D or len(h3)>=1):
            return '3D',0.84,['3d-path:'+x for x in h3[:4]], 'geometry-candidate'
        return 'Composant 3D',0.88,['3d-path:'+x for x in h3[:4]], 'component'

    if tech in THREE_D_COMPONENT_TECH:
        role3='material' if tech=='material' else 'shader'
        return 'Mixte 2D/3D',0.72,['technical-kind:'+tech,'context-not-resolved'],role3
    if tech in PREFAB_TECH:
        return 'Mixte 2D/3D',0.68,['technical-kind:prefab','context-not-resolved'],'prefab'
    if tech in ANIM_TECH:
        return 'Mixte 2D/3D',0.62,['technical-kind:'+tech,'context-not-resolved'],'animation'
    if hc:
        return 'Mixte 2D/3D',0.60,['component-path:'+x for x in hc[:4]],'component'

    if hn:
        return 'Non visuel',0.92,['non-visual-path:'+x for x in hn[:4]],'none'
    if (row['graphic_class'] or '')=='Non graphique':
        return 'Non visuel',0.86,['graphic-class:Non graphique'],'none'

    return 'Indéterminé',0.0,['insufficient-evidence'],'unknown'


def ensure_schema(con: sqlite3.Connection):
    cols={r[1] for r in con.execute('pragma table_info(assets)')}
    additions={
        'dimension_class':'TEXT','dimension_conf':'REAL','dimension_evidence_json':'TEXT',
        'model_role':'TEXT','asset_folder':'TEXT'
    }
    for c,t in additions.items():
        if c not in cols: con.execute(f'ALTER TABLE assets ADD COLUMN {c} {t}')
    con.execute('CREATE INDEX IF NOT EXISTS idx_assets_dimension_v33 ON assets(dimension_class)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_assets_model_role_v33 ON assets(model_role)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_assets_folder_v33 ON assets(asset_folder)')


def rebuild_facets(con: sqlite3.Connection):
    con.execute("DELETE FROM facets WHERE axis IN ('dimension_class','model_role')")
    for value,count in con.execute("SELECT coalesce(dimension_class,'Indéterminé'),count(*) FROM assets GROUP BY coalesce(dimension_class,'Indéterminé')"):
        con.execute('INSERT INTO facets(axis,value,count) VALUES(?,?,?)',('dimension_class',value,count))
    for value,count in con.execute("SELECT coalesce(model_role,'unknown'),count(*) FROM assets GROUP BY coalesce(model_role,'unknown')"):
        con.execute('INSERT INTO facets(axis,value,count) VALUES(?,?,?)',('model_role',value,count))


def main():
    con=sqlite3.connect(DB);con.row_factory=sqlite3.Row;ensure_schema(con)
    counts=Counter();roles=Counter();total=0
    rows=con.execute('SELECT stable_id,asset_path,logical_name,alias_name,visual_role,family,tech_kind,graphic_class FROM assets')
    for row in rows:
        dclass,conf,evidence,mrole=classify(row)
        folder=parent_folder(str(row['asset_path'] or row['logical_name'] or ''))
        con.execute('UPDATE assets SET dimension_class=?,dimension_conf=?,dimension_evidence_json=?,model_role=?,asset_folder=? WHERE stable_id=?',
                    (dclass,conf,json.dumps(evidence,ensure_ascii=False,separators=(',',':')),mrole,folder,row['stable_id']))
        counts[dclass]+=1;roles[mrole]+=1;total+=1
        if total%20000==0:print('V33_DIMENSION_PROGRESS',total,flush=True)
    rebuild_facets(con);con.commit();con.close()
    print('V33_DIMENSION_COUNTS',json.dumps(counts,ensure_ascii=False),flush=True)
    print('V33_MODEL_ROLE_COUNTS',json.dumps(roles,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
