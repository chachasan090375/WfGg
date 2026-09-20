package main

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"testing"
	"time"
)

func makeTargetHistoryDBV6199(t *testing.T) string {
	t.Helper()
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 unavailable")
	}
	dir := t.TempDir()
	db := filepath.Join(dir, "collector.db")
	script := `
import hashlib,json,sqlite3,sys
db=sys.argv[1]
c=sqlite3.connect(db)
c.executescript("""
CREATE TABLE cycles(id INTEGER PRIMARY KEY,status TEXT,error TEXT,query TEXT);
CREATE TABLE cycle_seen(id INTEGER PRIMARY KEY AUTOINCREMENT,cycle_id INTEGER,game_uid TEXT,state_hash TEXT);
CREATE TABLE cycle_baseline(cycle_id INTEGER,game_uid TEXT,state_json TEXT);
CREATE TABLE cycle_changes(id INTEGER PRIMARY KEY AUTOINCREMENT,cycle_id INTEGER,game_uid TEXT,after_json TEXT);
""")
cycles=[
 (1,'SUCCESS','', '@federated:8125'),
 (2,'SUCCESS','PARTIAL_REGIONS_1','@federated:8125'),
 (3,'FAILED','MAP_ALL_REGIONS_FAILED','@federated:8125'),
 (4,'SUCCESS','', '@federated:8125'),
 (5,'SUCCESS','', '@federated:8125'),
 (6,'SUCCESS','', '@federated:8126'),
 (7,'SUCCESS','', '@federated:8125'),
]
c.executemany('INSERT INTO cycles(id,status,error,query) VALUES(?,?,?,?)',cycles)
def baseline(cid,uid,sid):
    raw=json.dumps({'server_id':sid},separators=(',',':'))
    c.execute('INSERT INTO cycle_baseline(cycle_id,game_uid,state_json) VALUES(?,?,?)',(cid,uid,raw))
    c.execute('INSERT INTO cycle_seen(cycle_id,game_uid,state_hash) VALUES(?,?,?)',(cid,uid,hashlib.sha256(raw.encode()).hexdigest()))
baseline(1,'u1','8125')
baseline(2,'u2','8125')
baseline(3,'u3','8125')
baseline(4,'u4','9999')
baseline(5,'u5','8125')
baseline(6,'u6','8126')
raw0=json.dumps({'server_id':'9999'},separators=(',',':'))
raw1=json.dumps({'server_id':'8125'},separators=(',',':'))
c.execute('INSERT INTO cycle_baseline(cycle_id,game_uid,state_json) VALUES(?,?,?)',(7,'u7',raw0))
c.execute('INSERT INTO cycle_changes(cycle_id,game_uid,after_json) VALUES(?,?,?)',(7,'u7',raw1))
c.execute('INSERT INTO cycle_seen(cycle_id,game_uid,state_hash) VALUES(?,?,?)',(7,'u7',hashlib.sha256(raw1.encode()).hexdigest()))
c.commit()
c.close()
`
	cmd := exec.Command("python3", "-c", script, db)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("create sqlite fixture: %v: %s", err, out)
	}
	return db
}

func TestAutopilotTargetedFullCycleIDsV6199(t *testing.T) {
	db := makeTargetHistoryDBV6199(t)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	got, err := autopilotTargetedFullCycleIDsV6199(ctx, db, "8125")
	if err != nil {
		t.Fatalf("targeted history: %v", err)
	}
	want := []int64{1, 5, 7}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v want %v", got, want)
	}
}

func TestAutopilotTargetedFullCycleIDsV6199NoCandidates(t *testing.T) {
	db := makeTargetHistoryDBV6199(t)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	got, err := autopilotTargetedFullCycleIDsV6199(ctx, db, "9998")
	if err != nil {
		t.Fatalf("targeted history: %v", err)
	}
	if len(got) != 0 {
		t.Fatalf("got %v want empty", got)
	}
}

func TestAutopilotTargetedFullCycleIDsV6199MissingDB(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	_, err := autopilotTargetedFullCycleIDsV6199(ctx, filepath.Join(t.TempDir(), "missing.db"), "8125")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestAutopilotTargetedHistoryV6199ReadOnly(t *testing.T) {
	db := makeTargetHistoryDBV6199(t)
	before, err := os.Stat(db)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if _, err := autopilotTargetedFullCycleIDsV6199(ctx, db, "8125"); err != nil {
		t.Fatal(err)
	}
	after, err := os.Stat(db)
	if err != nil {
		t.Fatal(err)
	}
	if after.Size() != before.Size() {
		t.Fatalf("db size changed: %d -> %d", before.Size(), after.Size())
	}
}
