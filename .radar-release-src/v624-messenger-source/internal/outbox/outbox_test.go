package outbox

import (
	"path/filepath"
	"testing"
	"time"

	"wfgg-lastwar-messenger-v624/internal/mailcontract"
)

func sampleDraft() mailcontract.Draft {
	return mailcontract.Draft{
		TargetName: "Player",
		TargetUID: "7568966261000065",
		Title: "Recruitment",
		Contents: "Hello from WfGg",
		SendLocalTime: 1700000000,
		SenderServer: 8120,
		TargetServer: 8120,
	}
}

func TestCreateQueueHistoryAndReplay(t *testing.T) {
	path := filepath.Join(t.TempDir(), "outbox.jsonl")
	s, err := Open(path)
	if err != nil { t.Fatal(err) }

	t0 := time.Unix(1700000000, 0).UTC()
	r, reused, err := s.CreateOrReuse(sampleDraft(), t0)
	if err != nil { t.Fatal(err) }
	if reused || r.State != StateDraft || r.Revision != 1 {
		t.Fatalf("unexpected create result: reused=%v record=%#v", reused, r)
	}
	q, err := s.Queue(r.ID, t0.Add(time.Second))
	if err != nil { t.Fatal(err) }
	if q.State != StateQueued || q.Revision != 2 {
		t.Fatalf("unexpected queued record: %#v", q)
	}
	h, err := s.History(r.ID)
	if err != nil { t.Fatal(err) }
	if len(h) != 2 || h[0].State != StateDraft || h[1].State != StateQueued {
		t.Fatalf("unexpected history: %#v", h)
	}

	s2, err := Open(path)
	if err != nil { t.Fatal(err) }
	got, ok, err := s2.Get(r.ID)
	if err != nil { t.Fatal(err) }
	if !ok || got.State != StateQueued || got.Revision != 2 {
		t.Fatalf("replay mismatch: ok=%v got=%#v", ok, got)
	}
}

func TestActiveDuplicateIsReused(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "outbox.jsonl"))
	if err != nil { t.Fatal(err) }
	d := sampleDraft()
	first, reused, err := s.CreateOrReuse(d, time.Unix(1,0))
	if err != nil { t.Fatal(err) }
	if reused { t.Fatal("first insert unexpectedly reused") }
	second, reused, err := s.CreateOrReuse(d, time.Unix(2,0))
	if err != nil { t.Fatal(err) }
	if !reused || first.ID != second.ID {
		t.Fatalf("duplicate was not reused: first=%s second=%s reused=%v", first.ID, second.ID, reused)
	}
}

func TestCancelledMessageCanBeCreatedAgain(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "outbox.jsonl"))
	if err != nil { t.Fatal(err) }
	d := sampleDraft()
	first, _, err := s.CreateOrReuse(d, time.Unix(1,0))
	if err != nil { t.Fatal(err) }
	if _, err := s.Cancel(first.ID, time.Unix(2,0)); err != nil { t.Fatal(err) }

	second, reused, err := s.CreateOrReuse(d, time.Unix(3,0))
	if err != nil { t.Fatal(err) }
	if reused || second.ID == first.ID {
		t.Fatalf("cancelled message should allow a fresh draft: first=%s second=%s reused=%v", first.ID, second.ID, reused)
	}
}

func TestOutboxKeepsDryRunSafetyBoundary(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "outbox.jsonl"))
	if err != nil { t.Fatal(err) }
	r, _, err := s.CreateOrReuse(sampleDraft(), time.Unix(1,0))
	if err != nil { t.Fatal(err) }
	if r.DryRun.NetworkEnabled || r.DryRun.MutationExecuted {
		t.Fatalf("unsafe dry-run persisted: %#v", r.DryRun)
	}
	if r.DryRun.Command != "mail.send" || r.DryRun.MailType != 21 {
		t.Fatalf("unexpected protocol contract: %#v", r.DryRun)
	}
}

func TestCrossServerCannotEnterOutbox(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "outbox.jsonl"))
	if err != nil { t.Fatal(err) }
	d := sampleDraft()
	d.TargetServer = 8131
	if _, _, err := s.CreateOrReuse(d, time.Unix(1,0)); err == nil {
		t.Fatal("cross-server draft unexpectedly accepted")
	}
}
