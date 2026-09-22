package main

import (
	"bytes"
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"
)

func TestCLICreateQueueHistory(t *testing.T) {
	ledger := filepath.Join(t.TempDir(), "outbox.jsonl")
	draft := `{"targetName":"Player","targetUid":"123456","title":"Hello","contents":"WfGg","sendLocalTime":1700000000,"senderServer":8120,"targetServer":8120}`

	var out, errOut bytes.Buffer
	if code := run([]string{"-ledger", ledger, "create"}, strings.NewReader(draft), &out, &errOut); code != 0 {
		t.Fatalf("create code=%d stderr=%s", code, errOut.String())
	}
	var created struct {
		Record struct { ID string `json:"id"`; State string `json:"state"` } `json:"record"`
		Reused bool `json:"reused"`
	}
	if err := json.Unmarshal(out.Bytes(), &created); err != nil { t.Fatal(err) }
	if created.Record.ID == "" || created.Record.State != "DRAFT" || created.Reused {
		t.Fatalf("unexpected create response: %s", out.String())
	}

	out.Reset(); errOut.Reset()
	if code := run([]string{"-ledger", ledger, "queue", created.Record.ID}, strings.NewReader(""), &out, &errOut); code != 0 {
		t.Fatalf("queue code=%d stderr=%s", code, errOut.String())
	}
	if !strings.Contains(out.String(), `"state":"QUEUED"`) {
		t.Fatalf("queue output=%s", out.String())
	}

	out.Reset(); errOut.Reset()
	if code := run([]string{"-ledger", ledger, "history", created.Record.ID}, strings.NewReader(""), &out, &errOut); code != 0 {
		t.Fatalf("history code=%d stderr=%s", code, errOut.String())
	}
	if strings.Count(out.String(), `"revision":`) != 2 {
		t.Fatalf("history output=%s", out.String())
	}
}

func TestCLIRequiresExplicitLedger(t *testing.T) {
	t.Setenv("WFGG_MESSENGER_OUTBOX_LEDGER", "")
	var out, errOut bytes.Buffer
	if code := run([]string{"list"}, strings.NewReader(""), &out, &errOut); code != 2 {
		t.Fatalf("expected usage failure, got %d", code)
	}
}
