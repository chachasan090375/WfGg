package main

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"
)

// WFGG_RADAR_COLLECTOR_CYCLE_TERMINALIZATION_V6198
//
// Collector failures are often reported by the Connector immediately, but a
// transient local Collector disconnect can make the first /cycle/finish call
// fail as well. Before V6.19.8 those finish errors were deliberately ignored,
// leaving the Collector DB row RUNNING forever. V6.19.8 retries terminalization
// on a bounded schedule and verifies the terminal state after every attempt.
//
// Last War is not contacted by this helper. It only talks to the local
// Collector HTTP API.
const (
	collectorTerminalizationAttemptsV6198 = 12
	collectorTerminalizationHTTPTimeoutV6198 = 6 * time.Second
	collectorTerminalizationVerifyTimeoutV6198 = 4 * time.Second
)

func collectorTerminalizationBackoffV6198(attempt int) time.Duration {
	if attempt < 1 {
		attempt = 1
	}
	seconds := attempt * 2
	if seconds > 10 {
		seconds = 10
	}
	return time.Duration(seconds) * time.Second
}

func collectorCycleTerminalStateV6198(id int64, expected string) bool {
	ctx, cancel := context.WithTimeout(context.Background(), collectorTerminalizationVerifyTimeoutV6198)
	defer cancel()
	cycle, err := collectorCycleStatus(ctx, id)
	if err != nil {
		return false
	}
	return strings.EqualFold(strings.TrimSpace(cycle.Status), strings.TrimSpace(expected))
}

func collectorFinishCycleReliableV6198(id int64, status, errorCode string) error {
	status = strings.ToUpper(strings.TrimSpace(status))
	if id <= 0 {
		return errors.New("COLLECTOR_CYCLE_ID_INVALID")
	}
	if status != "SUCCESS" && status != "FAILED" {
		return errors.New("COLLECTOR_CYCLE_TERMINAL_STATUS_INVALID")
	}
	if collectorCycleTerminalStateV6198(id, status) {
		return nil
	}

	var lastErr error
	for attempt := 1; attempt <= collectorTerminalizationAttemptsV6198; attempt++ {
		ctx, cancel := context.WithTimeout(context.Background(), collectorTerminalizationHTTPTimeoutV6198)
		err := collectorFinishCycle(ctx, id, status, errorCode)
		cancel()

		if err == nil && collectorCycleTerminalStateV6198(id, status) {
			return nil
		}
		if err != nil {
			lastErr = err
		} else {
			lastErr = errors.New("COLLECTOR_CYCLE_TERMINAL_STATUS_NOT_APPLIED")
		}

		if attempt < collectorTerminalizationAttemptsV6198 {
			time.Sleep(collectorTerminalizationBackoffV6198(attempt))
		}
	}
	return fmt.Errorf("COLLECTOR_CYCLE_TERMINALIZATION_FAILED: %w", lastErr)
}
