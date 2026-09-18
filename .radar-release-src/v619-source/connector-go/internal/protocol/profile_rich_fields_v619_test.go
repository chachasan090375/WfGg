package protocol

import (
	"encoding/json"
	"strings"
	"testing"
)

func i64V619(v int64) *int64 { return &v }

func TestPlayerRichFieldsJSONV619(t *testing.T) {
	p := Player{
		GameUID: "101",
		ArmyPower: i64V619(7000),
		ArmyKill: i64V619(123456),
		SVIPLevel: i64V619(17),
		Country: "FR",
		AvatarRef: "44",
	}
	raw, err := json.Marshal(p)
	if err != nil {
		t.Fatal(err)
	}
	s := string(raw)
	for _, want := range []string{
		"\"armyPower\":7000",
		"\"armyKill\":123456",
		"\"svipLevel\":17",
		"\"country\":\"FR\"",
		"\"avatarRef\":\"44\"",
	} {
		if !strings.Contains(s, want) {
			t.Fatalf("missing %s in %s", want, s)
		}
	}
}

func TestPlayerRichFieldsOmitUnknownV619(t *testing.T) {
	raw, err := json.Marshal(Player{GameUID: "202"})
	if err != nil {
		t.Fatal(err)
	}
	s := string(raw)
	for _, forbidden := range []string{"armyPower", "armyKill", "svipLevel", "country", "avatarRef"} {
		if strings.Contains(s, forbidden) {
			t.Fatalf("unexpected %s in %s", forbidden, s)
		}
	}
}
