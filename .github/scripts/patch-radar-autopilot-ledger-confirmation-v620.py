#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
AUTOPILOT = ROOT / 'connector-go/cmd/radar-connector/server_autopilot_v6194.go'
LEDGER = ROOT / 'connector-go/cmd/radar-connector/autopilot_persistent_ledger_v61913.go'
TEST = ROOT / 'connector-go/cmd/radar-connector/autopilot_confirmation_resilience_v620_test.go'

text = AUTOPILOT.read_text(encoding='utf-8')
marker = '// WFGG_RADAR_AUTOPILOT_LEDGER_CONFIRMATION_RESILIENCE_V620'
bt = chr(96)

if marker not in text:
    text = text.replace(
        'autopilotVersionV6194                    = "v6.19.17"',
        'autopilotVersionV6194                    = "v6.20.0"',
        1,
    )
    field_anchor = '\tVerificationMode        string                          ' + bt + 'json:"verificationMode,omitempty"' + bt + '\n'
    if text.count(field_anchor) != 1:
        raise SystemExit(f'V620_CONFIRM_FIELD_ANCHOR_COUNT={text.count(field_anchor)}')
    text = text.replace(
        field_anchor,
        field_anchor
        + '\tConfirmationRetries     int                             ' + bt + 'json:"confirmationRetries,omitempty"' + bt + '\n'
        + '\tConfirmationLastError   string                          ' + bt + 'json:"confirmationLastError,omitempty"' + bt + '\n',
        1,
    )

    early = '''\t\tif autopilotPersistAndConfirmCurrentClusterV61913(jobID) {
\t\t\ttime.Sleep(1200 * time.Millisecond)
\t\t\tcontinue
\t\t}
'''
    early_new = '''\t\tif confirmed, confirmErr := autopilotPersistAndConfirmCurrentClusterV620(jobID); confirmed {
\t\t\ttime.Sleep(1200 * time.Millisecond)
\t\t\tcontinue
\t\t} else if confirmErr != "" {
\t\t\tphase := "CONFIRMATION_FAILED"
\t\t\tif strings.Contains(confirmErr, "LEDGER") {
\t\t\t\tphase = "LEDGER_WRITE_FAILED"
\t\t\t}
\t\t\tautopilotFailV6194(jobID, phase, confirmErr)
\t\t\treturn
\t\t}
'''
    if text.count(early) != 1:
        raise SystemExit(f'V620_CONFIRM_EARLY_ANCHOR_COUNT={text.count(early)}')
    text = text.replace(early, early_new, 1)

    final = '''\t\tif !autopilotPersistAndConfirmCurrentClusterV61913(jobID) {
\t\t\tautopilotFailV6194(jobID, "CONFIRMATION_FAILED", "AUTOPILOT_LEDGER_OR_CONFIRMATION_INVARIANT_V61913")
\t\t\treturn
\t\t}
'''
    final_new = '''\t\tconfirmed, confirmErr := autopilotPersistAndConfirmCurrentClusterV620(jobID)
\t\tif !confirmed {
\t\t\tif confirmErr == "" {
\t\t\t\tconfirmErr = "AUTOPILOT_CONFIRMATION_NOT_READY_V620"
\t\t\t}
\t\t\tphase := "CONFIRMATION_FAILED"
\t\t\tif strings.Contains(confirmErr, "LEDGER") {
\t\t\t\tphase = "LEDGER_WRITE_FAILED"
\t\t\t}
\t\t\tautopilotFailV6194(jobID, phase, confirmErr)
\t\t\treturn
\t\t}
'''
    if text.count(final) != 1:
        raise SystemExit(f'V620_CONFIRM_FINAL_ANCHOR_COUNT={text.count(final)}')
    text = text.replace(final, final_new, 1)

    scout_anchor = '// WFGG_RADAR_AUTOPILOT_ADAPTIVE_VERIFICATION_V61917\n'
    if text.count(scout_anchor) != 1:
        raise SystemExit(f'V620_CONFIRM_MARKER_ANCHOR_COUNT={text.count(scout_anchor)}')
    text = text.replace(scout_anchor, scout_anchor + marker + '\n', 1)

AUTOPILOT.write_text(text, encoding='utf-8')

ledger = LEDGER.read_text(encoding='utf-8')
helper_marker = '// WFGG_RADAR_AUTOPILOT_LEDGER_CONFIRMATION_HELPER_V620'
if helper_marker not in ledger:
    ledger += r'''

// WFGG_RADAR_AUTOPILOT_LEDGER_CONFIRMATION_HELPER_V620
func autopilotLedgerRetryableV620(err error) bool {
    if err == nil {
        return false
    }
    code := strings.ToUpper(strings.TrimSpace(err.Error()))
    return strings.Contains(code, "AUTOPILOT_LEDGER_WRITE_FAILED_V61913") ||
        strings.Contains(code, "AUTOPILOT_LEDGER_WRITE_TIMEOUT_V61913")
}

// V6.20 keeps the durable-ledger-before-confirm ordering, but a temporary
// SQLite writer lock must not kill a healthy 9/9 coverage campaign.
// The upsert is idempotent, so bounded retries are safe.
func autopilotPersistAndConfirmCurrentClusterV620(jobID string) (bool, string) {
    job, ok := radarAutopilotJobsV6194.get(jobID)
    if !ok || strings.TrimSpace(job.CurrentSeed) == "" || job.ValidatedCycles < job.RequiredFullCycles {
        return false, ""
    }

    delays := []time.Duration{0, 750 * time.Millisecond, 1500 * time.Millisecond, 3 * time.Second}
    var lastErr error
    for attempt, delay := range delays {
        if delay > 0 {
            time.Sleep(delay)
        }
        err := autopilotPersistCurrentSeedOutcomeV61913(jobID, "QUALIFIED", "FULL_CYCLES_QUALIFIED")
        if err == nil {
            if !autopilotConfirmCurrentClusterV6194(jobID) {
                radarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
                    a.ConfirmationLastError = "AUTOPILOT_CONFIRMATION_STATE_CHANGED_V620"
                })
                return false, "AUTOPILOT_CONFIRMATION_STATE_CHANGED_V620"
            }
            radarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
                a.ConfirmationLastError = ""
            })
            return true, ""
        }

        lastErr = err
        radarAutopilotJobsV6194.update(jobID, func(a *autopilotJobV6194) {
            a.ConfirmationLastError = err.Error()
            if attempt > 0 || autopilotLedgerRetryableV620(err) {
                a.ConfirmationRetries++
            }
            a.Phase = "LEDGER_CONFIRMATION_RETRY"
        })
        if !autopilotLedgerRetryableV620(err) {
            break
        }
    }

    if lastErr == nil {
        return false, "AUTOPILOT_LEDGER_PERSIST_FAILED_V620"
    }
    return false, "AUTOPILOT_LEDGER_PERSIST_FAILED_V620:" + lastErr.Error()
}
'''
LEDGER.write_text(ledger, encoding='utf-8')

TEST.write_text(r'''package main

import (
    "context"
    "errors"
    "testing"
)

func TestAutopilotV620FullAfterPartialPersistsAndConfirms(t *testing.T) {
    db := newLedgerDBV61913(t)
    t.Setenv("WFGG_COLLECTOR_DB", db)
    id := "v620-full-after-partial"
    radarAutopilotJobsV6194.add(&autopilotJobV6194{
        ID: id, Status: "RUNNING", Phase: "CYCLE_FULL",
        CurrentSeed: "8117", CurrentCommand: "@federated:8117",
        CurrentFullCycleIDs: []int64{94},
        RequiredFullCycles: 1, ValidatedCycles: 1, PartialCycles: 1,
        AdaptiveVerification: true, VerificationMode: "ADAPTIVE_FAST",
        History: []autopilotClusterResultV6194{}, SkippedSeeds: []autopilotSkippedSeedV6196{},
    })

    confirmed, errCode := autopilotPersistAndConfirmCurrentClusterV620(id)
    if !confirmed || errCode != "" {
        t.Fatalf("confirmed=%v err=%q", confirmed, errCode)
    }
    job, _ := radarAutopilotJobsV6194.get(id)
    if job.ConfirmedClusters != 1 || len(job.History) != 1 {
        t.Fatalf("confirmation state=%#v", job)
    }
    if job.History[0].Seed != "8117" || job.History[0].FullCycles != 1 || job.History[0].PartialCycles != 1 {
        t.Fatalf("history=%#v", job.History[0])
    }

    rows, err := autopilotLedgerReadV61913(context.Background(), db, []string{"8117"})
    if err != nil {
        t.Fatal(err)
    }
    if len(rows) != 1 || rows[0].State != "QUALIFIED" || rows[0].RequiredFullCycles != 1 || rows[0].ValidatedCycles != 1 || rows[0].PartialCycles != 1 {
        t.Fatalf("ledger=%#v", rows)
    }
}

func TestAutopilotLedgerRetryableV620(t *testing.T) {
    if !autopilotLedgerRetryableV620(errors.New("AUTOPILOT_LEDGER_WRITE_FAILED_V61913")) {
        t.Fatal("generic sqlite write failure must be retryable")
    }
    if !autopilotLedgerRetryableV620(errors.New("AUTOPILOT_LEDGER_WRITE_TIMEOUT_V61913")) {
        t.Fatal("write timeout must be retryable")
    }
    if autopilotLedgerRetryableV620(errors.New("AUTOPILOT_LEDGER_PYTHON3_MISSING_V61913")) {
        t.Fatal("structural ledger errors must remain blocking")
    }
}
''', encoding='utf-8')

print('RADAR_V620_LEDGER_CONFIRMATION_RESILIENCE=READY')
