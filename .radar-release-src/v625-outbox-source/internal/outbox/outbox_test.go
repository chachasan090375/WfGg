package outbox

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"wfgg-lastwar-mail-outbox-v625/internal/mailcontract"
)

func request(campaign, contents string, sendTime int64) PrepareRequest {
	return PrepareRequest{
		CampaignKey: campaign,
		Trigger:     "RADAR_RECRUITMENT_MATCH",
		Draft: mailcontract.Draft{
			TargetName:    "Player",
			TargetUID:     "123456789",
			Title:         "WfGg",
			Contents:      contents,
			SendLocalTime: sendTime,
			SenderServer:  8120,
			TargetServer:  8120,
		},
	}
}

func TestPreparePersistsAndDeduplicates(t *testing.T) {
	path := filepath.Join(t.TempDir(), "outbox.json")
	store, err := NewFileStore(path)
	if err != nil {
		t.Fatal(err)
	}
	store.SetClockForTest(func() time.Time {
		return time.Date(2026, 9, 22, 6, 15, 0, 0, time.UTC)
	})

	first, created, err := store.Prepare(request("recruitment-s6", "Hello", 100))
	if err != nil || !created {
		t.Fatalf("first prepare created=%v err=%v", created, err)
	}
	if first.Status != StatusPreparedDry || first.NetworkEnabled || first.MutationExecuted {
		t.Fatalf("unsafe item: %#v", first)
	}
	second, created, err := store.Prepare(request("recruitment-s6", "Hello", 200))
	if err != nil || created {
		t.Fatalf("duplicate prepare created=%v err=%v", created, err)
	}
	if second.ID != first.ID || second.IdempotencyKey != first.IdempotencyKey {
		t.Fatalf("duplicate identity changed: first=%#v second=%#v", first, second)
	}

	items, err := store.List()
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 {
		t.Fatalf("items=%d want=1", len(items))
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Fatalf("outbox permissions=%#o want=0600", info.Mode().Perm())
	}
}

func TestSameCampaignDifferentContentConflicts(t *testing.T) {
	store, _ := NewFileStore(filepath.Join(t.TempDir(), "outbox.json"))
	if _, _, err := store.Prepare(request("campaign-a", "A", 100)); err != nil {
		t.Fatal(err)
	}
	_, _, err := store.Prepare(request("campaign-a", "B", 200))
	if err == nil || !strings.Contains(err.Error(), "OUTBOX_IDEMPOTENCY_CONFLICT") {
		t.Fatalf("expected idempotency conflict, got %v", err)
	}
}

func TestDifferentCampaignCreatesAnotherItem(t *testing.T) {
	store, _ := NewFileStore(filepath.Join(t.TempDir(), "outbox.json"))
	if _, created, err := store.Prepare(request("campaign-a", "A", 100)); err != nil || !created {
		t.Fatalf("first created=%v err=%v", created, err)
	}
	if _, created, err := store.Prepare(request("campaign-b", "A", 100)); err != nil || !created {
		t.Fatalf("second created=%v err=%v", created, err)
	}
	items, err := store.List()
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 2 {
		t.Fatalf("items=%d want=2", len(items))
	}
}

func TestCrossServerStillBlocked(t *testing.T) {
	store, _ := NewFileStore(filepath.Join(t.TempDir(), "outbox.json"))
	req := request("campaign", "A", 100)
	req.Draft.TargetServer = 8131
	_, _, err := store.Prepare(req)
	if err == nil || !strings.Contains(err.Error(), "cross-server") {
		t.Fatalf("expected cross-server guard, got %v", err)
	}
}

func TestCampaignAndTriggerRequired(t *testing.T) {
	store, _ := NewFileStore(filepath.Join(t.TempDir(), "outbox.json"))
	req := request("", "A", 100)
	if _, _, err := store.Prepare(req); err == nil {
		t.Fatal("expected missing campaign error")
	}
	req = request("campaign", "A", 100)
	req.Trigger = ""
	if _, _, err := store.Prepare(req); err == nil {
		t.Fatal("expected missing trigger error")
	}
}
