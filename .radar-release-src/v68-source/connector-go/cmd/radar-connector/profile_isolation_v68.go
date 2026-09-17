package main

import (
	"context"
	"errors"
	"strings"
	"unicode"

	"wfgg-radar-connector/internal/protocol"
)

// WFGG_RADAR_PROFILE_ISOLATION_V68
// Profile enrichment is deliberately best-effort: map observations are already
// valid Collector evidence and must never be discarded because a later profile
// read fails. Failed batches are bisected until the failing subset is isolated,
// subject to a hard attempt budget.
const v68ProfileAttemptBudget = 192

type collectorProfileFailureV68 struct {
	Scope     string `json:"scope"`
	BatchSize int    `json:"batchSize"`
	Code      string `json:"code"`
}

type collectorProfileStatsV68 struct {
	Status             string                       `json:"status"`
	Requested          int                          `json:"requested"`
	Attempts           int                          `json:"attempts"`
	BatchesSucceeded   int                          `json:"batchesSucceeded"`
	BatchesFailed      int                          `json:"batchesFailed"`
	ProfilesReturned   int                          `json:"profilesReturned"`
	ProfilesResolved   int                          `json:"profilesResolved"`
	ProfilesUnresolved int                          `json:"profilesUnresolved"`
	ProfilesAccepted   int                          `json:"profilesAccepted"`
	SinglesFailed      int                          `json:"singlesFailed"`
	IngestFailures     int                          `json:"ingestFailures"`
	BudgetExhausted    bool                         `json:"budgetExhausted"`
	ContextDone        bool                         `json:"contextDone"`
	Failures           []collectorProfileFailureV68 `json:"failures,omitempty"`
}

type profileIngestV68 func(context.Context, []protocol.Player, int64) (int, error)

func safeProfileCodeV68(err error) string {
	if err == nil {
		return "PROFILE_UNKNOWN"
	}
	raw := strings.TrimSpace(err.Error())
	if raw == "" {
		return "PROFILE_UNKNOWN"
	}
	if i := strings.IndexAny(raw, ":\r\n\t"); i >= 0 {
		raw = raw[:i]
	}
	var b strings.Builder
	lastUnderscore := false
	for _, r := range raw {
		if unicode.IsLetter(r) || unicode.IsDigit(r) || r == '_' || r == '-' || r == '.' {
			b.WriteRune(unicode.ToUpper(r))
			lastUnderscore = r == '_'
		} else if b.Len() > 0 && !lastUnderscore {
			b.WriteByte('_')
			lastUnderscore = true
		}
		if b.Len() >= 96 {
			break
		}
	}
	out := strings.Trim(b.String(), "_")
	if out == "" {
		return "PROFILE_UNKNOWN"
	}
	return out
}

func addProfileFailureV68(s *collectorProfileStatsV68, scope string, batchSize int, err error) {
	if s == nil || len(s.Failures) >= 32 {
		return
	}
	s.Failures = append(s.Failures, collectorProfileFailureV68{
		Scope: scope, BatchSize: batchSize, Code: safeProfileCodeV68(err),
	})
}

func cleanProfileUIDsV68(uids []string) []string {
	seen := map[string]bool{}
	out := make([]string, 0, len(uids))
	for _, uid := range uids {
		uid = strings.TrimSpace(uid)
		if uid == "" || seen[uid] {
			continue
		}
		seen[uid] = true
		out = append(out, uid)
	}
	return out
}

func enrichProfilesIsolatedV68(
	ctx context.Context,
	scanner protocol.ProfileScanner,
	token string,
	uids []string,
	cycleID int64,
	ingest profileIngestV68,
) collectorProfileStatsV68 {
	clean := cleanProfileUIDsV68(uids)
	stats := collectorProfileStatsV68{Requested: len(clean)}
	if len(clean) == 0 {
		stats.Status = "NONE"
		return stats
	}
	resolved := map[string]bool{}

	var visit func([]string)
	visit = func(batch []string) {
		if len(batch) == 0 {
			return
		}
		if ctx.Err() != nil {
			stats.ContextDone = true
			addProfileFailureV68(&stats, "CONTEXT", len(batch), ctx.Err())
			return
		}
		if stats.Attempts >= v68ProfileAttemptBudget {
			stats.BudgetExhausted = true
			addProfileFailureV68(&stats, "BUDGET", len(batch), errors.New("PROFILE_ATTEMPT_BUDGET_EXHAUSTED"))
			return
		}

		stats.Attempts++
		players, err := scanner.ScanProfiles(ctx, token, batch)
		if err != nil {
			stats.BatchesFailed++
			addProfileFailureV68(&stats, "SCAN", len(batch), err)
			if len(batch) == 1 {
				stats.SinglesFailed++
				return
			}
			mid := len(batch) / 2
			visit(batch[:mid])
			visit(batch[mid:])
			return
		}

		stats.BatchesSucceeded++
		stats.ProfilesReturned += len(players)
		returned := map[string]bool{}
		for _, p := range players {
			uid := strings.TrimSpace(p.GameUID)
			if uid == "" {
				continue
			}
			returned[uid] = true
			resolved[uid] = true
		}
		if len(players) > 0 && ingest != nil {
			accepted, ingestErr := ingest(ctx, players, cycleID)
			if ingestErr != nil {
				stats.IngestFailures++
				addProfileFailureV68(&stats, "INGEST", len(batch), ingestErr)
			} else {
				stats.ProfilesAccepted += accepted
			}
		}

		missing := make([]string, 0, len(batch))
		for _, uid := range batch {
			if !returned[uid] {
				missing = append(missing, uid)
			}
		}
		if len(missing) == 0 {
			return
		}
		if len(batch) == 1 {
			stats.SinglesFailed++
			addProfileFailureV68(&stats, "EMPTY", 1, errors.New("PROFILE_NOT_RETURNED"))
			return
		}
		// A partial/empty multi response is itself useful protocol evidence. Retry
		// only the missing subset so successful profiles are never fetched twice.
		visit(missing)
	}

	for start := 0; start < len(clean); start += 50 {
		end := start + 50
		if end > len(clean) {
			end = len(clean)
		}
		visit(clean[start:end])
		if stats.BudgetExhausted || stats.ContextDone {
			break
		}
	}

	stats.ProfilesResolved = len(resolved)
	stats.ProfilesUnresolved = stats.Requested - stats.ProfilesResolved
	switch {
	case stats.ContextDone:
		stats.Status = "PARTIAL_CONTEXT"
	case stats.BudgetExhausted && stats.ProfilesResolved > 0:
		stats.Status = "PARTIAL_BUDGET"
	case stats.BudgetExhausted:
		stats.Status = "FAILED_BUDGET"
	case stats.ProfilesUnresolved == 0 && stats.IngestFailures == 0:
		stats.Status = "COMPLETE"
	case stats.ProfilesResolved > 0:
		stats.Status = "PARTIAL"
	default:
		stats.Status = "FAILED"
	}
	return stats
}
