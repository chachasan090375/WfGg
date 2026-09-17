package main

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestServerCensusV612AggregatesWithoutRawPlayerData(t *testing.T) {
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "collector.db")
	seed := `
import sqlite3, sys
p=sys.argv[1]
c=sqlite3.connect(p)
c.executescript("""
CREATE TABLE players(game_uid TEXT PRIMARY KEY, pseudo TEXT, server_id INTEGER);
CREATE TABLE observations(id INTEGER PRIMARY KEY, game_uid TEXT, cycle_id INTEGER);
INSERT INTO players VALUES('uid-a','Alice',990);
INSERT INTO players VALUES('uid-b','Bob',990);
INSERT INTO players VALUES('uid-c','Carol',992);
INSERT INTO observations(game_uid,cycle_id) VALUES('uid-a',10),('uid-b',10),('uid-a',11),('uid-c',11),('uid-c',12);
""")
c.commit()
`
	if out, err := exec.Command("python3", "-c", seed, dbPath).CombinedOutput(); err != nil {
		t.Fatalf("seed sqlite: %v: %s", err, out)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	payload, err := runServerCensusV612(ctx, dbPath)
	if err != nil {
		t.Fatal(err)
	}
	if payload.ServerCount != 2 || payload.PlayersTotal != 3 || payload.ObservationsTotal != 5 {
		t.Fatalf("unexpected totals: %+v", payload)
	}
	if payload.Schema.JoinMode != "UID_JOIN" {
		t.Fatalf("join mode=%q", payload.Schema.JoinMode)
	}
	if len(payload.Servers) != 2 {
		t.Fatalf("servers=%d", len(payload.Servers))
	}
	if payload.Servers[0].ServerID != "990" || payload.Servers[0].Players != 2 || payload.Servers[0].Observations != 3 || payload.Servers[0].DistinctCycles != 2 {
		t.Fatalf("server 990=%+v", payload.Servers[0])
	}
	if payload.Servers[1].ServerID != "992" || payload.Servers[1].Players != 1 || payload.Servers[1].Observations != 2 || payload.Servers[1].DistinctCycles != 2 {
		t.Fatalf("server 992=%+v", payload.Servers[1])
	}
	blob, _ := json.Marshal(payload)
	text := string(blob)
	for _, forbidden := range []string{"uid-a", "uid-b", "uid-c", "Alice", "Bob", "Carol"} {
		if strings.Contains(text, forbidden) {
			t.Fatalf("raw player data leaked: %s", forbidden)
		}
	}
}

func TestServerCensusV612MissingDBFailsClosed(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_, err := runServerCensusV612(ctx, filepath.Join(t.TempDir(), "missing.db"))
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestServerCensusV612PayloadContainsNoSensitiveKeys(t *testing.T) {
	blob, _ := json.Marshal(serverCensusPayloadV612{})
	text := strings.ToLower(string(blob))
	for _, forbidden := range []string{"pseudo", "gameuid", "game_uid", "alliance", "token", "credential"} {
		if strings.Contains(text, forbidden) {
			t.Fatalf("sensitive key present: %s", forbidden)
		}
	}
	_ = os.ErrNotExist
}
