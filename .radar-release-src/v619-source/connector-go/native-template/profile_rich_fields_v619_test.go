//go:build lastwar_native_template

package main

import (
	"lastwar-client/internal/sfs"
	"testing"
)

func putV619(o *sfs.SFSObject, key string, value any) {
	o.PutValue(key, sfs.SFSValue{Val: value})
}

func TestFindProfileV3RichFieldsV619(t *testing.T) {
	o := sfs.NewSFSObject()
	putV619(o, "uid", "101")
	putV619(o, "name", "Pilot")
	putV619(o, "power", int64(9000))
	putV619(o, "armyPower", int64(7000))
	putV619(o, "armyKill", int64(123456))
	putV619(o, "svipLevel", int64(17))
	putV619(o, "country", "FR")
	putV619(o, "avatarId", int64(44))

	p, ok := findProfileV3(o, "101", "2026-09-18T00:00:00Z", 0)
	if !ok {
		t.Fatal("profile not found")
	}
	if p.ArmyPower == nil || *p.ArmyPower != 7000 {
		t.Fatalf("armyPower=%v", p.ArmyPower)
	}
	if p.ArmyKill == nil || *p.ArmyKill != 123456 {
		t.Fatalf("armyKill=%v", p.ArmyKill)
	}
	if p.SVIPLevel == nil || *p.SVIPLevel != 17 {
		t.Fatalf("svipLevel=%v", p.SVIPLevel)
	}
	if p.Country != "FR" {
		t.Fatalf("country=%q", p.Country)
	}
	if p.AvatarRef != "44" {
		t.Fatalf("avatarRef=%q", p.AvatarRef)
	}
}

func TestFindProfileV3RichFieldsRemainAbsentWhenUnobservedV619(t *testing.T) {
	o := sfs.NewSFSObject()
	putV619(o, "uid", "202")
	putV619(o, "name", "Sparse")

	p, ok := findProfileV3(o, "202", "2026-09-18T00:00:00Z", 0)
	if !ok {
		t.Fatal("profile not found")
	}
	if p.ArmyPower != nil || p.ArmyKill != nil || p.SVIPLevel != nil {
		t.Fatalf("unobserved numeric fields must stay nil: %#v", p)
	}
	if p.Country != "" || p.AvatarRef != "" {
		t.Fatalf("unobserved string fields must stay empty: %#v", p)
	}
}
