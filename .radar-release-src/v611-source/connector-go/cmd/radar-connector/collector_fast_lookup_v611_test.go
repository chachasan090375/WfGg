package main

import "testing"

func TestFastLookupQueryV611(t *testing.T) {
	if q, ok := fastLookupQueryV611("  Test Player  "); !ok || q != "Test Player" {
		t.Fatalf("unexpected query normalization: q=%q ok=%v", q, ok)
	}
	if _, ok := fastLookupQueryV611("   "); ok {
		t.Fatal("blank query must be rejected")
	}
	tooLong := make([]byte, 129)
	for i := range tooLong {
		tooLong[i] = 'x'
	}
	if _, ok := fastLookupQueryV611(string(tooLong)); ok {
		t.Fatal("query >128 bytes must be rejected")
	}
}

func TestFastLookupPlayerV611(t *testing.T) {
	x, y, hq := 12, 34, 30
	power := int64(123456789)
	p := fastLookupPlayerV611(&collectorFastPlayerV611{
		GameUID: " 1234567890123456 ", Pseudo: " Test Player ", ServerID: " 999 ",
		AllianceTag: " TEST ", X: &x, Y: &y, HQLevel: &hq, Power: &power,
		LastSeen: " 2026-01-01T00:00:00Z ",
	})
	if p == nil {
		t.Fatal("expected normalized player")
	}
	if p.GameUID != "1234567890123456" || p.Pseudo != "Test Player" || p.ServerID != "999" || p.AllianceTag != "TEST" {
		t.Fatalf("unexpected normalization: %#v", p)
	}
	if p.X == nil || *p.X != 12 || p.Y == nil || *p.Y != 34 || p.HQLevel == nil || *p.HQLevel != 30 || p.Power == nil || *p.Power != 123456789 {
		t.Fatalf("unexpected numeric fields: %#v", p)
	}
}

func TestFastLookupPlayerV611RejectsEmptyIdentity(t *testing.T) {
	if p := fastLookupPlayerV611(&collectorFastPlayerV611{}); p != nil {
		t.Fatalf("expected nil for empty identity, got %#v", p)
	}
}
