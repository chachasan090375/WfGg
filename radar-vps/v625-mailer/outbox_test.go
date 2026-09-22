package mailer

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func validDraft() DraftRequest {
	return DraftRequest{
		CampaignID: "recruitment-v1",
		TargetUID:  "7568966261000065",
		TargetName: "Candidate",
		Title:      "WfGg",
		Contents:   "Bonjour, nous souhaitons te contacter.",
	}
}

func TestBuildSelfPayloadMatchesV624Contract(t *testing.T) {
	d := validDraft()
	p, err := BuildSelfPayload(d, 1770000000)
	if err != nil {
		t.Fatal(err)
	}
	if p.Name != d.TargetName || p.Title != d.Title || p.Contents != d.Contents {
		t.Fatalf("text fields mismatch: %#v", p)
	}
	if p.AllianceID != "" || p.TargetUID != d.TargetUID {
		t.Fatalf("1:1 routing mismatch: %#v", p)
	}
	if p.SendLocalTime != 1770000000 || p.Type != 21 || p.ServerID != nil {
		t.Fatalf("wire contract mismatch: %#v", p)
	}
}

func TestTitleAndContentLimitsAreUTF8ByteLimits(t *testing.T) {
	d := validDraft()
	d.Title = strings.Repeat("a", 50)
	if err := ValidateDraft(d); err != nil {
		t.Fatalf("50-byte title rejected: %v", err)
	}
	d.Title = strings.Repeat("a", 51)
	if err := ValidateDraft(d); err == nil {
		t.Fatal("51-byte title must be rejected")
	}
	d = validDraft()
	d.Title = strings.Repeat("é", 25) // 50 UTF-8 bytes
	if err := ValidateDraft(d); err != nil {
		t.Fatalf("50-byte UTF-8 title rejected: %v", err)
	}
	d.Title = strings.Repeat("é", 26) // 52 UTF-8 bytes
	if err := ValidateDraft(d); err == nil {
		t.Fatal("52-byte UTF-8 title must be rejected")
	}
	d = validDraft()
	d.Contents = strings.Repeat("x", 2000)
	if err := ValidateDraft(d); err != nil {
		t.Fatalf("2000-byte content rejected: %v", err)
	}
	d.Contents = strings.Repeat("x", 2001)
	if err := ValidateDraft(d); err == nil {
		t.Fatal("2001-byte content must be rejected")
	}
}

func TestQueueIsDurableAndIdempotent(t *testing.T) {
	path := filepath.Join(t.TempDir(), "mail-outbox.jsonl")
	s := &Store{Path: path}
	first, err := s.Queue(validDraft())
	if err != nil {
		t.Fatal(err)
	}
	if first.Duplicate || first.Record.State != "DRY_RUN_READY" {
		t.Fatalf("unexpected first queue: %#v", first)
	}
	second, err := s.Queue(validDraft())
	if err != nil {
		t.Fatal(err)
	}
	if !second.Duplicate || second.Record.ID != first.Record.ID {
		t.Fatalf("dedupe failed: %#v %#v", first, second)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if got := strings.Count(strings.TrimSpace(string(raw)), "\n") + 1; got != 1 {
		t.Fatalf("expected one durable record, got %d", got)
	}
	var rec OutboxRecord
	if err := json.Unmarshal([]byte(strings.TrimSpace(string(raw))), &rec); err != nil {
		t.Fatal(err)
	}
	if rec.LastWarMutation || rec.TokenPersisted || !rec.RequiresServerTime {
		t.Fatalf("dry-run safety invariant broken: %#v", rec)
	}
}

func TestDedupeIsScopedByCampaign(t *testing.T) {
	a := validDraft()
	b := a
	b.CampaignID = "recruitment-v2"
	if draftID(a) == draftID(b) {
		t.Fatal("campaign change must produce a distinct idempotency key")
	}
}

func TestLiveDispatchIsHardBlocked(t *testing.T) {
	err := DispatchLive(makeRecord(validDraft()), 1770000000)
	if !errors.Is(err, ErrLastWarWriteDisabled) {
		t.Fatalf("live dispatch must be blocked, got %v", err)
	}
}

func TestServerTimeMustBeInjectedAtDispatch(t *testing.T) {
	if _, err := BuildSelfPayload(validDraft(), 0); err == nil {
		t.Fatal("server time is required for the final wire payload")
	}
	rec := makeRecord(validDraft())
	if rec.WireTemplate.SendLocalTime != 0 || !rec.RequiresServerTime {
		t.Fatalf("outbox must not freeze a send timestamp: %#v", rec)
	}
}
