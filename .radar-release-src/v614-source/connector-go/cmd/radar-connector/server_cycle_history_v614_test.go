package main

import (
	"context"
	"encoding/json"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestServerCycleHistoryV614UsesCycleTimeState(t *testing.T) {
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "collector.db")
	seed := `
import hashlib,json,sqlite3,sys
p=sys.argv[1]
c=sqlite3.connect(p)
c.executescript("""
CREATE TABLE cycle_seen(cycle_id INTEGER,game_uid TEXT,state_hash TEXT,enriched INTEGER DEFAULT 0,PRIMARY KEY(cycle_id,game_uid));
CREATE TABLE cycle_baseline(cycle_id INTEGER,game_uid TEXT,state_hash TEXT,state_json TEXT,PRIMARY KEY(cycle_id,game_uid));
CREATE TABLE cycle_changes(id INTEGER PRIMARY KEY AUTOINCREMENT,cycle_id INTEGER,game_uid TEXT,change_type TEXT,before_json TEXT,after_json TEXT,changed_at TEXT);
""")
def state(uid,sid):
    d={'game_uid':uid,'pseudo':uid,'server_id':sid,'alliance_id':'','alliance_tag':'','x':1,'y':2,'hq_level':30,'power':None}
    raw=json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return raw,hashlib.sha256(raw.encode()).hexdigest()
a990,h990=state('a','990'); b992,hb=state('b','992'); a1008,h1008=state('a','1008')
# Cycle 1: a=990, b=992.
c.execute('INSERT INTO cycle_baseline VALUES(1,?,?,?)',('a',h990,a990))
c.execute('INSERT INTO cycle_baseline VALUES(1,?,?,?)',('b',hb,b992))
c.execute('INSERT INTO cycle_seen VALUES(1,?,?,0)',('a',h990))
c.execute('INSERT INTO cycle_seen VALUES(1,?,?,0)',('b',hb))
# Cycle 2 starts at the same baseline, then a changes to server 1008.
c.execute('INSERT INTO cycle_baseline VALUES(2,?,?,?)',('a',h990,a990))
c.execute('INSERT INTO cycle_baseline VALUES(2,?,?,?)',('b',hb,b992))
c.execute('INSERT INTO cycle_changes(cycle_id,game_uid,change_type,before_json,after_json,changed_at) VALUES(2,?,?,?,?,?)',('a','SERVER_TRANSFER',a990,a1008,'2026-01-01T00:00:00Z'))
c.execute('INSERT INTO cycle_seen VALUES(2,?,?,0)',('a',h1008))
c.execute('INSERT INTO cycle_seen VALUES(2,?,?,0)',('b',hb))
# Cycle 3 contains one deliberately invalid state hash; it must not contaminate graph counts.
c.execute('INSERT INTO cycle_baseline VALUES(3,?,?,?)',('b',hb,b992))
c.execute('INSERT INTO cycle_seen VALUES(3,?,?,0)',('b','deadbeef'))
c.commit()
`
	if out, err := exec.Command("python3", "-c", seed, dbPath).CombinedOutput(); err != nil {
		t.Fatalf("seed sqlite: %v: %s", err, out)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	p, err := runServerCycleHistoryV614(ctx, dbPath)
	if err != nil {
		t.Fatal(err)
	}
	if p.MapVersion != "v6.14" || p.CycleCount != 3 || p.SeenRows != 5 || p.HashMatched != 4 || p.HashMismatched != 1 || p.Unresolved != 0 {
		t.Fatalf("unexpected integrity totals: %+v", p)
	}
	if p.ClusterSemanticsProven {
		t.Fatal("cluster semantics must remain unproven")
	}
	if len(p.Cycles) != 3 {
		t.Fatalf("cycles=%d", len(p.Cycles))
	}
	if got := p.Cycles[0].Servers; len(got) != 2 || got[0].ServerID != "990" || got[1].ServerID != "992" {
		t.Fatalf("cycle1 servers=%+v", got)
	}
	if got := p.Cycles[1].Servers; len(got) != 2 || got[0].ServerID != "992" || got[1].ServerID != "1008" {
		t.Fatalf("cycle2 servers=%+v", got)
	}
	if p.Cycles[2].ServerCount != 0 || p.Cycles[2].HashMismatched != 1 {
		t.Fatalf("cycle3 should be excluded by hash mismatch: %+v", p.Cycles[2])
	}
	if len(p.Edges) != 2 {
		t.Fatalf("edges=%+v", p.Edges)
	}
	weights := map[string]int{}
	for _, e := range p.Edges {
		weights[e.ServerA+"-"+e.ServerB] = e.CyclesTogether
	}
	if weights["990-992"] != 1 || weights["992-1008"] != 1 {
		t.Fatalf("historical edges=%+v", weights)
	}
}

func TestServerCycleHistoryV614PayloadContainsNoIdentityKeys(t *testing.T) {
	blob, _ := json.Marshal(serverCycleHistoryPayloadV614{})
	text := strings.ToLower(string(blob))
	for _, forbidden := range []string{"gameuid", "game_uid", "pseudo", "alliance", "credential", "token", "coordinate"} {
		if strings.Contains(text, forbidden) {
			t.Fatalf("sensitive key present: %s", forbidden)
		}
	}
}
