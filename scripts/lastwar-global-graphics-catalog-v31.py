#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from collections import Counter, defaultdict
import csv, hashlib, json, re, sqlite3, sys, time, unicodedata

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
TSV = ROOT / 'frontend/lab/master-assets-v2/index/lastwar-graphics-asset-path-index-v1.tsv'
TAXONOMY = ROOT / 'frontend/lab/global-graphics-v31/taxonomy-v31.json'
CACHE = Path.home() / '.cache/wfgg-lastwar-v31'
DB = CACHE / 'graphics-catalog-v31.sqlite3'
SUMMARY = CACHE / 'graphics-catalog-v31-summary.json'
BATCH = 3000

if not TSV.is_file():
    raise SystemExit(f'INDEX TSV introuvable: {TSV}')
if not TAXONOMY.is_file():
    raise SystemExit(f'Taxonomie introuvable: {TAXONOMY}')
CACHE.mkdir(parents=True, exist_ok=True)
taxonomy = json.loads(TAXONOMY.read_text('utf-8'))


def norm(s: object) -> str:
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode('ascii').lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def compact(s: object) -> str:
    return norm(s).replace(' ', '')


def as_int(v: object, default: int = -1) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def first_field(r: dict, *names: str) -> str:
    for n in names:
        v = r.get(n)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ''


def contains_any(text: str, terms) -> list[str]:
    hits = []
    padded = f' {text} '
    dense = text.replace(' ', '')
    for t in terms:
        nt = norm(t)
        if not nt:
            continue
        if f' {nt} ' in padded or nt.replace(' ', '') in dense:
            hits.append(str(t))
    return hits


FAMILY_RULES = [
    ('characters', ['hero','character','herospin','heroshow','heroicon','portrait','audie','murphy','williams','kimberly','marshall','stetman','mcgregor']),
    ('vehicles', ['vehicle','vehicles','car','cars','tank','aircraft','plane','helicopter','missile','uav','drone','truck','chariot','garage']),
    ('buildings', ['building','buildings','build','basebuilding','citybuilding','headquarter','headquarters','hq']),
    ('weapons-equipment', ['weapon','weapons','equipment','equip','gear','zhuanwu','exclusiveweapon','armour','armor']),
    ('units', ['soldier','troop','unit','units','army','squad']),
    ('objects-resources', ['resource','resources','item','items','reward','rewards','chest','box','coin','diamond','food','iron','gold']),
    ('world-environment', ['world','map','terrain','ground','environment','scene','city','grass','road','desert','snow']),
    ('effects', ['effect','effects','eff','particle','smoke','fire','explosion','fx','vfx']),
    ('ui', ['ui','icon','icons','button','btn','frame','panel','badge','atlas','sprite']),
]
ROLE_RULES = [
    ('portrait', ['portrait','heroicon','hero icon','headicon','avatar']),
    ('icon', ['icon','ico','smallicon','bigicon']),
    ('background', ['background','bg','backdrop']),
    ('frame', ['frame','border','kuang']),
    ('button', ['button','btn']),
    ('badge', ['badge','medal','rankicon']),
    ('loading', ['loading','loadscreen','splash']),
    ('sprite-atlas', ['atlas','spriteatlas']),
    ('texture', ['texture','tex']),
    ('effect', ['effect','eff','particle','fx','vfx','smoke','explosion']),
    ('illustration', ['illustration','poster','banner','cover','picture','pic']),
]
CONTEXT_RULES = [
    ('hero', ['hero','heroshow','herodetail','heroexhibit']),
    ('formation', ['formation','squad','herosquad','squadequip']),
    ('combat', ['fight','battle','combat','war']),
    ('base', ['base','city','building','headquarter','hq']),
    ('world-map', ['worldmap','bigmap','world map','mapworld']),
    ('alliance', ['alliance','guild']),
    ('shop', ['shop','store','mall']),
    ('inventory', ['inventory','bag','warehouse']),
    ('mission', ['mission','quest','task']),
    ('reward', ['reward','rewards','chest']),
    ('tutorial', ['tutorial','guide','newbie']),
]
TECH_RULES = [
    ('sprite', ['sprite']), ('texture2d', ['texture2d','texture']), ('atlas', ['atlas']),
    ('material', ['material']), ('prefab', ['prefab']), ('mesh', ['mesh']),
    ('animation', ['animation','animclip']), ('animator', ['animator','controller']),
    ('render-target', ['rendertexture','render target']), ('shader', ['shader'])
]
STATE_RULES = [
    ('locked', ['locked','lock']), ('disabled', ['disabled','disable','grey','gray']),
    ('selected', ['selected','select','active']), ('destroyed', ['destroyed','broken','wreck']),
    ('awakened', ['awaken','awakened']), ('zombie', ['zombie']), ('normal', ['normal','default'])
]
LANG_RULES = [('jp',['_jp',' japan ']),('kr',['_kr',' korea ']),('cn',['_cn']),('tw',['_tw']),('en',['_en']),('fr',['_fr']),('it',['_it']),('es',['_es'])]


def classify_one(text: str, rules, default='unknown'):
    best = (default, [], 0.0)
    for label, terms in rules:
        hits = contains_any(text, terms)
        if hits:
            score = min(0.99, 0.70 + 0.07 * len(hits))
            if score > best[2]:
                best = (label, hits, score)
    return best


def discover_scope(raw_text: str, normalized: str):
    # Scope is deliberately independent from family/context. Lack of an event token
    # is NOT evidence that an asset is generic.
    segments = [x for x in re.split(r'[/\\._\-\s]+', raw_text.lower()) if x]
    evidence = []
    kind, sid, name, period, conf = 'unknown', '', '', '', 0.0

    inter_hits = contains_any(normalized, taxonomy['scopeDiscovery']['interseasonTokens'])
    if inter_hits:
        return 'interseason', 'interseason', 'Inter-Saison', '', 0.95, ['token:' + x for x in inter_hits]

    season_match = re.search(r'(?i)(?:season|saison)[_\- /]?([0-9]{1,2})', raw_text)
    if season_match:
        n = season_match.group(1)
        return 'season', 'season-' + n, 'Saison ' + n, n, 0.99, ['regex:season-number']

    season_hits = contains_any(normalized, taxonomy['scopeDiscovery']['seasonAnchors'])
    if season_hits:
        return 'season', 'season-unknown', 'Saison non identifiée', '', 0.83, ['token:' + x for x in season_hits]

    anchors = set(taxonomy['scopeDiscovery']['eventAnchors'])
    for i, seg in enumerate(segments[:-1]):
        if seg in anchors:
            candidate = segments[i+1]
            if candidate and candidate not in {'ui','icon','icons','prefab','texture','textures','common','main'}:
                sid = re.sub(r'[^a-z0-9]+','-', candidate).strip('-')
                return 'event', sid, candidate, '', 0.90, [f'path-anchor:{seg}/{candidate}']
    event_hits = contains_any(normalized, taxonomy['scopeDiscovery']['eventAnchors'])
    if event_hits:
        return 'event', 'event-unknown', 'Événement non identifié', '', 0.72, ['token:' + x for x in event_hits]

    collab = contains_any(normalized, taxonomy['scopeDiscovery']['collaborationTokens'])
    if collab:
        return 'collaboration', 'collaboration', 'Collaboration', '', 0.92, ['token:' + x for x in collab]
    limited = contains_any(normalized, taxonomy['scopeDiscovery']['limitedTokens'])
    if limited:
        return 'limited', 'limited', 'Temps limité', '', 0.86, ['token:' + x for x in limited]
    regional = contains_any(raw_text.lower(), taxonomy['scopeDiscovery']['regionalTokens'])
    if regional:
        return 'regional', regional[0].strip('_'), regional[0].strip('_').upper(), '', 0.86, ['suffix:' + x for x in regional]
    generic = contains_any(normalized, taxonomy['scopeDiscovery']['genericTokens'])
    if generic:
        return 'generic', 'generic', 'Jeu générique', '', 0.78, ['token:' + x for x in generic]

    # Permanent modules are useful as a separate scope when explicit.
    feature_terms = ['hero','formation','alliance','inventory','shop','worldmap','basebuilding']
    feature_hits = contains_any(normalized, feature_terms)
    if feature_hits:
        return 'feature', re.sub(r'[^a-z0-9]+','-', norm(feature_hits[0])), feature_hits[0], '', 0.72, ['feature-token:' + x for x in feature_hits]
    return kind, sid, name, period, conf, evidence


def infer_subject(text: str, family: str) -> str:
    # Keep a conservative subject: explicit model/icon name tail when possible.
    words = [w for w in text.split() if len(w) > 2]
    stop = {'gameres','main','file','auto','assets','lastwar','texture','prefab','material','sprite','icon','icons','bundle','asset','art','dir','ui','common'}
    candidates = [w for w in words if w not in stop]
    if not candidates:
        return ''
    priority = {
        'vehicles': {'tank','aircraft','plane','helicopter','missile','uav','drone','truck','car'},
        'characters': {'murphy','audie','williams','kimberly','marshall','stetman','mcgregor'},
    }.get(family, set())
    for w in candidates:
        if w in priority:
            return w
    return candidates[-1][:80]


def stable_id(r: dict, asset_path: str, logical: str, alias: str) -> str:
    key = '|'.join([
        first_field(r,'tableFragment','fragment','fragmentEntry'),
        first_field(r,'bundleId','bundle_id'),
        first_field(r,'offset'), asset_path, logical, alias,
    ])
    return 'LWGA-' + hashlib.sha1(key.encode('utf-8','replace')).hexdigest()[:14].upper()


def create_schema(con):
    con.executescript('''
    PRAGMA journal_mode=WAL;
    PRAGMA synchronous=NORMAL;
    PRAGMA temp_store=MEMORY;
    DROP TABLE IF EXISTS assets;
    DROP TABLE IF EXISTS aliases;
    DROP TABLE IF EXISTS facets;
    DROP TABLE IF EXISTS asset_fts;
    CREATE TABLE assets(
      stable_id TEXT PRIMARY KEY, row_no INTEGER, bundle_id INTEGER, offset_bytes INTEGER, span_bytes INTEGER,
      fragment_entry TEXT, table_fragment TEXT, asset_path TEXT, logical_name TEXT, alias_name TEXT,
      family TEXT, subfamily TEXT, subject TEXT, visual_role TEXT, context TEXT, tech_kind TEXT,
      state TEXT, variant TEXT, language TEXT,
      scope_kind TEXT, scope_id TEXT, scope_name TEXT, scope_period TEXT,
      family_conf REAL, role_conf REAL, context_conf REAL, scope_conf REAL,
      confidence REAL, evidence_json TEXT, search_text TEXT
    );
    CREATE TABLE aliases(alias TEXT PRIMARY KEY, expansion_json TEXT NOT NULL);
    CREATE TABLE facets(axis TEXT, value TEXT, count INTEGER, PRIMARY KEY(axis,value));
    CREATE INDEX idx_assets_bundle ON assets(bundle_id);
    CREATE INDEX idx_assets_family ON assets(family);
    CREATE INDEX idx_assets_role ON assets(visual_role);
    CREATE INDEX idx_assets_context ON assets(context);
    CREATE INDEX idx_assets_scope_kind ON assets(scope_kind);
    CREATE INDEX idx_assets_scope_id ON assets(scope_id);
    CREATE INDEX idx_assets_tech ON assets(tech_kind);
    ''')
    try:
        con.execute('CREATE VIRTUAL TABLE asset_fts USING fts5(stable_id UNINDEXED, search_text, tokenize="unicode61 remove_diacritics 2")')
        return True
    except sqlite3.OperationalError:
        return False


def main():
    start = time.time()
    tmp = DB.with_suffix('.tmp.sqlite3')
    if tmp.exists(): tmp.unlink()
    con = sqlite3.connect(tmp)
    fts = create_schema(con)
    for alias, expansion in taxonomy.get('searchAliases',{}).items():
        con.execute('INSERT INTO aliases(alias,expansion_json) VALUES(?,?)',(norm(alias),json.dumps(expansion,ensure_ascii=False)))

    counters = defaultdict(Counter)
    rows_out = []
    fts_out = []
    seen = set()
    total = duplicates = 0

    with TSV.open('r', encoding='utf-8', errors='replace', newline='') as fh:
        reader = csv.DictReader(fh, delimiter='\t')
        print('V31_CATALOG_FIELDS', ','.join(reader.fieldnames or []), flush=True)
        for row_no, r in enumerate(reader, 1):
            asset_path = first_field(r,'assetPath','asset_path','path')
            logical = first_field(r,'logicalName','logical_name','bundleName')
            alias = first_field(r,'aliasName','alias_name','name')
            fragment_entry = first_field(r,'fragmentEntry','fragment_entry')
            table_fragment = first_field(r,'tableFragment','table_fragment','fragment')
            raw = ' '.join(x for x in [asset_path,logical,alias,fragment_entry,table_fragment] if x)
            text = norm(raw)
            sid = stable_id(r, asset_path, logical, alias)
            if sid in seen:
                duplicates += 1
                continue
            seen.add(sid)

            family, fev, fconf = classify_one(text,FAMILY_RULES)
            role, rev, rconf = classify_one(text,ROLE_RULES)
            context, cev, cconf = classify_one(text,CONTEXT_RULES)
            tech, tev, tconf = classify_one(text,TECH_RULES)
            state, sev, sconf = classify_one(text,STATE_RULES)
            lang, lev, lconf = classify_one(raw.lower(),LANG_RULES, default='')
            scope_kind, scope_id, scope_name, scope_period, scope_conf, scope_ev = discover_scope(raw,text)
            subject = infer_subject(text,family)

            # Useful but intentionally conservative subfamilies.
            subfamily = 'unknown'
            if family == 'vehicles':
                subfamily, subev, _ = classify_one(text,[
                    ('tank',['tank']),('aircraft',['aircraft','plane']),('helicopter',['helicopter']),
                    ('missile',['missile']),('drone-uav',['drone','uav']),('truck',['truck']),('car',['car','cars'])])
            elif family == 'characters':
                subfamily = 'hero' if contains_any(text,['hero','audie','murphy','williams','kimberly']) else 'character'
            elif family == 'ui':
                subfamily = role if role != 'unknown' else 'ui-generic'
            elif family == 'effects': subfamily = 'visual-effect'

            variant_hits = [w for w in text.split() if w in {'zw','jp','awaken','awakened','zombie','high','low','skin'}]
            variant = ','.join(sorted(set(variant_hits)))
            confidence_parts = [x for x in [fconf,rconf,cconf,scope_conf] if x > 0]
            confidence = round(sum(confidence_parts)/len(confidence_parts),3) if confidence_parts else 0.0
            evidence = {
                'family': fev, 'visualRole': rev, 'context': cev, 'technical': tev,
                'state': sev, 'language': lev, 'scope': scope_ev,
                'policy': 'unknown-is-not-generic'
            }
            searchable = ' '.join(filter(None,[sid,text,family,subfamily,subject,role,context,tech,state,variant,lang,scope_kind,scope_id,scope_name]))
            vals = (
                sid,row_no,as_int(first_field(r,'bundleId','bundle_id')),as_int(first_field(r,'offset','offsetBytes')),
                as_int(first_field(r,'spanBytes','span_bytes','length')),fragment_entry,table_fragment,asset_path,logical,alias,
                family,subfamily,subject,role,context,tech,state,variant,lang,scope_kind,scope_id,scope_name,scope_period,
                fconf,rconf,cconf,scope_conf,confidence,json.dumps(evidence,ensure_ascii=False,separators=(',',':')),searchable
            )
            rows_out.append(vals)
            if fts: fts_out.append((sid,searchable))
            total += 1
            for axis,value in [('family',family),('subfamily',subfamily),('visual_role',role),('context',context),('tech_kind',tech),('scope_kind',scope_kind),('scope_id',scope_id or 'unknown'),('language',lang or 'unknown')]:
                counters[axis][value] += 1
            if len(rows_out) >= BATCH:
                con.executemany('INSERT INTO assets VALUES('+','.join('?'*30)+')',rows_out)
                if fts: con.executemany('INSERT INTO asset_fts(stable_id,search_text) VALUES(?,?)',fts_out)
                con.commit(); rows_out.clear(); fts_out.clear()
                if total % 30000 < BATCH: print('V31_CATALOG_PROGRESS', total, flush=True)

    if rows_out:
        con.executemany('INSERT INTO assets VALUES('+','.join('?'*30)+')',rows_out)
        if fts: con.executemany('INSERT INTO asset_fts(stable_id,search_text) VALUES(?,?)',fts_out)
    for axis, values in counters.items():
        con.executemany('INSERT INTO facets(axis,value,count) VALUES(?,?,?)',[(axis,k,v) for k,v in values.items()])
    con.commit()
    try: con.execute('PRAGMA optimize')
    except Exception: pass
    con.close()
    if DB.exists(): DB.unlink()
    tmp.replace(DB)

    summary = {
        'schemaVersion':31,'generatedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        'source':str(TSV.relative_to(ROOT)),'database':str(DB),'assets':total,'stableIdDuplicatesSkipped':duplicates,
        'fts5':fts,'seconds':round(time.time()-start,3),
        'facets':{axis:dict(values.most_common()) for axis,values in counters.items()},
        'policy':{'unknownIsNotGeneric':True,'multiAxis':True,'scopeEvidenceRequired':True}
    }
    SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2),'utf-8')
    print('V31_CATALOG_READY', f'assets={total}', f'db={DB}', f'fts5={fts}', f'seconds={summary["seconds"]}', flush=True)
    print('V31_SCOPE_COUNTS', json.dumps(summary['facets'].get('scope_kind',{}),ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()
