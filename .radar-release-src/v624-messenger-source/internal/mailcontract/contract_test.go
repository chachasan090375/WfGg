package mailcontract

import (
	"strings"
	"testing"
)

func TestPrivateSameServerContract(t *testing.T) {
	got, err := BuildPrivateSameServerDryRun(Draft{
		TargetName: "Player",
		TargetUID: "123456789",
		Title: "Hello",
		Contents: "Test message",
		SendLocalTime: 1234567890,
		SenderServer: 8120,
		TargetServer: 8120,
	})
	if err != nil {
		t.Fatal(err)
	}
	if got.Command != "mail.send" || got.MailType != 21 || got.Transport != "SFS" {
		t.Fatalf("unexpected envelope: %#v", got)
	}
	if got.NetworkEnabled || got.MutationExecuted {
		t.Fatal("dry-run must never enable network or execute mutation")
	}
	want := []struct{ method, key string }{
		{"PutUtfString", "name"},
		{"PutUtfString", "title"},
		{"PutUtfString", "contents"},
		{"PutUtfString", "allianceId"},
		{"PutUtfString", "targetUid"},
		{"PutLong", "sendLocalTime"},
		{"PutInt", "type"},
	}
	if len(got.Fields) != len(want) {
		t.Fatalf("field count=%d want=%d", len(got.Fields), len(want))
	}
	for i, w := range want {
		if got.Fields[i].Method != w.method || got.Fields[i].Key != w.key {
			t.Fatalf("field[%d]=%#v want %s:%s", i, got.Fields[i], w.method, w.key)
		}
	}
}

func TestCrossServerPrivateMailBlocked(t *testing.T) {
	_, err := BuildPrivateSameServerDryRun(Draft{
		TargetName: "Player", TargetUID: "1", Title: "T", Contents: "C",
		SendLocalTime: 1, SenderServer: 8120, TargetServer: 8131,
	})
	if err == nil || !strings.Contains(err.Error(), "cross-server") {
		t.Fatalf("expected cross-server guard, got %v", err)
	}
}

func TestClientTextLimits(t *testing.T) {
	d := Draft{TargetName:"P", TargetUID:"1", Title: strings.Repeat("x", 51), Contents:"C", SendLocalTime:1}
	if _, err := BuildPrivateSameServerDryRun(d); err == nil {
		t.Fatal("expected title limit error")
	}
	d.Title="T"
	d.Contents=strings.Repeat("x", 2001)
	if _, err := BuildPrivateSameServerDryRun(d); err == nil {
		t.Fatal("expected contents limit error")
	}
}
