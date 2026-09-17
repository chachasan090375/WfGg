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

func TestServerCycleMapV6122AggregatesCyclesAndEdges(t *testing.T) {
	dbPath := filepath.Join(t.TempDir(), "collector.db")
	seed := `
import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
c.executescript("""
CREATE TABLE players(game_uid TEXT PRIMARY KEY,pseudo TEXT,server_id INTEGER);
CREATE TABLE cycle_seen(game_uid TEXT,cycle_id INTEGER);
INSERT INTO players VALUES('a','Alice',990),('b','Bob',992),('c','Carol',1008),('d','Dan',1006);
INSERT INTO cycle_seen VALUES
 ('a',1),('b',1),('c',1),
 ('a',2),('b',2),('c',2),
 ('a',3),('b',3),('d',3);
""")
c.commit()
`
	if out, err := exec.Command("python3", "-c", seed, dbPath).CombinedOutput(); err != nil {
		t.Fatalf("seed: %v %s", err, out)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	p, err := runServerCycleMapV6122(ctx, dbPath)
	if err != nil { t.Fatal(err) }
	if p.MapVersion != "v6.12.2" || p.CycleCount != 3 { t.Fatalf("payload=%+v", p) }
	if len(p.Cycles) != 3 || p.Cycles[0].ServerCount != 3 { t.Fatalf("cycles=%+v", p.Cycles) }
	var edge990992 int
	for _, e := range p.Edges {
		if e.ServerA == "990" && e.ServerB == "992" { edge990992 = e.CyclesTogether }
	}
	if edge990992 != 3 { t.Fatalf("990-992 cycles=%d edges=%+v", edge990992, p.Edges) }
	blob, _ := json.Marshal(p)
	text := string(blob)
	for _, forbidden := range []string{"Alice","Bob","Carol","Dan","\"a\"","\"b\"","\"c\"","\"d\""} {
		if strings.Contains(text, forbidden) { t.Fatalf("raw identity leaked: %s", forbidden) }
	}
}

func TestServerCycleMapV6122MissingDBFailsClosed(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	_, err := runServerCycleMapV6122(ctx, filepath.Join(t.TempDir(), "missing.db"))
	if err == nil { t.Fatal("expected error") }
}
