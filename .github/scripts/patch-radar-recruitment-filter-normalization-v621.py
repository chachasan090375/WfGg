#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
MAIN = ROOT / 'connector-go/cmd/radar-connector/main.go'
SRC = ROOT / 'connector-go/cmd/radar-connector/player_intelligence_v621.go'
TEST = ROOT / 'connector-go/cmd/radar-connector/player_intelligence_v621_test.go'

main = MAIN.read_text(encoding='utf-8')
marker = 'WFGG_RADAR_PLAYER_INTELLIGENCE_ROUTE_V621'
if marker not in main:
    anchor = '\tmux.HandleFunc("POST /v1/collector/intelligence/search", s.signed(s.playerIntelligenceSearchV620))\n'
    if main.count(anchor) != 1:
        raise SystemExit(f'V621_ROUTE_ANCHOR_COUNT={main.count(anchor)}')
    main = main.replace(
        anchor,
        anchor + '\t// ' + marker + '\n\tmux.HandleFunc("POST /v1/collector/intelligence/search-v621", s.signed(s.playerIntelligenceSearchV621))\n',
        1,
    )
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

// WFGG_RADAR_RECRUITMENT_FILTER_NORMALIZATION_V621
// V6.21 is a local Collector-only search/filter layer. It never opens a
// Last War connection and never mutates game state.
type playerIntelligenceRequestV621 struct {
    Query               string   `json:"query,omitempty"`
    Mode                string   `json:"mode,omitempty"`
    Limit               int      `json:"limit,omitempty"`
    Offset              int      `json:"offset,omitempty"`
    Country             string   `json:"country,omitempty"`
    IncludeServers      []string `json:"includeServers,omitempty"`
    ExcludeServers      []string `json:"excludeServers,omitempty"`
    IncludeAlliances    []string `json:"includeAlliances,omitempty"`
    ExcludeAlliances    []string `json:"excludeAlliances,omitempty"`
    IncludePlayers      []string `json:"includePlayers,omitempty"`
    ExcludePlayers      []string `json:"excludePlayers,omitempty"`
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

type playerIntelligenceOptionsV621 struct {
    Countries     []string `json:"countries,omitempty"`
    CountrySource string   `json:"countrySource,omitempty"`
}

type playerIntelligencePayloadV621 struct {
    OK             bool                          `json:"ok"`
    Version        string                        `json:"version,omitempty"`
    Readonly       bool                          `json:"readonly"`
    Source         string                        `json:"source,omitempty"`
    Total          int                           `json:"total,omitempty"`
    Count          int                           `json:"count,omitempty"`
    Players        []map[string]any              `json:"players,omitempty"`
    Alliances      []map[string]any              `json:"alliances,omitempty"`
    Capabilities   map[string]bool               `json:"capabilities,omitempty"`
    Options        playerIntelligenceOptionsV621 `json:"options,omitempty"`
    Warnings       []string                      `json:"warnings,omitempty"`
    IgnoredFilters []string                      `json:"ignoredFilters,omitempty"`
    Schema         map[string]any                `json:"schema,omitempty"`
    Error          string                        `json:"error,omitempty"`
}

const playerIntelligencePythonV621 = `
import json,sqlite3,sys,re

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

def uniq(values,maxn=200):
    out=[]; seen=set()
    for v in values or []:
        s=txt(v)
        if not s: continue
        k=s.casefold()
        if k in seen: continue
        seen.add(k); out.append(s)
        if len(out)>=maxn: break
    return out

def norm_server(v):
    s=txt(v)
    if len(s)>1 and s[0] in 'sS' and s[1:].isdigit():
        s=s[1:]
    return s

def norm_alliance(v):
    s=txt(v)
    while len(s)>=2 and s[0]=='[' and s[-1]==']':
        s=s[1:-1].strip()
    return s

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
country_names=['country','country_code','countryCode','nation','nationality']
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
    print(json.dumps({'ok':False,'readonly':True,'error':'PLAYER_INDEX_UNAVAILABLE_V621'},separators=(',',':')))
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

obs_country=None
if obs_table:
    obs_country=pick(schema[obs_table],country_names)

# Country dropdown is intentionally NOT a generic world-country catalogue.
# It contains only values that Last War has actually supplied to Collector.
country_options=[]
for table,col in [(player_table,country),(obs_table,obs_country)]:
    if table and col:
        sql='SELECT DISTINCT TRIM(CAST('+qi(col)+' AS TEXT)) v FROM '+qi(table)+' WHERE '+qi(col)+' IS NOT NULL AND TRIM(CAST('+qi(col)+' AS TEXT))<>\'\' LIMIT 256'
        for rr in conn.execute(sql):
            v=txt(rr['v'])
            if v:
                country_options.append(v)
country_options=sorted(uniq(country_options,256),key=lambda s:s.casefold())

caps={
 'aliases': bool(obs_table),
 'server': bool(server),
 'alliance': bool(alliance_tag or alliance_id),
 'hq': bool(hq),
 'power': bool(power),
 'lastSeen': bool(seen),
 'country': bool(country and country_options),
 'avatar': bool(avatar),
 'armyPower': bool(army_power),
 'kills': bool(kills),
 'svip': bool(svip),
}

warnings=[]
ignored=[]

def requested(name):
    v=req.get(name)
    if isinstance(v,list): return bool([x for x in v if txt(x)])
    return v is not None and txt(v)!=''

def ignore_if_missing(cap,key,*request_keys):
    if any(requested(k) for k in request_keys) and not caps.get(cap,False):
        warnings.append(cap+'_unavailable')
        ignored.append(key)
        return True
    return False

skip_server=ignore_if_missing('server','servers','includeServers','excludeServers')
skip_alliance=ignore_if_missing('alliance','alliances','includeAlliances','excludeAlliances')
skip_hq=ignore_if_missing('hq','hq','minHQ','maxHQ')
skip_power=ignore_if_missing('power','power','minPower','maxPower')
skip_seen=ignore_if_missing('lastSeen','activity','observedWithinDays','observedOlderDays')
skip_country=ignore_if_missing('country','country','country')
skip_army=ignore_if_missing('armyPower','armyPower','minArmyPower','maxArmyPower')
skip_kills=ignore_if_missing('kills','kills','minKills')
skip_svip=ignore_if_missing('svip','svip','minSVIP')

options={
 'countries':country_options,
 'countrySource':'lastwar-observed-values' if country_options else 'unavailable'
}

if txt(req.get('mode')).lower() in ('metadata','options','capabilities'):
    payload={
      'ok':True,'version':'v6.21.0','readonly':True,'source':'collector-sqlite-local',
      'total':0,'count':0,'players':[],'alliances':[],'capabilities':caps,
      'options':options,'warnings':warnings,'ignoredFilters':ignored,
      'schema':{'playerTable':player_table,'observationTable':obs_table or ''}
    }
    conn.close()
    print(json.dumps(payload,separators=(',',':')))
    raise SystemExit(0)

q=txt(req.get('query'))
qfold=q.casefold()

def aliases_for_tokens(tokens):
    out=[]
    if not obs_table: return out
    oc=schema[obs_table]; ouid=pick(oc,uid_names); opseudo=pick(oc,pseudo_names)
    if not ouid or not opseudo: return out
    for token in uniq(tokens,100):
        for rr in conn.execute(
            'SELECT DISTINCT CAST('+qi(ouid)+' AS TEXT) uid FROM '+qi(obs_table)+' WHERE lower(TRIM(COALESCE('+qi(opseudo)+",'')))=? LIMIT 500",
            (token.casefold(),)
        ):
            u=txt(rr['uid'])
            if u: out.append(u)
    return uniq(out,2000)

alias_uids=[]
alias_matches={}
if q and obs_table:
    oc=schema[obs_table]; ouid=pick(oc,uid_names); opseudo=pick(oc,pseudo_names)
    if ouid and opseudo:
        like='%'+qfold+'%'
        sql='SELECT '+qi(ouid)+' uid,'+qi(opseudo)+' pseudo FROM '+qi(obs_table)+' WHERE lower(COALESCE('+qi(opseudo)+",'')) LIKE ? LIMIT 2500"
        for rr in conn.execute(sql,(like,)):
            u=txt(rr['uid']); p=txt(rr['pseudo'])
            if u:
                alias_uids.append(u)
                if p and qfold in p.casefold():
                    alias_matches.setdefault(u,p)
alias_uids=uniq(alias_uids,2000)

include_players=uniq(req.get('includePlayers'),100)
exclude_players=uniq(req.get('excludePlayers'),100)
include_player_alias_uids=aliases_for_tokens(include_players)
exclude_player_alias_uids=aliases_for_tokens(exclude_players)

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

if not skip_server:
    include_servers=uniq([norm_server(x) for x in req.get('includeServers') or []],100)
    if include_servers:
        marks=','.join('?' for _ in include_servers)
        where.append('CAST('+qi(server)+' AS TEXT) IN ('+marks+')'); params.extend(include_servers)
    exclude_servers=uniq([norm_server(x) for x in req.get('excludeServers') or []],100)
    if exclude_servers:
        marks=','.join('?' for _ in exclude_servers)
        where.append('CAST('+qi(server)+' AS TEXT) NOT IN ('+marks+')'); params.extend(exclude_servers)

def alliance_or(values):
    ors=[]; ps=[]
    for raw in uniq(values,100):
        a=norm_alliance(raw)
        if not a: continue
        if alliance_tag:
            ors.append('lower(TRIM(COALESCE('+qi(alliance_tag)+",''))) = ?"); ps.append(a.casefold())
        if alliance_id:
            ors.append('lower(TRIM(COALESCE(CAST('+qi(alliance_id)+' AS TEXT),\'\'))) = ?'); ps.append(a.casefold())
    return ors,ps

if not skip_alliance:
    ors,ps=alliance_or(req.get('includeAlliances') or [])
    if ors:
        where.append('('+' OR '.join(ors)+')'); params.extend(ps)
    ors,ps=alliance_or(req.get('excludeAlliances') or [])
    if ors:
        where.append('NOT ('+' OR '.join(ors)+')'); params.extend(ps)

def player_or(values,alias_ids):
    ors=[]; ps=[]
    vals=uniq(values,100)
    for p in vals:
        ors.append('lower(TRIM(COALESCE('+qi(pseudo)+",''))) = ?"); ps.append(p.casefold())
        ors.append('CAST('+qi(uid)+' AS TEXT) = ?'); ps.append(p)
    if alias_ids:
        marks=','.join('?' for _ in alias_ids)
        ors.append('CAST('+qi(uid)+' AS TEXT) IN ('+marks+')'); ps.extend(alias_ids)
    return ors,ps

ors,ps=player_or(include_players,include_player_alias_uids)
if ors:
    where.append('('+' OR '.join(ors)+')'); params.extend(ps)
ors,ps=player_or(exclude_players,exclude_player_alias_uids)
if ors:
    where.append('NOT ('+' OR '.join(ors)+')'); params.extend(ps)

def add_num(col,op,key):
    val=req.get(key)
    if val is not None:
        where.append('CAST('+qi(col)+' AS INTEGER) '+op+' ?'); params.append(int(val))

if not skip_power:
    add_num(power,'>=','minPower'); add_num(power,'<=','maxPower')
if not skip_hq:
    add_num(hq,'>=','minHQ'); add_num(hq,'<=','maxHQ')
if not skip_army:
    add_num(army_power,'>=','minArmyPower'); add_num(army_power,'<=','maxArmyPower')
if not skip_kills:
    add_num(kills,'>=','minKills')
if not skip_svip:
    add_num(svip,'>=','minSVIP')

country_filter=txt(req.get('country'))
if country_filter and not skip_country:
    # The UI sends one of the Last-War-observed option values. Match exactly,
    # case-insensitively, to avoid guessing or accepting a generic country list.
    where.append('lower(TRIM(COALESCE('+qi(country)+",''))) = ?")
    params.append(country_filter.casefold())

if not skip_seen:
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

result_uids=[txt(rr['game_uid']) for rr in rows if txt(rr['game_uid'])]
aliases={}
if obs_table and result_uids:
    oc=schema[obs_table]; ouid=pick(oc,uid_names); opseudo=pick(oc,pseudo_names)
    if ouid and opseudo:
        marks=','.join('?' for _ in result_uids)
        sql='SELECT '+qi(ouid)+' uid,'+qi(opseudo)+' pseudo FROM '+qi(obs_table)+' WHERE CAST('+qi(ouid)+' AS TEXT) IN ('+marks+')'
        for rr in conn.execute(sql,tuple(result_uids)):
            u=txt(rr['uid']); p=txt(rr['pseudo'])
            if not u or not p: continue
            aliases.setdefault(u,[])
            if p.casefold() not in {x.casefold() for x in aliases[u]}:
                aliases[u].append(p)

players=[]
for rr in rows:
    d={k:rr[k] for k in rr.keys()}
    u=txt(d.get('game_uid')); current=txt(d.get('pseudo'))
    hist=[p for p in aliases.get(u,[]) if p.casefold()!=current.casefold()]
    matched_by='current'; matched_alias=''
    if q:
        if qfold in current.casefold(): matched_by='current'
        elif u==q: matched_by='uid'
        elif alliance_tag and qfold in txt(d.get('alliance_tag')).casefold(): matched_by='alliance'
        elif alliance_id and qfold in txt(d.get('alliance_id')).casefold(): matched_by='alliance'
        else:
            for a in hist:
                if qfold in a.casefold():
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
 'ok':True,'version':'v6.21.0','readonly':True,'source':'collector-sqlite-local',
 'total':total,'count':len(players),'players':players,'alliances':alliances,
 'capabilities':caps,'options':options,'warnings':warnings,'ignoredFilters':ignored,
 'schema':{'playerTable':player_table,'observationTable':obs_table or ''},
}
conn.close()
print(json.dumps(payload,separators=(',',':')))
`

func runPlayerIntelligenceV621(ctx context.Context, dbPath string, input playerIntelligenceRequestV621) (playerIntelligencePayloadV621, error) {
    if strings.TrimSpace(dbPath) == "" {
        return playerIntelligencePayloadV621{}, errors.New("COLLECTOR_DB_PATH_EMPTY")
    }
    if _, err := os.Stat(dbPath); err != nil {
        return playerIntelligencePayloadV621{}, errors.New("COLLECTOR_DB_UNAVAILABLE")
    }
    if _, err := exec.LookPath("python3"); err != nil {
        return playerIntelligencePayloadV621{}, errors.New("PLAYER_INTELLIGENCE_PYTHON3_MISSING_V621")
    }
    raw, _ := json.Marshal(input)
    cmd := exec.CommandContext(ctx, "python3", "-c", playerIntelligencePythonV621, dbPath, string(raw))
    out, err := cmd.Output()
    if err != nil {
        if errors.Is(ctx.Err(), context.DeadlineExceeded) {
            return playerIntelligencePayloadV621{}, errors.New("PLAYER_INTELLIGENCE_TIMEOUT_V621")
        }
        return playerIntelligencePayloadV621{}, errors.New("PLAYER_INTELLIGENCE_EXEC_FAILED_V621")
    }
    var payload playerIntelligencePayloadV621
    if err := json.Unmarshal(out, &payload); err != nil {
        return playerIntelligencePayloadV621{}, errors.New("PLAYER_INTELLIGENCE_REPORT_INVALID_V621")
    }
    if !payload.OK {
        if payload.Error == "" {
            payload.Error = "PLAYER_INTELLIGENCE_UNAVAILABLE_V621"
        }
        return payload, errors.New(payload.Error)
    }
    if !payload.Readonly {
        return playerIntelligencePayloadV621{}, errors.New("PLAYER_INTELLIGENCE_READONLY_INVARIANT_V621")
    }
    return payload, nil
}

func normalizeIntelStringsV621(values []string) []string {
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

func (s *server) playerIntelligenceSearchV621(w http.ResponseWriter, r *http.Request, body []byte) {
    var input playerIntelligenceRequestV621
    if err := decodeJSON(body, &input); err != nil {
        writeJSON(w, http.StatusBadRequest, map[string]any{"error": "PLAYER_INTELLIGENCE_REQUEST_INVALID_V621"})
        return
    }
    input.Query = strings.TrimSpace(input.Query)
    input.Mode = strings.TrimSpace(input.Mode)
    input.Country = strings.TrimSpace(input.Country)
    input.Sort = strings.TrimSpace(input.Sort)
    input.IncludeServers = normalizeIntelStringsV621(input.IncludeServers)
    input.ExcludeServers = normalizeIntelStringsV621(input.ExcludeServers)
    input.IncludeAlliances = normalizeIntelStringsV621(input.IncludeAlliances)
    input.ExcludeAlliances = normalizeIntelStringsV621(input.ExcludeAlliances)
    input.IncludePlayers = normalizeIntelStringsV621(input.IncludePlayers)
    input.ExcludePlayers = normalizeIntelStringsV621(input.ExcludePlayers)
    if len(input.Query) > 128 || len(input.Country) > 64 || len(input.Mode) > 32 {
        writeJSON(w, http.StatusBadRequest, map[string]any{"error": "PLAYER_INTELLIGENCE_FILTER_TOO_LONG_V621"})
        return
    }
    if input.Limit == 0 {
        input.Limit = 50
    }
    if input.Limit < 1 || input.Limit > 100 || input.Offset < 0 || input.Offset > 10000 {
        writeJSON(w, http.StatusBadRequest, map[string]any{"error": "PLAYER_INTELLIGENCE_PAGE_INVALID_V621"})
        return
    }
    dbPath := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_DB"))
    if dbPath == "" {
        dbPath = "/opt/wfgg-collector/data/collector.db"
    }
    ctx, cancel := context.WithTimeout(r.Context(), 25*time.Second)
    defer cancel()
    payload, err := runPlayerIntelligenceV621(ctx, dbPath, input)
    if err != nil {
        writeJSON(w, http.StatusBadGateway, map[string]any{
            "ok": false, "version": "v6.21.0", "readonly": true, "error": err.Error(),
        })
        return
    }
    writeJSON(w, http.StatusOK, payload)
}
''', encoding='utf-8')

TEST.write_text(r'''package main

import (
    "context"
    "os/exec"
    "path/filepath"
    "testing"
    "time"
)

func intelDBV621(t *testing.T, withCountry bool) string {
    t.Helper()
    if _, err := exec.LookPath("python3"); err != nil {
        t.Skip("python3 unavailable")
    }
    db := filepath.Join(t.TempDir(), "collector.db")
    countryCol := ""
    if withCountry {
        countryCol = ",country TEXT"
    }
    script := `
import sqlite3,sys
db=sys.argv[1]; with_country=sys.argv[2]=='1'
c=sqlite3.connect(db)
country=',country TEXT' if with_country else ''
c.execute("CREATE TABLE players(game_uid TEXT PRIMARY KEY,pseudo TEXT,server_id TEXT,alliance_id TEXT,alliance_tag TEXT,x INTEGER,y INTEGER,hq_level INTEGER,power INTEGER,last_seen TEXT"+country+",army_power INTEGER,army_kill INTEGER,svip_level INTEGER,avatar_ref TEXT)")
c.execute("CREATE TABLE observations(id INTEGER PRIMARY KEY,game_uid TEXT,pseudo TEXT,server_id TEXT,cycle_id INTEGER,observed_at TEXT"+country+")")
if with_country:
 p=[
 ('1001','AliceFR','992','A1','WFGG',101,202,30,150000000,'2026-09-21T15:00:00Z','FR',90000000,2500000,15,''),
 ('1002','BobFR','992','A2','FOX',303,404,29,90000000,'2026-09-20T15:00:00Z','FR',60000000,1500000,12,''),
 ('1003','CharlesUS','993','B2','BETA',505,606,31,210000000,'2026-09-19T15:00:00Z','US',120000000,5000000,18,'')
 ]
 c.executemany('INSERT INTO players VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',p)
 o=[(1,'1001','AliceOld','992',80,'2026-08-20T00:00:00Z','FR'),(2,'1001','AliceFR','992',94,'2026-09-21T15:00:00Z','FR'),(3,'1002','BobFR','992',94,'2026-09-20T15:00:00Z','FR'),(4,'1003','CharlesUS','993',60,'2026-09-19T15:00:00Z','US')]
 c.executemany('INSERT INTO observations VALUES(?,?,?,?,?,?,?)',o)
else:
 p=[
 ('1001','AliceFR','992','A1','WFGG',101,202,30,150000000,'2026-09-21T15:00:00Z',90000000,2500000,15,''),
 ('1002','BobFR','992','A2','FOX',303,404,29,90000000,'2026-09-20T15:00:00Z',60000000,1500000,12,'')
 ]
 c.executemany('INSERT INTO players VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',p)
 o=[(1,'1001','AliceOld','992',80,'2026-08-20T00:00:00Z'),(2,'1001','AliceFR','992',94,'2026-09-21T15:00:00Z')]
 c.executemany('INSERT INTO observations VALUES(?,?,?,?,?,?)',o)
c.commit(); c.close()
`
    cmd := exec.Command("python3", "-c", script, db)
    if withCountry {
        cmd.Args = append(cmd.Args, "1")
    } else {
        cmd.Args = append(cmd.Args, "0")
    }
    if out, err := cmd.CombinedOutput(); err != nil {
        t.Fatalf("fixture: %v %s", err, out)
    }
    _ = countryCol
    return db
}

func runIntelV621(t *testing.T, db string, req playerIntelligenceRequestV621) playerIntelligencePayloadV621 {
    t.Helper()
    ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
    defer cancel()
    got, err := runPlayerIntelligenceV621(ctx, db, req)
    if err != nil {
        t.Fatalf("run: %v payload=%#v", err, got)
    }
    return got
}

func TestPlayerIntelligenceCountryOptionsAreGameObservedV621(t *testing.T) {
    got := runIntelV621(t, intelDBV621(t, true), playerIntelligenceRequestV621{Mode: "metadata", Limit: 50})
    if !got.Capabilities["country"] {
        t.Fatalf("country capability missing: %#v", got)
    }
    if got.Options.CountrySource != "lastwar-observed-values" {
        t.Fatalf("source=%q", got.Options.CountrySource)
    }
    if len(got.Options.Countries) != 2 || got.Options.Countries[0] != "FR" || got.Options.Countries[1] != "US" {
        t.Fatalf("countries=%#v", got.Options.Countries)
    }
}

func TestPlayerIntelligenceUnsupportedCountryIsGracefulV621(t *testing.T) {
    got := runIntelV621(t, intelDBV621(t, false), playerIntelligenceRequestV621{Country: "FR", Limit: 50})
    if got.Count != 2 {
        t.Fatalf("country should be ignored, count=%d payload=%#v", got.Count, got)
    }
    if got.Capabilities["country"] {
        t.Fatal("country must be unavailable")
    }
    found := false
    for _, w := range got.Warnings {
        if w == "country_unavailable" { found = true }
    }
    if !found {
        t.Fatalf("warning missing: %#v", got.Warnings)
    }
}

func TestPlayerIntelligenceNormalizedChipsV621(t *testing.T) {
    got := runIntelV621(t, intelDBV621(t, true), playerIntelligenceRequestV621{
        IncludeServers: []string{"S992"},
        IncludeAlliances: []string{"[wfgg]", "FOX"},
        ExcludePlayers: []string{"BobFR"},
        Limit: 50,
    })
    if got.Count != 1 || got.Players[0]["pseudo"] != "AliceFR" {
        t.Fatalf("payload=%#v", got)
    }
}

func TestPlayerIntelligenceIncludeAliasV621(t *testing.T) {
    got := runIntelV621(t, intelDBV621(t, true), playerIntelligenceRequestV621{
        IncludePlayers: []string{"AliceOld"}, Limit: 50,
    })
    if got.Count != 1 || got.Players[0]["gameUid"] != "1001" {
        t.Fatalf("payload=%#v", got)
    }
}

func TestPlayerIntelligenceAliasSearchStillWorksV621(t *testing.T) {
    got := runIntelV621(t, intelDBV621(t, true), playerIntelligenceRequestV621{Query:"AliceOld", Limit:50})
    if got.Count != 1 || got.Players[0]["matchedBy"] != "alias" {
        t.Fatalf("payload=%#v", got)
    }
}
''', encoding='utf-8')

print('RADAR_V621_RECRUITMENT_FILTER_NORMALIZATION_CONNECTOR=READY')
