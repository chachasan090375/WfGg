package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestDeriveServerClusterEvidenceV6123(t *testing.T) {
	m := serverCycleMapPayloadV6122{
		OK: true,
		MapVersion: "v6.12.2",
		Readonly: true,
		RawPlayerDataExposed: false,
		Cycles: []serverCycleRowV6122{
			{CycleID: 1, Servers: []serverCycleMemberV6122{{ServerID: "100", Observations: 100}, {ServerID: "200", Observations: 90}, {ServerID: "300", Observations: 5}, {ServerID: "999", Observations: 1}}},
			{CycleID: 2, Servers: []serverCycleMemberV6122{{ServerID: "100", Observations: 100}, {ServerID: "200", Observations: 90}, {ServerID: "300", Observations: 5}}},
			{CycleID: 3, Servers: []serverCycleMemberV6122{{ServerID: "100", Observations: 100}, {ServerID: "200", Observations: 90}, {ServerID: "300", Observations: 5}}},
		},
		Edges: []serverPairEdgeV6122{
			{ServerA: "100", ServerB: "200", CyclesTogether: 3},
			{ServerA: "100", ServerB: "300", CyclesTogether: 3},
			{ServerA: "200", ServerB: "300", CyclesTogether: 3},
			{ServerA: "100", ServerB: "999", CyclesTogether: 1},
			{ServerA: "200", ServerB: "999", CyclesTogether: 1},
			{ServerA: "300", ServerB: "999", CyclesTogether: 1},
		},
	}
	p := deriveServerClusterEvidenceV6123(m)
	if p.CycleCount != 3 || p.PersistentCount != 3 || p.TransientCount != 1 {
		t.Fatalf("unexpected counts: %+v", p)
	}
	if p.CoreExpectedEdges != 3 || p.CoreStrongEdges != 3 || !p.CoreCliqueComplete {
		t.Fatalf("unexpected clique state: %+v", p)
	}
	if len(p.Persistent) != 3 || p.Persistent[2].ServerID != "300" || p.Persistent[2].EvidenceClass != "persistent_low_volume" {
		t.Fatalf("low-volume persistent node not classified: %+v", p.Persistent)
	}
	if len(p.Transient) != 1 || p.Transient[0].ServerID != "999" || p.Transient[0].CyclesSeen != 1 || p.Transient[0].EvidenceClass != "transient" {
		t.Fatalf("transient node not classified: %+v", p.Transient)
	}
	if p.Persistent[0].CycleCoverage != 1 || p.Transient[0].CycleCoverage != 1.0/3.0 {
		t.Fatalf("unexpected coverage: persistent=%v transient=%v", p.Persistent[0].CycleCoverage, p.Transient[0].CycleCoverage)
	}
}

func TestServerClusterEvidenceV6123ContainsNoIdentityKeys(t *testing.T) {
	blob, _ := json.Marshal(serverClusterEvidencePayloadV6123{})
	text := strings.ToLower(string(blob))
	for _, forbidden := range []string{"gameuid", "game_uid", "pseudo", "alliance", "credential", "token", "coordinate"} {
		if strings.Contains(text, forbidden) {
			t.Fatalf("sensitive key present: %s", forbidden)
		}
	}
}
