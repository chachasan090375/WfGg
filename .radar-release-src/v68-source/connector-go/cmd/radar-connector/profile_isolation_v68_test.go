package main

import (
	"context"
	"errors"
	"testing"

	"wfgg-radar-connector/internal/protocol"
)

type fakeProfileScannerV68 struct {
	fn func([]string) ([]protocol.Player, error)
}

func (f fakeProfileScannerV68) ScanProfiles(_ context.Context, _ string, uids []string) ([]protocol.Player, error) {
	return f.fn(uids)
}

func TestV68SplitsFailedBatchAndPreservesSuccess(t *testing.T) {
	scanner := fakeProfileScannerV68{fn: func(uids []string) ([]protocol.Player, error) {
		if len(uids) > 1 {
			return nil, errors.New("LASTWAR_PLAYER_SCAN_FAILED")
		}
		if uids[0] == "bad" {
			return nil, errors.New("LASTWAR_PLAYER_SCAN_FAILED")
		}
		return []protocol.Player{{GameUID: uids[0], Pseudo: "ok"}}, nil
	}}
	ingest := func(_ context.Context, p []protocol.Player, _ int64) (int, error) { return len(p), nil }
	stats := enrichProfilesIsolatedV68(context.Background(), scanner, "token-123456", []string{"a", "bad", "c"}, 1, ingest)
	if stats.ProfilesResolved != 2 || stats.ProfilesUnresolved != 1 {
		t.Fatalf("resolved=%d unresolved=%d", stats.ProfilesResolved, stats.ProfilesUnresolved)
	}
	if stats.ProfilesAccepted != 2 || stats.SinglesFailed != 1 {
		t.Fatalf("accepted=%d singlesFailed=%d", stats.ProfilesAccepted, stats.SinglesFailed)
	}
	if stats.Status != "PARTIAL" {
		t.Fatalf("status=%s", stats.Status)
	}
}

func TestV68RetriesMissingSubsetFromPartialBatch(t *testing.T) {
	calls := 0
	scanner := fakeProfileScannerV68{fn: func(uids []string) ([]protocol.Player, error) {
		calls++
		if len(uids) == 3 {
			return []protocol.Player{{GameUID: "a", Pseudo: "A"}, {GameUID: "c", Pseudo: "C"}}, nil
		}
		return []protocol.Player{{GameUID: uids[0], Pseudo: "B"}}, nil
	}}
	ingest := func(_ context.Context, p []protocol.Player, _ int64) (int, error) { return len(p), nil }
	stats := enrichProfilesIsolatedV68(context.Background(), scanner, "token-123456", []string{"a", "b", "c"}, 1, ingest)
	if calls != 2 {
		t.Fatalf("calls=%d", calls)
	}
	if stats.ProfilesResolved != 3 || stats.Status != "COMPLETE" {
		t.Fatalf("resolved=%d status=%s", stats.ProfilesResolved, stats.Status)
	}
}

func TestV68SanitizesFailureCode(t *testing.T) {
	got := safeProfileCodeV68(errors.New("LASTWAR_PLAYER_SCAN_FAILED:peer=secret"))
	if got != "LASTWAR_PLAYER_SCAN_FAILED" {
		t.Fatalf("got=%q", got)
	}
}
