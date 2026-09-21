#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
MAIN = ROOT / 'connector-go/cmd/radar-connector/main.go'
SRC = ROOT / 'connector-go/cmd/radar-connector/player_intelligence_v620.go'
TEST = ROOT / 'connector-go/cmd/radar-connector/player_intelligence_v620_test.go'

main = MAIN.read_text(encoding='utf-8')
marker = 'WFGG_RADAR_PLAYER_INTELLIGENCE_ROUTE_V620'
if marker not in main:
    anchors = [
        '\tmux.HandleFunc("GET /v1/collector/server-census", s.signed(s.serverCensusV612))\n',
        '\tmux.HandleFunc("GET /v1/collector/identity/lookup", s.signed(s.collectorFastLookupV611))\n',
    ]
    for anchor in anchors:
        if main.count(anchor) == 1:
            main = main.replace(
                anchor,
                anchor + '\t// ' + marker + '\n\tmux.HandleFunc("POST /v1/collector/intelligence/search", s.signed(s.playerIntelligenceSearchV620))\n',
                1,
            )
            break
    else:
        raise SystemExit('V620_PLAYER_INTELLIGENCE_ROUTE_ANCHOR_MISSING')
MAIN.write_text(main, encoding='utf-8')

SRC.write_text(r'''package main

import (
    "context"
    "encoding/json"
    "errors"
    "net/http"
    "os"
    "os/exec"
    "strings"
    "time"
)

// WFGG_RADAR_PLAYER_INTELLIGENCE_V620
// Local-only recruitment/search engine. It reads the Collector SQLite database
// in query_only mode. It never contacts Last War and never mutates game state.
type playerIntelligenceRequestV620 struct {
    Query               string   `json:"query,omitempty"`
    Mode                string   `json:"mode,omitempty"`
    Limit               int      `json:"limit,omitempty"`
    Offset              int      `json:"offset,omitempty"`
    Servers             []string `json:"servers,omitempty"`
    ExcludeServers      []string `json:"excludeServers,omitempty"`
    Alliance            string   `json:"alliance,omitempty"`
    ExcludeAlliances    []string `json:"excludeAlliances,omitempty"`
    ExcludePlayers      []string `json:"excludePlayers,omitempty"`
    Country             string   `json:"country,omitempty"`
    MinPower            *int64   `json:"minPower,omitempty"`
    MaxPower            *int64   `json:"maxPower,omitempty"`
    MinHQ               *int     `json:"minHQ,omitempty"`
    MaxHQ               *int     `json:"maxHQ,omitempty"`
    ObservedWithinDays  *int     `json:"observedWithinDays,omitempty"`
    ObservedOlderDays   *int     `json:"observedOlderDays,omitempty"`
    MinArmyPower        *int64   `json:"minArmyPower,omitempty"`
    MaxArmyPower        *int64   `json:"maxArmyPower,omitempty"`
    MinKills            *int64   `json:"minKills,omitempty"`
    MinSVIP             *int     `json:"minSVIP,omitempty"`
    Sort                string   `json:"sort,omitempty"`
}

type playerIntelligencePayloadV620 struct {
    OK         bool           `json:"ok"`
    Version    string         `json:"version,omitempty"`
    Readonly   bool           `json:"readonly"`
    Source     string         `json:"source,omitempty"`
    Total      int            `json:"total,omitempty"`
    Count      int            `json:"count,omitempty"`
    Players    []map[string]any `json:"players,omitempty"`
    Alliances  []map[string]any `json:"alliances,omitempty"`
    Capabilities map[string]bool `json:"capabilities,omitempty"`
    Schema     map[string]any  `json:"schema,omitempty"`
    Error      string         `json:"error,omitempty"`
}

const playerIntelligencePythonV620 = `
import json,sqlite3,sys

path=sys.argv[1]
req=json.loads(sys.argv[2])
conn=sqlite3.connect('file:'+path+'?mode=ro',uri=True)
conn.row_factory=sqlite3.Row
conn.execute('PRAGMA query_only=ON')

def qi(name):
    return '"' + str(name).replace('"','""') + '"'

def cols(table):
    return [r[1] for r in conn.execute('PRAGMA table_info('+qi(table)+')')]

def pick(columns,names):
    m={str(c).lower():c for c in columns}
    for n in names:
        if n.lower() in m:
            return m[n.lower()]
    return None

def txt(v):
    return '' if v is None else str(v).strip()

def uniq(values,maxn=100):
    out=[]; seen=set()
    for v in values or []:
        s=txt(v)
        if not s: continue
        k=s.lower()
        if k in seen: continue
        seen.add(k); out.append(s)
        if len(out)>=maxn: break
    return out

tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
schema={t:cols(t) for t in tables}
uid_names=['game_uid','gameUid','uid','player_uid','playerId','player_id','subject_uid']
pseudo_names=['pseudo','name','player_name','playerName','nickname']
server_names=['server_id','serverId','server','serverid','current_server']
alliance_id_names=['alliance_id','allianceId']
alliance_tag_names=['alliance_tag','allianceTag','alliance_abbr_name','allianceAbbrName','alliance_name']
x_names=['x','map_x','mapX','pos_x']
y_names=['y','map_y','mapY','pos_y']
hq_names=['hq_level','hqLevel','main_building_level','mainBuildingLevel','level','baseLevel']
power_names=['power','combat_power','combatPower','strength']
seen_names=['last_seen','lastSeen','observed_at','observedAt','updated_at','updatedAt']
country_names=['country','country_code','countryCode']
avatar_names=['avatar_ref','avatarRef','avatar','avatar_url','avatarUrl']
army_power_names=['army_power','armyPower']
kills_names=['army_kill','armyKill','kills']
svip_names=['svip_level','svipLevel','svip']

cycle_names=['cycle_id','cycleId','cycle','scan_cycle_id']

def player_score(t,c):
    score=0; low=t.lower()
    if low=='players': score+=200
    if 'player' in low: score+=50
    if pick(c,uid_names): score+=60
    if pick(c,pseudo_names): score+=60
    if pick(c,server_names): score+=20
    if pick(c,power_names): score+=10
    return score

pcands=[(player_score(t,schema[t]),t) for t in tables if pick(schema[t],uid_names) and pick(schema[t],pseudo_names)]
pcands.sort(reverse=True)
player_table=pcands[0][1] if pcands else None
if not player_table:
    print(json.dumps({'ok':False,'readonly':True,'error':'PLAYER_INDEX_UNAVAILABLE_V620'},separators=(',',':')))
    raise SystemExit(0)

def obs_score(t,c):
    score=0; low=t.lower()
    if low in ('observations','player_observations'): score+=200
    if 'observation' in low: score+=80
    if pick(c,uid_names): score+=40
    if pick(c,pseudo_names): score+=40
    if pick(c,cycle_names): score+=20
    return score

ocands=[(obs_score(t,schema[t]),t) for t in tables if pick(schema[t],uid_names) and pick(schema[t],pseudo_names)]
ocands.sort(reverse=True)
obs_table=ocands[0][1] if ocands else None

pc=schema[player_table]
uid=pick(pc,uid_names); pseudo=pick(pc,pseudo_names)
server=pick(pc,server_names); alliance_id=pick(pc,alliance_id_names); alliance_tag=pick(pc,alliance_tag_names)
xcol=pick(pc,x_names); ycol=pick(pc,y_names); hq=pick(pc,hq_names); power=pick(pc,power_names)
seen=pick(pc,seen_names); country=pick(pc,country_names); avatar=pick(pc,avatar_names)
army_power=pick(pc,army_power_names); kills=pick(pc,kills_names); svip=pick(pc,svip_names)

caps={
 'aliases': bool(obs_table),
 'server': bool(server),
 'alliance': bool(alliance_tag or alliance_id),
 'hq': bool(hq),
 'power': bool(power),
 'lastSeen': bool(seen),
 'country': bool(country),
 'avatar': bool(avatar),
 'armyPower': bool(army_power),
 'kills': bool(kills),
 'svip': bool(svip),
}

unsupported=[]
for key,requested in [
 ('server', bool(req.get('servers') or req.get('excludeServers'))),
 ('alliance', bool(req.get('alliance') or req.get('excludeAlliances'))),
 ('hq', req.get('minHQ') is not None or req.get('maxHQ') is not None),
 ('power', req.get('minPower') is not None or req.get('maxPower') is not None),
 ('lastSeen', req.get('observedWithinDays') is not None or req.get('observedOlderDays') is not None),
 ('country', bool(txt(req.get('country')))),
 ('armyPower', req.get('minArmyPower') is not None or req.get('maxArmyPower') is not None),
 ('kills', req.get('minKills') is not None),
 ('svip', req.get('minSVIP') is not None),
]:
    if requested and not caps[key]:
        unsupported.append(key)
if unsupported:
    print(json.dumps({'ok':False,'readonly':True,'error':'FILTER_UNSUPPORTED_V620:'+','.join(unsupported),'capabilities':caps},separators=(',',':')))
    raise SystemExit(0)

q=txt(req.get('query'))
qfold=q.lower()
alias_uids=[]
alias_matches={}
if q and obs_table:
    oc=schema[obs_table]; ouid=pick(oc,uid_names); opseudo=pick(oc,pseudo_names)
    if ouid and opseudo:
        like='%'+qfold+'%'
        sql='SELECT '+qi(ouid)+' uid,'+qi(opseudo)+' pseudo FROM '+qi(obs_table)+' WHERE lower(COALESCE('+qi(opseudo)+",'')) LIKE ? LIMIT 2500"
        for r in conn.execute(sql,(like,)):
            u=txt(r['uid']); p=txt(r['pseudo'])
            if u:
                alias_uids.append(u)
                if p and qfold in p.lower():
                    alias_matches.setdefault(u,p)
alias_uids=uniq(alias_uids,2000)

where=[]; params=[]
if q:
    ors=['lower(COALESCE('+qi(pseudo)+",'')) LIKE ?"]
    params.append('%'+qfold+'%')
    ors.append('CAST('+qi(uid)+' AS TEXT) = ?'); params.append(q)
    if alliance_tag:
        ors.append('lower(COALESCE('+qi(alliance_tag)+",'')) LIKE ?"); params.append('%'+qfold+'%')
    if alliance_id:
        ors.append('lower(COALESCE(CAST('+qi(alliance_id)+' AS TEXT),\'\')) LIKE ?'); params.append('%'+qfold+'%')
    if alias_uids:
        marks=','.join('?' for _ in alias_uids)
        ors.append('CAST('+qi(uid)+' AS TEXT) IN ('+marks+')'); params.extend(alias_uids)
    where.append('('+' OR '.join(ors)+')')

servers=uniq(req.get('servers'))
if servers:
    marks=','.join('?' for _ in servers)
    where.append('CAST('+qi(server)+' AS TEXT) IN ('+marks+')'); params.extend(servers)
exclude_servers=uniq(req.get('excludeServers'))
if exclude_servers:
    marks=','.join('?' for _ in exclude_servers)
    where.append('CAST('+qi(server)+' AS TEXT) NOT IN ('+marks+')'); params.extend(exclude_servers)

alliance_filter=txt(req.get('alliance'))
if alliance_filter:
    ors=[]
    if alliance_tag:
        ors.append('lower(COALESCE('+qi(alliance_tag)+",'')) LIKE ?"); params.append('%'+alliance_filter.lower()+'%')
    if alliance_id:
        ors.append('lower(COALESCE(CAST('+qi(alliance_id)+' AS TEXT),\'\')) LIKE ?'); params.append('%'+alliance_filter.lower()+'%')
    where.append('('+' OR '.join(ors)+')')

for a in uniq(req.get('excludeAlliances')):
    ors=[]
    if alliance_tag:
        ors.append('lower(COALESCE('+qi(alliance_tag)+",'')) = ?"); params.append(a.lower())
    if alliance_id:
        ors.append('lower(COALESCE(CAST('+qi(alliance_id)+' AS TEXT),\'\')) = ?'); params.append(a.lower())
    where.append('NOT ('+' OR '.join(ors)+')')

for p in uniq(req.get('excludePlayers')):
    where.append("(lower(COALESCE("+qi(pseudo)+",'') ) <> ? AND CAST("+qi(uid)+" AS TEXT) <> ?)")
    params.extend([p.lower(),p])

def add_num(col,op,key):
    val=req.get(key)
    if val is not None:
        where.append('CAST('+qi(col)+' AS INTEGER) '+op+' ?'); params.append(int(val))
if power:
    add_num(power,'>=','minPower'); add_num(power,'<=','maxPower')
if hq:
    add_num(hq,'>=','minHQ'); add_num(hq,'<=','maxHQ')
if army_power:
    add_num(army_power,'>=','minArmyPower'); add_num(army_power,'<=','maxArmyPower')
if kills:
    add_num(kills,'>=','minKills')
if svip:
    add_num(svip,'>=','minSVIP')

country_filter=txt(req.get('country')).upper()
if country_filter:
    if country_filter in ('FR','FRA','FRANCE'):
        where.append("upper(trim(COALESCE("+qi(country)+",''))) IN ('FR','FRA','FRANCE')")
    else:
        where.append("upper(trim(COALESCE("+qi(country)+",''))) = ?"); params.append(country_filter)

if seen:
    within=req.get('observedWithinDays')
    older=req.get('observedOlderDays')
    if within is not None:
        where.append("julianday("+qi(seen)+") >= julianday('now', ?)")
        params.append('-'+str(max(0,int(within)))+' days')
    if older is not None:
        where.append("julianday("+qi(seen)+") <= julianday('now', ?)")
        params.append('-'+str(max(0,int(older)))+' days')

where_sql=(' WHERE '+' AND '.join(where)) if where else ''
limit=max(1,min(int(req.get('limit') or 50),100))
offset=max(0,min(int(req.get('offset') or 0),10000))

sort=txt(req.get('sort') or 'power_desc').lower()
sort_map={
 'power_desc': (qi(power)+' DESC' if power else qi(pseudo)+' COLLATE NOCASE ASC'),
 'power_asc': (qi(power)+' ASC' if power else qi(pseudo)+' COLLATE NOCASE ASC'),
 'hq_desc': (qi(hq)+' DESC' if hq else qi(pseudo)+' COLLATE NOCASE ASC'),
 'observed_desc': (qi(seen)+' DESC' if seen else qi(pseudo)+' COLLATE NOCASE ASC'),
 'observed_asc': (qi(seen)+' ASC' if seen else qi(pseudo)+' COLLATE NOCASE ASC'),
 'army_desc': (qi(army_power)+' DESC' if army_power else (qi(power)+' DESC' if power else qi(pseudo)+' COLLATE NOCASE ASC')),
 'kills_desc': (qi(kills)+' DESC' if kills else (qi(power)+' DESC' if power else qi(pseudo)+' COLLATE NOCASE ASC')),
 'pseudo_asc': qi(pseudo)+' COLLATE NOCASE ASC',
}
order=sort_map.get(sort,sort_map['power_desc'])

def expr(col,alias):
    return (qi(col)+' AS '+alias) if col else ('NULL AS '+alias)

select=[
 expr(uid,'game_uid'),expr(pseudo,'pseudo'),expr(server,'server_id'),
 expr(alliance_id,'alliance_id'),expr(alliance_tag,'alliance_tag'),
 expr(xcol,'x'),expr(ycol,'y'),expr(hq,'hq_level'),expr(power,'power'),
 expr(seen,'last_seen'),expr(country,'country'),expr(avatar,'avatar_ref'),
 expr(army_power,'army_power'),expr(kills,'army_kill'),expr(svip,'svip_level'),
]
base=' FROM '+qi(player_table)+where_sql
total=int(conn.execute('SELECT COUNT(*)'+base,tuple(params)).fetchone()[0])
rows=list(conn.execute('SELECT '+','.join(select)+base+' ORDER BY '+order+' LIMIT ? OFFSET ?',tuple(params+[limit,offset])))

result_uids=[txt(r['game_uid']) for r in rows if txt(r['game_uid'])]
aliases={}
if obs_table and result_uids:
    oc=schema[obs_table]; ouid=pick(oc,uid_names); opseudo=pick(oc,pseudo_names); oseen=pick(oc,seen_names)
    if ouid and opseudo:
        marks=','.join('?' for _ in result_uids)
        osel=qi(ouid)+' uid,'+qi(opseudo)+' pseudo'+((','+qi(oseen)+' seen') if oseen else '')
        sql='SELECT '+osel+' FROM '+qi(obs_table)+' WHERE CAST('+qi(ouid)+' AS TEXT) IN ('+marks+')'
        for rr in conn.execute(sql,tuple(result_uids)):
            u=txt(rr['uid']); p=txt(rr['pseudo'])
            if not u or not p: continue
            aliases.setdefault(u,[])
            if p.lower() not in {x.lower() for x in aliases[u]}:
                aliases[u].append(p)

players=[]
for r in rows:
    d={k:r[k] for k in r.keys()}
    u=txt(d.get('game_uid')); current=txt(d.get('pseudo'))
    hist=[p for p in aliases.get(u,[]) if p.lower()!=current.lower()]
    matched_by='current'
    matched_alias=''
    if q:
        if qfold in current.lower(): matched_by='current'
        elif u==q: matched_by='uid'
        elif alliance_tag and qfold in txt(d.get('alliance_tag')).lower(): matched_by='alliance'
        elif alliance_id and qfold in txt(d.get('alliance_id')).lower(): matched_by='alliance'
        else:
            for a in hist:
                if qfold in a.lower():
                    matched_by='alias'; matched_alias=a; break
    players.append({
      'gameUid':u,'pseudo':current,'serverId':txt(d.get('server_id')),
      'allianceId':txt(d.get('alliance_id')),'allianceTag':txt(d.get('alliance_tag')),
      'x':d.get('x'),'y':d.get('y'),'hqLevel':d.get('hq_level'),'power':d.get('power'),
      'observedAt':txt(d.get('last_seen')),'country':txt(d.get('country')),
      'avatarRef':txt(d.get('avatar_ref')),'armyPower':d.get('army_power'),
      'armyKill':d.get('army_kill'),'svipLevel':d.get('svip_level'),
      'aliases':hist[:20],'matchedBy':matched_by,'matchedAlias':matched_alias,
    })

alliances=[]
if q and (alliance_tag or alliance_id):
    aw=[]; ap=[]
    if alliance_tag:
        aw.append('lower(COALESCE('+qi(alliance_tag)+",'')) LIKE ?"); ap.append('%'+qfold+'%')
    if alliance_id:
        aw.append('lower(COALESCE(CAST('+qi(alliance_id)+' AS TEXT),\'\')) LIKE ?'); ap.append('%'+qfold+'%')
    tag_expr=qi(alliance_tag) if alliance_tag else "''"
    id_expr=qi(alliance_id) if alliance_id else "''"
    sql='SELECT '+tag_expr+' alliance_tag,'+id_expr+' alliance_id,COUNT(*) members FROM '+qi(player_table)+' WHERE ('+' OR '.join(aw)+') GROUP BY '+tag_expr+','+id_expr+' ORDER BY members DESC LIMIT 20'
    for ar in conn.execute(sql,tuple(ap)):
        alliances.append({'allianceTag':txt(ar['alliance_tag']),'allianceId':txt(ar['alliance_id']),'members':int(ar['members'] or 0)})

payload={
 'ok':True,'version':'v6.20.0','readonly':True,'source':'collector-sqlite-local',
 'total':total,'count':len(players),'players':players,'alliances':alliances,
 'capabilities':caps,'schema':{'playerTable':player_table,'observationTable':obs_table or ''},
}
conn.close()
print(json.dumps(payload,separators=(',',':')))
`

func runPlayerIntelligenceV620(ctx context.Context, dbPath string, input playerIntelligenceRequestV620) (playerIntelligencePayloadV620, error) {
    if strings.TrimSpace(dbPath) == "" {
        return playerIntelligencePayloadV620{}, errors.New("COLLECTOR_DB_PATH_EMPTY")
    }
    if _, err := os.Stat(dbPath); err != nil {
        return playerIntelligencePayloadV620{}, errors.New("COLLECTOR_DB_UNAVAILABLE")
    }
    if _, err := exec.LookPath("python3"); err != nil {
        return playerIntelligencePayloadV620{}, errors.New("PLAYER_INTELLIGENCE_PYTHON3_MISSING_V620")
    }
    raw, _ := json.Marshal(input)
    cmd := exec.CommandContext(ctx, "python3", "-c", playerIntelligencePythonV620, dbPath, string(raw))
    out, err := cmd.Output()
    if err != nil {
        if errors.Is(ctx.Err(), context.DeadlineExceeded) {
            return playerIntelligencePayloadV620{}, errors.New("PLAYER_INTELLIGENCE_TIMEOUT_V620")
        }
        return playerIntelligencePayloadV620{}, errors.New("PLAYER_INTELLIGENCE_EXEC_FAILED_V620")
    }
    var payload playerIntelligencePayloadV620
    if err := json.Unmarshal(out, &payload); err != nil {
        return playerIntelligencePayloadV620{}, errors.New("PLAYER_INTELLIGENCE_REPORT_INVALID_V620")
    }
    if !payload.OK {
        if payload.Error == "" {
            payload.Error = "PLAYER_INTELLIGENCE_UNAVAILABLE_V620"
        }
        return payload, errors.New(payload.Error)
    }
    if !payload.Readonly {
        return playerIntelligencePayloadV620{}, errors.New("PLAYER_INTELLIGENCE_READONLY_INVARIANT_V620")
    }
    return payload, nil
}

func normalizeIntelStringsV620(values []string) []string {
    out := make([]string, 0, len(values))
    seen := map[string]bool{}
    for _, v := range values {
        v = strings.TrimSpace(v)
        k := strings.ToLower(v)
        if v == "" || seen[k] {
            continue
        }
        seen[k] = true
        out = append(out, v)
        if len(out) >= 100 {
            break
        }
    }
    return out
}

func (s *server) playerIntelligenceSearchV620(w http.ResponseWriter, r *http.Request, body []byte) {
    var input playerIntelligenceRequestV620
    if err := decodeJSON(body, &input); err != nil {
        writeJSON(w, http.StatusBadRequest, map[string]any{"error": "PLAYER_INTELLIGENCE_REQUEST_INVALID_V620"})
        return
    }
    input.Query = strings.TrimSpace(input.Query)
    input.Alliance = strings.TrimSpace(input.Alliance)
    input.Country = strings.TrimSpace(input.Country)
    input.Sort = strings.TrimSpace(input.Sort)
    input.Servers = normalizeIntelStringsV620(input.Servers)
    input.ExcludeServers = normalizeIntelStringsV620(input.ExcludeServers)
    input.ExcludeAlliances = normalizeIntelStringsV620(input.ExcludeAlliances)
    input.ExcludePlayers = normalizeIntelStringsV620(input.ExcludePlayers)
    if len(input.Query) > 128 || len(input.Alliance) > 128 || len(input.Country) > 32 {
        writeJSON(w, http.StatusBadRequest, map[string]any{"error": "PLAYER_INTELLIGENCE_FILTER_TOO_LONG_V620"})
        return
    }
    if input.Limit == 0 {
        input.Limit = 50
    }
    if input.Limit < 1 || input.Limit > 100 || input.Offset < 0 || input.Offset > 10000 {
        writeJSON(w, http.StatusBadRequest, map[string]any{"error": "PLAYER_INTELLIGENCE_PAGE_INVALID_V620"})
        return
    }
    dbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
    if dbPath == "" {
        dbPath = "/opt/wfgg-collector/data/collector.db"
    }
    ctx, cancel := context.WithTimeout(r.Context(), 25*time.Second)
    defer cancel()
    payload, err := runPlayerIntelligenceV620(ctx, dbPath, input)
    if err != nil {
        status := http.StatusBadGateway
        if strings.HasPrefix(err.Error(), "FILTER_UNSUPPORTED_V620:") {
            status = http.StatusUnprocessableEntity
        }
        writeJSON(w, status, map[string]any{
            "ok": false, "version": "v6.20.0", "readonly": true,
            "error": err.Error(), "capabilities": payload.Capabilities,
        })
        return
    }
    writeJSON(w, http.StatusOK, payload)
}
''', encoding='utf-8')

TEST.write_text(r'''package main

import (
    "context"
    "encoding/json"
    "os/exec"
    "path/filepath"
    "testing"
    "time"
)

func intelDBV620(t *testing.T) string {
    t.Helper()
    if _, err := exec.LookPath("python3"); err != nil {
        t.Skip("python3 unavailable")
    }
    db := filepath.Join(t.TempDir(), "collector.db")
    script := `
import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
c.execute("""CREATE TABLE players(
 game_uid TEXT PRIMARY KEY,pseudo TEXT,server_id TEXT,alliance_id TEXT,alliance_tag TEXT,
 x INTEGER,y INTEGER,hq_level INTEGER,power INTEGER,last_seen TEXT,country TEXT,
 army_power INTEGER,army_kill INTEGER,svip_level INTEGER,avatar_ref TEXT)""")
c.execute("""CREATE TABLE observations(
 id INTEGER PRIMARY KEY,game_uid TEXT,pseudo TEXT,server_id TEXT,cycle_id INTEGER,observed_at TEXT)""")
players=[
 ('1001','AliceFR','8117','A1','WFGG',101,202,30,150000000,'2026-09-21T15:00:00Z','FR',90000000,2500000,15,'https://example.invalid/a.png'),
 ('1002','BobFR','8117','A1','WFGG',303,404,29,90000000,'2026-09-20T15:00:00Z','France',60000000,1500000,12,''),
 ('1003','CharlesUS','8120','B2','BETA',505,606,31,210000000,'2026-08-01T15:00:00Z','US',120000000,5000000,18,'')
]
c.executemany('INSERT INTO players VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',players)
obs=[
 (1,'1001','AliceOld','8117',80,'2026-08-20T00:00:00Z'),
 (2,'1001','AliceFR','8117',94,'2026-09-21T15:00:00Z'),
 (3,'1002','BobFR','8117',94,'2026-09-20T15:00:00Z'),
 (4,'1003','CharlesUS','8120',60,'2026-08-01T15:00:00Z')
]
c.executemany('INSERT INTO observations VALUES(?,?,?,?,?,?)',obs)
c.commit();c.close()
`
    cmd := exec.Command("python3", "-c", script, db)
    if out, err := cmd.CombinedOutput(); err != nil {
        t.Fatalf("fixture: %v %s", err, out)
    }
    return db
}

func runIntelV620(t *testing.T, db string, req playerIntelligenceRequestV620) playerIntelligencePayloadV620 {
    t.Helper()
    ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
    defer cancel()
    got, err := runPlayerIntelligenceV620(ctx, db, req)
    if err != nil {
        raw, _ := json.Marshal(got)
        t.Fatalf("run: %v payload=%s", err, raw)
    }
    return got
}

func TestPlayerIntelligenceAliasSearchV620(t *testing.T) {
    got := runIntelV620(t, intelDBV620(t), playerIntelligenceRequestV620{Query:"AliceOld", Limit:20})
    if got.Count != 1 || got.Players[0]["gameUid"] != "1001" || got.Players[0]["matchedBy"] != "alias" {
        t.Fatalf("payload=%#v", got)
    }
    aliases, _ := got.Players[0]["aliases"].([]any)
    if len(aliases) == 0 {
        t.Fatalf("aliases missing: %#v", got.Players[0])
    }
}

func TestPlayerIntelligenceAllianceSearchV620(t *testing.T) {
    got := runIntelV620(t, intelDBV620(t), playerIntelligenceRequestV620{Query:"WFGG", Limit:20, Sort:"power_desc"})
    if got.Count != 2 || got.Total != 2 {
        t.Fatalf("payload=%#v", got)
    }
    if got.Players[0]["pseudo"] != "AliceFR" {
        t.Fatalf("sort=%#v", got.Players)
    }
    if len(got.Alliances) < 1 {
        t.Fatalf("alliance summary missing")
    }
}

func TestPlayerIntelligenceRecruitmentFiltersV620(t *testing.T) {
    min := int64(100000000)
    got := runIntelV620(t, intelDBV620(t), playerIntelligenceRequestV620{
        Country:"FR", MinPower:&min, ExcludeAlliances:[]string{"BETA"}, Limit:20,
    })
    if got.Count != 1 || got.Players[0]["pseudo"] != "AliceFR" {
        t.Fatalf("payload=%#v", got)
    }
    if !got.Capabilities["country"] || !got.Capabilities["armyPower"] || !got.Capabilities["aliases"] {
        t.Fatalf("capabilities=%#v", got.Capabilities)
    }
}
''', encoding='utf-8')

print('RADAR_V620_PLAYER_INTELLIGENCE_CONNECTOR=READY')
