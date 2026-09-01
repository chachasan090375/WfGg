#!/usr/bin/env python3
from pathlib import Path
from collections import Counter, defaultdict
import json, re, sqlite3, sys, unicodedata

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
DB = Path.home() / '.cache/wfgg-lastwar-v31/graphics-catalog-v31.sqlite3'
TAX = ROOT / 'frontend/lab/global-graphics-v31/taxonomy-v31.json'
if not DB.is_file():
    raise SystemExit(f'Catalogue absent: {DB}')

tax = json.loads(TAX.read_text('utf-8'))
registry_rel = tax.get('eventRegistry', {}).get('index', 'data/lastwar/event-registry-v1.json')
REGISTRY = ROOT / registry_rel
if not REGISTRY.is_file():
    raise SystemExit(f'Registre événements absent: {REGISTRY}')


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def compact(s):
    return norm(s).replace(' ', '')


def load_registry():
    index = json.loads(REGISTRY.read_text('utf-8'))
    events = []
    seen = set()
    for item in index.get('files', []):
        p = REGISTRY.parent / item['path']
        if not p.is_file():
            raise SystemExit(f'Fichier registre absent: {p}')
        doc = json.loads(p.read_text('utf-8'))
        defaults = doc.get('defaults') or {}
        file_events = doc.get('events') or []
        expected = item.get('entries')
        if expected is not None and int(expected) != len(file_events):
            raise SystemExit(f'Compteur registre incohérent {p.name}: attendu={expected} réel={len(file_events)}')
        for raw in file_events:
            ev = dict(defaults)
            ev.update(raw)
            eid = str(ev.get('id') or '').strip()
            if not eid:
                raise SystemExit(f'Event sans id dans {p.name}')
            if eid in seen:
                raise SystemExit(f'Event id dupliqué: {eid}')
            seen.add(eid)
            ev.setdefault('name', eid)
            ev.setdefault('kind', 'event')
            ev.setdefault('category', 'event')
            ev.setdefault('phase', 'core')
            ev.setdefault('seasons', [])
            ev.setdefault('cadence', 'irregular')
            ev.setdefault('confidence', 'high')
            ev.setdefault('aliases', [])
            ev.setdefault('assetTokens', [])
            ev.setdefault('sourceKeys', [])
            ev['_registry_file'] = item['path']
            events.append(ev)
    expected_total = index.get('countingPolicy', {}).get('registryEntries')
    if expected_total is not None and int(expected_total) != len(events):
        raise SystemExit(f'Compteur registre global incohérent: attendu={expected_total} réel={len(events)}')
    return index, events


REGISTRY_INDEX, EVENTS = load_registry()


def fts_phrases(term):
    """Return conservative FTS5 phrase expressions for one curated term."""
    n = norm(term)
    if not n:
        return []
    toks = n.split()
    # Never auto-classify on a tiny generic token.
    if len(toks) == 1 and len(toks[0]) < 6:
        return []
    out = ['"' + ' '.join(toks) + '"']
    # Season-specific curated tokens often use s6_* while raw game paths may say season_6_*.
    if len(toks) >= 2 and re.fullmatch(r's[1-9][0-9]?', toks[0]):
        num = toks[0][1:]
        out.append('"' + ' '.join(['season', num] + toks[1:]) + '"')
    return list(dict.fromkeys(out))


def candidate_terms(ev):
    """Curated tokens are strongest; canonical names/aliases are lower-priority fallbacks."""
    out = []
    for t in ev.get('assetTokens') or []:
        if t and norm(t):
            out.append(('asset-token', t))
    name = ev.get('name') or ''
    if name and len(norm(name).split()) >= 2:
        out.append(('canonical-name', name))
    for a in ev.get('aliases') or []:
        if a and len(norm(a).split()) >= 2:
            out.append(('alias', a))
    seen = set()
    clean = []
    for source, term in out:
        key = (source, norm(term))
        if key not in seen:
            seen.add(key)
            clean.append((source, term))
    return clean


def match_score(ev, source, term):
    toks = norm(term).split()
    if source == 'asset-token':
        if len(toks) >= 3:
            score = 0.995
        elif len(toks) == 2:
            score = 0.985
        else:
            score = 0.96 if len(toks[0]) >= 10 else 0.93
    elif source == 'canonical-name':
        score = 0.94 if len(toks) >= 3 else 0.92
    else:
        score = 0.90
    if ev.get('confidence') == 'medium':
        score = min(score, 0.88)
    if ev.get('seasons') and any(re.search(rf'(^|[^0-9]){s}([^0-9]|$)', norm(term)) for s in ev.get('seasons', [])):
        score = min(0.999, score + 0.004)
    return round(score, 3)


con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
con.executescript('''
DROP TABLE IF EXISTS event_registry;
DROP TABLE IF EXISTS asset_event_links;
CREATE TABLE event_registry(
  event_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  category TEXT NOT NULL,
  phase TEXT NOT NULL,
  seasons_json TEXT NOT NULL,
  cadence TEXT NOT NULL,
  confidence TEXT NOT NULL,
  aliases_json TEXT NOT NULL,
  asset_tokens_json TEXT NOT NULL,
  source_keys_json TEXT NOT NULL,
  parent_event_id TEXT,
  notification_relevant INTEGER NOT NULL DEFAULT 1,
  registry_file TEXT NOT NULL
);
CREATE TABLE asset_event_links(
  stable_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  match_score REAL NOT NULL,
  evidence_json TEXT NOT NULL,
  PRIMARY KEY(stable_id,event_id,relation)
);
CREATE INDEX idx_event_registry_kind ON event_registry(kind);
CREATE INDEX idx_event_registry_phase ON event_registry(phase);
CREATE INDEX idx_asset_event_event ON asset_event_links(event_id,relation);
CREATE INDEX idx_asset_event_asset ON asset_event_links(stable_id,relation);
''')

con.executemany(
    'INSERT INTO event_registry VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
    [(
        ev['id'], ev['name'], ev['kind'], ev['category'], ev['phase'],
        json.dumps(ev.get('seasons') or [], ensure_ascii=False, separators=(',', ':')),
        ev.get('cadence') or 'irregular', ev.get('confidence') or 'high',
        json.dumps(ev.get('aliases') or [], ensure_ascii=False, separators=(',', ':')),
        json.dumps(ev.get('assetTokens') or [], ensure_ascii=False, separators=(',', ':')),
        json.dumps(ev.get('sourceKeys') or [], ensure_ascii=False, separators=(',', ':')),
        ev.get('parent'), 1 if ev.get('notificationRelevant', True) else 0,
        ev['_registry_file']
    ) for ev in EVENTS]
)

# Build exact direct-name matches. Multiple event links are preserved; one strongest link
# is selected only for the legacy primary scope_* columns used by the V31 viewer.
matched = defaultdict(lambda: {'score': 0.0, 'evidence': []})
fts_available = True
try:
    con.execute("SELECT count(*) FROM asset_fts WHERE asset_fts MATCH 'zzzz_wfgg_probe_zzzz'").fetchone()
except sqlite3.OperationalError:
    fts_available = False

for pos, ev in enumerate(EVENTS, 1):
    eid = ev['id']
    for source, term in candidate_terms(ev):
        score = match_score(ev, source, term)
        ids = set()
        if fts_available:
            for expr in fts_phrases(term):
                try:
                    for r in con.execute('SELECT stable_id FROM asset_fts WHERE asset_fts MATCH ?', (expr,)):
                        ids.add(r['stable_id'])
                except sqlite3.OperationalError:
                    pass
        else:
            n = norm(term)
            if n:
                like = '%' + n + '%'
                for r in con.execute('SELECT stable_id FROM assets WHERE lower(search_text) LIKE ?', (like,)):
                    ids.add(r['stable_id'])
        for sid in ids:
            key = (sid, eid)
            rec = matched[key]
            if score > rec['score']:
                rec['score'] = score
            marker = {'source': source, 'term': term, 'score': score}
            if marker not in rec['evidence']:
                rec['evidence'].append(marker)
    if pos % 25 == 0:
        print('V31_EVENT_REGISTRY_MATCH_PROGRESS', pos, '/', len(EVENTS), 'links=', len(matched), flush=True)

link_rows = []
primary = {}
confidence_rank = {'high': 2, 'medium': 1}
for (sid, eid), rec in matched.items():
    ev = next(x for x in EVENTS if x['id'] == eid)
    evidence = {
        'registry': REGISTRY_INDEX.get('registryVersion'),
        'relation': 'belongs-to',
        'eventId': eid,
        'matches': rec['evidence'],
        'sourceKeys': ev.get('sourceKeys') or []
    }
    link_rows.append((sid, eid, 'belongs-to', rec['score'], json.dumps(evidence, ensure_ascii=False, separators=(',', ':'))))
    rank = (
        rec['score'],
        1 if ev.get('seasons') else 0,
        confidence_rank.get(ev.get('confidence'), 0),
        len(norm(ev.get('name')).split()),
        eid
    )
    if sid not in primary or rank > primary[sid][0]:
        primary[sid] = (rank, ev, rec)

if link_rows:
    con.executemany('INSERT INTO asset_event_links VALUES(?,?,?,?,?)', link_rows)

updated = 0
for sid, (_rank, ev, rec) in primary.items():
    row = con.execute('SELECT evidence_json FROM assets WHERE stable_id=?', (sid,)).fetchone()
    try:
        evidence = json.loads(row['evidence_json'] or '{}') if row else {}
    except Exception:
        evidence = {}
    registry_ev = list(evidence.get('eventRegistry') or [])
    registry_ev.append({
        'eventId': ev['id'],
        'relation': 'belongs-to',
        'score': rec['score'],
        'registryVersion': REGISTRY_INDEX.get('registryVersion'),
        'evidence': rec['evidence']
    })
    evidence['eventRegistry'] = registry_ev
    evidence['scope'] = ['event-registry-direct:' + ev['id']]
    evidence['scopeRecurrence'] = ev.get('cadence') or ''
    con.execute(
        'UPDATE assets SET scope_kind=?,scope_id=?,scope_name=?,scope_period=?,scope_conf=?,evidence_json=? WHERE stable_id=?',
        (ev['kind'], ev['id'], ev['name'], ev.get('cadence') or '', rec['score'],
         json.dumps(evidence, ensure_ascii=False, separators=(',', ':')), sid)
    )
    updated += 1

# Keep the previous generic recurring-token inference only for assets that still have no
# canonical event link. This can improve lifecycle classification but never invents an event id.
recurring = [norm(x) for x in tax.get('scopeDiscovery', {}).get('recurringTokens', []) if norm(x)]
recurrence_updates = 0
for tok in recurring:
    rows = con.execute(
        "SELECT a.stable_id,a.evidence_json FROM assets a "
        "WHERE a.scope_kind='event' AND lower(a.search_text) LIKE ? "
        "AND NOT EXISTS(SELECT 1 FROM asset_event_links l WHERE l.stable_id=a.stable_id AND l.relation='belongs-to')",
        ('%' + tok + '%',)
    ).fetchall()
    for row in rows:
        try:
            evidence = json.loads(row['evidence_json'] or '{}')
        except Exception:
            evidence = {}
        sev = list(evidence.get('scope') or [])
        marker = 'recurrence-token:' + tok
        if marker not in sev:
            sev.append(marker)
        evidence['scope'] = sev
        con.execute(
            "UPDATE assets SET scope_kind='recurring-event',scope_conf=max(scope_conf,0.90),evidence_json=? WHERE stable_id=?",
            (json.dumps(evidence, ensure_ascii=False, separators=(',', ':')), row['stable_id'])
        )
        recurrence_updates += 1

# Rebuild scope facets after canonical enrichment.
con.execute("DELETE FROM facets WHERE axis IN ('scope_kind','scope_id')")
for axis in ('scope_kind', 'scope_id'):
    counts = Counter()
    for value, count in con.execute(f'SELECT {axis},count(*) FROM assets GROUP BY {axis}'):
        counts[value or 'unknown'] = count
    con.executemany('INSERT INTO facets(axis,value,count) VALUES(?,?,?)', [(axis, k, v) for k, v in counts.items()])

con.commit()
registered = con.execute('SELECT count(*) FROM event_registry').fetchone()[0]
links = con.execute("SELECT count(*) FROM asset_event_links WHERE relation='belongs-to'").fetchone()[0]
matched_events = con.execute("SELECT count(DISTINCT event_id) FROM asset_event_links WHERE relation='belongs-to'").fetchone()[0]
con.close()
print('V31_EVENT_REGISTRY_READY', f'events={registered}', f'directLinks={links}', f'matchedEvents={matched_events}', f'primaryAssets={updated}', f'recurrenceUpdates={recurrence_updates}', flush=True)
