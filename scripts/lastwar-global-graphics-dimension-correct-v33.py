#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from collections import Counter
import json, sqlite3, sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
DB = Path.home() / '.cache/wfgg-lastwar-v31/graphics-catalog-v31.sqlite3'

if not DB.is_file():
    raise SystemExit(f'Catalogue absent: {DB}')

MODEL_EXTS = {'.fbx','.obj','.mesh'}
PREFAB_EXTS = {'.prefab'}
MATERIAL_EXTS = {'.mat','.material','.shader'}
ANIM_EXTS = {'.anim','.animation','.controller'}
IMAGE_EXTS = {'.png','.jpg','.jpeg','.webp','.tga','.bmp','.gif','.dds','.ktx','.ktx2','.exr','.hdr','.psd'}
THREE_D_MARKERS = (
    '/mesh/','/meshes/','/model/','/models/','/geometry/','/character/','/characters/',
    '/vehicle/','/vehicles/','/building/','/buildings/','/weapon/','/weapons/','/unit/','/units/',
    '/scene/','/world/','skinnedmesh','meshrenderer','lod0','lod1','lod2','lod3','skeleton','rig','bone'
)
FAMILY_3D = {'characters','vehicles','buildings','weapons-equipment','units','world-environment'}


def suffix(path: str) -> str:
    p=(path or '').replace('\\','/').lower()
    for ext in sorted(MODEL_EXTS|PREFAB_EXTS|MATERIAL_EXTS|ANIM_EXTS|IMAGE_EXTS,key=len,reverse=True):
        if p.endswith(ext):return ext
    return Path(p).suffix.lower()


def rebuild_facets(con):
    con.execute("DELETE FROM facets WHERE axis IN ('graphic_class','dimension_class','model_role')")
    for axis,col,default in [
        ('graphic_class','graphic_class','Indéterminé'),
        ('dimension_class','dimension_class','Indéterminé'),
        ('model_role','model_role','unknown')
    ]:
        for value,count in con.execute(f"SELECT coalesce({col},?),count(*) FROM assets GROUP BY coalesce({col},?)",(default,default)):
            con.execute('INSERT INTO facets(axis,value,count) VALUES(?,?,?)',(axis,value,count))


def main():
    con=sqlite3.connect(DB);con.row_factory=sqlite3.Row
    counts=Counter();changed=0
    rows=con.execute('SELECT stable_id,asset_path,family,graphic_class,dimension_class,model_role FROM assets').fetchall()
    for r in rows:
        path=str(r['asset_path'] or '');low=path.lower().replace('\\','/');ext=suffix(path)
        family=str(r['family'] or '').lower();is3d=(family in FAMILY_3D or any(t in low for t in THREE_D_MARKERS))
        gclass=r['graphic_class'];dclass=r['dimension_class'];role=r['model_role'];ev=None

        if ext in IMAGE_EXTS:
            # A raster/texture file is intrinsically 2D even when mapped on a 3D model.
            gclass='Graphique';dclass='2D';role='texture' if is3d else '2d-image';ev='file-extension:'+ext
        elif ext in MODEL_EXTS:
            gclass='Composant graphique';dclass='3D';role='geometry';ev='model-extension:'+ext
        elif ext in PREFAB_EXTS:
            # A prefab is a composition/container, never a direct 2D bitmap.
            gclass='Composant graphique';dclass='Composant 3D' if is3d else 'Mixte 2D/3D';role='prefab';ev='prefab-extension'
        elif ext in MATERIAL_EXTS:
            gclass='Composant graphique';dclass='Composant 3D' if is3d else 'Mixte 2D/3D';role='shader' if ext=='.shader' else 'material';ev='material-extension:'+ext
        elif ext in ANIM_EXTS:
            gclass='Composant graphique';dclass='Composant 3D' if is3d else 'Mixte 2D/3D';role='animation';ev='animation-extension:'+ext

        if ev and (gclass!=r['graphic_class'] or dclass!=r['dimension_class'] or role!=r['model_role']):
            con.execute('UPDATE assets SET graphic_class=?,is_graphic=?,graphic_conf=?,graphic_evidence_json=?,dimension_class=?,dimension_conf=?,dimension_evidence_json=?,model_role=? WHERE stable_id=?',(
                gclass,1 if gclass=='Graphique' else None,0.995,json.dumps([ev],ensure_ascii=False,separators=(',',':')),
                dclass,0.995,json.dumps([ev],ensure_ascii=False,separators=(',',':')),role,r['stable_id']))
            changed+=1
        counts[dclass]+=1

    rebuild_facets(con);con.commit();con.close()
    print('V33_DIMENSION_CORRECT_READY',f'changed={changed}',json.dumps(counts,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
