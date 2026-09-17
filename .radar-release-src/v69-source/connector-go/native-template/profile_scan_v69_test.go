//go:build lastwar_native_template

package main

import (
	"lastwar-client/internal/sfs"
	"testing"
)

func TestParseProfileUIDsV69(t *testing.T) {
	got, err := parseProfileUIDsV69(" 101,202,101 ")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got) != 2 || got[0] != "101" || got[1] != "202" {
		t.Fatalf("unexpected uids: %#v", got)
	}
}

func TestReplaceProfileUIDArrayV69(t *testing.T) {
	arr := sfs.NewSFSArray()
	arr.AddValue(sfs.SFSValue{Type: sfs.SFSUtfString, Val: "old"})
	got, ok := replaceProfileUIDValueV69(sfs.SFSValue{Val: arr}, []string{"101", "202"})
	if !ok {
		t.Fatal("expected replacement")
	}
	out, ok := got.Val.(*sfs.SFSArray)
	if !ok || out == nil {
		t.Fatalf("unexpected value: %#v", got.Val)
	}
	items := out.Items()
	if len(items) != 2 || items[0].Val != "101" || items[1].Val != "202" {
		t.Fatalf("unexpected array: %#v", items)
	}
}
