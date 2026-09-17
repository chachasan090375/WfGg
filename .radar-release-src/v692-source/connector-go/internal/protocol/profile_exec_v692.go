package protocol

import (
	"errors"
	"strings"
)

// WFGG_RADAR_NATIVE_PROFILE_EXEC_DIAGNOSTICS_V692
// profileExecutionFailureV692 classifies failures that happen before the native
// helper can return a valid JSON report. It deliberately exposes only a stable
// aggregate error code; stderr contents are never propagated to the client.
func profileExecutionFailureV692(runErr error, stdout, stderr []byte) error {
	stderrText := strings.ToLower(string(stderr))
	if strings.Contains(stderrText, "panic:") || strings.Contains(stderrText, "fatal error:") {
		return errors.New("LASTWAR_PLAYER_PROFILE_HELPER_PANIC")
	}

	if runErr != nil {
		runText := strings.ToLower(strings.TrimSpace(runErr.Error()))
		if strings.Contains(runText, "signal:") || strings.Contains(runText, "segmentation fault") {
			return errors.New("LASTWAR_PLAYER_PROFILE_HELPER_CRASH")
		}
		// A normal non-zero child exit is expected to be accompanied by the
		// helper's JSON failure report. Anything else means the executable could
		// not be started or supervised correctly.
		if !strings.Contains(runText, "exit status") && !strings.Contains(runText, "exited with") {
			return errors.New("LASTWAR_PLAYER_PROFILE_HELPER_EXEC_FAILED")
		}
	}

	if strings.TrimSpace(string(stdout)) == "" {
		return errors.New("LASTWAR_PLAYER_PROFILE_HELPER_NO_REPORT")
	}
	return errors.New("LASTWAR_PLAYER_PROFILE_HELPER_REPORT_INVALID")
}
