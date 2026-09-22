package main

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestMessengerOutboxBridgeV624RejectsRelativePaths(t *testing.T) {
	t.Setenv("WFGG_MESSENGER_OUTBOX_BIN", "relative/helper")
	t.Setenv("WFGG_MESSENGER_OUTBOX_LEDGER", "/tmp/outbox.jsonl")
	_, err := messengerOutboxRunV624(context.Background(), nil, "list")
	if err == nil || !strings.Contains(err.Error(), "BIN_MUST_BE_ABSOLUTE") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestMessengerOutboxBridgeV624RunsLocalHelperOnly(t *testing.T) {
	dir := t.TempDir()
	bin := filepath.Join(dir, "helper")
	ledger := filepath.Join(dir, "outbox.jsonl")
	script := "#!/bin/sh\nprintf '%s\\n' '{\"state\":\"DRAFT\",\"id\":\"0123456789abcdef01234567\"}'\n"
	if err := os.WriteFile(bin, []byte(script), 0o700); err != nil { t.Fatal(err) }
	t.Setenv("WFGG_MESSENGER_OUTBOX_BIN", bin)
	t.Setenv("WFGG_MESSENGER_OUTBOX_LEDGER", ledger)

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	got, err := messengerOutboxRunV624(ctx, []byte(`{"targetUid":"1"}`), "create")
	if err != nil { t.Fatal(err) }
	m, ok := got.(map[string]any)
	if !ok || m["state"] != "DRAFT" {
		t.Fatalf("unexpected payload %#v", got)
	}
}

func TestMessengerOutboxIDV624(t *testing.T) {
	for _, tc := range []struct{ id string; ok bool }{
		{"0123456789abcdef01234567", true},
		{"0123456789ABCDEF01234567", false},
		{"../etc/passwd", false},
		{"abc", false},
	} {
		if messengerOutboxIDV624.MatchString(tc.id) != tc.ok {
			t.Fatalf("id %q mismatch", tc.id)
		}
	}
}
