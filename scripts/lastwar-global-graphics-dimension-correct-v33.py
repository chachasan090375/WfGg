#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from collections import Counter
import json, re, sqlite3, sys, unicodedata

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

# Family classification V31 used dense substring matching.  In particular the token
# "car" matched "card", so UI cards could become vehicles.  V33 repairs the persisted
# catalogue using subject-bearing names only and token boundaries.
VEHICLE_TOKENS = {
    'vehicle','vehicles','tank','tanks','truck','trucks','jeep','jeeps','apc','ifv','humvee',
    'aircraft','airplane','aeroplane','plane','planes','helicopter','helicopters','chopper',
    'drone','drones','uav','chariot','chariots','car','cars','armoredcar','armouredcar'
}
UI_TOKENS = {'ui','icon','icons','button','buttons','btn','panel','panels','card','cards','frame','frames','hud','menu','popup','window','dialog','atlas','spriteatlas'}
EFFECT_TOKENS = {'effect','effects','eff','fx','vfx','particle','particles','smoke','explosion','glow'}
WEAPON_TOKENS = {'weapon','weapons','missile','missiles','gun','guns','cannon','armor','armour','equipment','equip','gear'}
CHARACTER_TOKENS = {'hero','heroes','character','characters','soldier','npc'}
BUILDING_TOKENS = {'building','buildings','headquarter','headquarters','hq','garage','factory','barracks'}
WORLD_TOKENS = {'world','terrain','environment','ground','scene','road','grass','desert','snow'}


def ascii_text(value: object) -> str:
    return unicodedata.normalize('NFKD', str(value or '')).encode('ascii','ignore').decode('ascii')


def tokens(*values: object) -> set[str]:
    # Preserve CamelCase boundaries before lower-casing: TacticalCard -> tactical + card,
    # never "car".
    text=' '.join(ascii_text(v) for v in values if v)
    text=re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', text)
    return set(re.findall(r'[a-z0-9]+', text.lower()))


def has_vehicle_subject(tok: set[str], raw: str) -> bool:
    if tok & VEHICLE_TOKENS:
        return True
    # Common numbered internal forms (tank01, vehicle_03, uav2) are legitimate.
    return bool(re.search(r'(?i)(?:^|[/_.\-])(tank|vehicle|truck|jeep|apc|ifv|uav|drone|helicopter|aircraft|chariot|car)[0-9]+(?:$|[/_.\-])', raw))


def repaired_family(current: str, tok: set[str], low: str) -> tuple[str,str,str|None]:
    strong_vehicle=has_vehicle_subject(tok,low)
    if strong_vehicle:
        sub='unknown'
        for label,candidates in [
            ('tank',{'tank','tanks'}),('aircraft',{'aircraft','airplane','aeroplane','plane','planes'}),
            ('helicopter',{'helicopter','helicopters','chopper'}),('drone-uav',{'drone','drones','uav'}),
            ('truck',{'truck','trucks'}),('armored',{'apc','ifv','humvee','armoredcar','armouredcar'}),
            ('car',{'car','cars'}),('chariot',{'chariot','chariots'})]:
            if tok & candidates:
                sub=label;break
        return 'vehicles',sub,'semantic-token-boundary:vehicle'

    # Only demote rows that were called vehicles without any actual vehicle subject.
    if current != 'vehicles':
        return current,'',None
    if tok & UI_TOKENS or '/ui/' in low or '/atlas/' in low or '/sprites/' in low or '/prefabs/ui/' in low:
        return 'ui','interface','semantic-correction:false-vehicle-ui'
    if tok & EFFECT_TOKENS:
        return 'effects','visual-effect','semantic-correction:false-vehicle-effect'
    if tok & WEAPON_TOKENS:
        return 'weapons-equipment','unknown','semantic-correction:false-vehicle-weapon'
    if tok & CHARACTER_TOKENS:
        return 'characters','character','semantic-correction:false-vehicle-character'
    if tok & BUILDING_TOKENS:
        return 'buildings','unknown','semantic-correction:false-vehicle-building'
    if tok & WORLD_TOKENS:
        return 'world-environment','unknown','semantic-correction:false-vehicle-world'
    return 'unknown','unknown','semantic-correction:false-vehicle-no-subject'


def suffix(path: str) -> str:
    p=(path or '').replace('\\','/').lower()
    for ext in sorted(MODEL_EXTS|PREFAB_EXTS|MATERIAL_EXTS|ANIM_EXTS|IMAGE_EXTS,key=len,reverse=True):
        if p.endswith(ext):return ext
    return Path(p).suffix.lower()


def rebuild_facets(con):
    axes=[
        ('family','family','unknown'),('subfamily','subfamily','unknown'),
        ('graphic_class','graphic_class','Indéterminé'),('dimension_class','dimension_class','Indéterminé'),
        ('model_role','model_role','unknown')
    ]
    con.execute("DELETE FROM facets WHERE axis IN (%s)" % ','.join('?'*len(axes)), tuple(x[0] for x in axes))
    for axis,col,default in axes:
        for value,count in con.execute(f"SELECT coalesce({col},?),count(*) FROM assets GROUP BY coalesce({col},?)",(default,default)):
            con.execute('INSERT INTO facets(axis,value,count) VALUES(?,?,?)',(axis,value,count))


def main():
    con=sqlite3.connect(DB);con.row_factory=sqlite3.Row
    before_vehicles=con.execute("SELECT count(*) FROM assets WHERE family='vehicles'").fetchone()[0]
    counts=Counter();changed_dim=0;changed_family=0
    rows=con.execute('''SELECT stable_id,asset_path,logical_name,alias_name,subject,family,subfamily,
                              graphic_class,dimension_class,model_role,tech_kind,visual_role
                       FROM assets''').fetchall()
    for r in rows:
        path=str(r['asset_path'] or '')
        logical=str(r['logical_name'] or '')
        alias=str(r['alias_name'] or '')
        subject=str(r['subject'] or '')
        low=' '.join([path,logical,alias,subject]).lower().replace('\\','/')
        tok=tokens(path,logical,alias,subject)
        ext=suffix(path)

        old_family=str(r['family'] or 'unknown').lower()
        family,subfamily,family_ev=repaired_family(old_family,tok,low)
        if family_ev and (family!=old_family or (subfamily and subfamily!=str(r['subfamily'] or ''))):
            con.execute('UPDATE assets SET family=?,subfamily=?,family_conf=? WHERE stable_id=?',
                        (family,subfamily or 'unknown',0.97,r['stable_id']))
            changed_family+=1
        elif not family_ev:
            family=old_family

        # UI paths are not 3D merely because an earlier family classifier said vehicles.
        explicit3d=any(t in low for t in THREE_D_MARKERS)
        uiish=('/ui/' in f'/{low}/' or '/prefabs/ui/' in f'/{low}/' or '/atlas/' in f'/{low}/' or
               '/sprites/' in f'/{low}/' or bool(tok & UI_TOKENS))
        is3d=explicit3d or (family in FAMILY_3D and not uiish)

        gclass=r['graphic_class'];dclass=r['dimension_class'];role=r['model_role'];ev=None
        if ext in IMAGE_EXTS:
            gclass='Graphique';dclass='2D';role='texture' if is3d else '2d-image';ev='file-extension:'+ext
        elif ext in MODEL_EXTS:
            gclass='Composant graphique';dclass='3D';role='geometry';ev='model-extension:'+ext
        elif ext in PREFAB_EXTS:
            gclass='Composant graphique'
            if uiish and not explicit3d:
                dclass='Composant 2D';role='ui-prefab';ev='ui-prefab-extension'
            else:
                dclass='Composant 3D' if is3d else 'Mixte 2D/3D';role='prefab';ev='prefab-extension'
        elif ext in MATERIAL_EXTS:
            gclass='Composant graphique'
            if uiish and not explicit3d:
                dclass='Composant 2D';role='ui-shader' if ext=='.shader' else 'ui-material';ev='ui-material-extension:'+ext
            else:
                dclass='Composant 3D' if is3d else 'Mixte 2D/3D';role='shader' if ext=='.shader' else 'material';ev='material-extension:'+ext
        elif ext in ANIM_EXTS:
            gclass='Composant graphique'
            if uiish and not explicit3d:
                dclass='Composant 2D';role='ui-animation';ev='ui-animation-extension:'+ext
            else:
                dclass='Composant 3D' if is3d else 'Mixte 2D/3D';role='animation';ev='animation-extension:'+ext

        if ev and (gclass!=r['graphic_class'] or dclass!=r['dimension_class'] or role!=r['model_role']):
            evidence=[ev]
            if family_ev:evidence.append(family_ev)
            con.execute('''UPDATE assets SET graphic_class=?,is_graphic=?,graphic_conf=?,graphic_evidence_json=?,
                           dimension_class=?,dimension_conf=?,dimension_evidence_json=?,model_role=? WHERE stable_id=?''',(
                gclass,1 if gclass=='Graphique' else None,0.995,json.dumps(evidence,ensure_ascii=False,separators=(',',':')),
                dclass,0.995,json.dumps(evidence,ensure_ascii=False,separators=(',',':')),role,r['stable_id']))
            changed_dim+=1
        counts[dclass]+=1

    rebuild_facets(con);con.commit()
    after_vehicles=con.execute("SELECT count(*) FROM assets WHERE family='vehicles'").fetchone()[0]
    true_vehicle_2d=con.execute("SELECT count(*) FROM assets WHERE family='vehicles' AND dimension_class='2D'").fetchone()[0]
    ui_prefab_3d=con.execute("SELECT count(*) FROM assets WHERE lower(asset_path) like '%/prefabs/ui/%' AND dimension_class IN ('3D','Composant 3D')").fetchone()[0]
    con.close()
    print('V33_SEMANTIC_CORRECT_READY',f'vehiclesBefore={before_vehicles}',f'vehiclesAfter={after_vehicles}',
          f'vehicle2D={true_vehicle_2d}',f'familyChanged={changed_family}',f'uiPrefab3D={ui_prefab_3d}',flush=True)
    print('V33_DIMENSION_CORRECT_READY',f'changed={changed_dim}',json.dumps(counts,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
