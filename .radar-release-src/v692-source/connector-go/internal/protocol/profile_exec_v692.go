package protocol

import (
	"errors"
	"strings"
)

// WFGG_RADAR_NATIVE_PROFILE_EXEC_DIAGNOSTICS_V692
// WFGG_RADAR_PROFILE_PANIC_FINGERPRINT_V694
// profileExecutionFailureV692 classifies failures that happen before the native
// helper can return a valid JSON report. It deliberately exposes only stable,
// non-secret aggregate error codes; stderr contents are never propagated.
func profileExecutionFailureV692(runErr error, stdout, stderr []byte) error {
	stderrText := strings.ToLower(string(stderr))
	if strings.Contains(stderrText, "panic:") || strings.Contains(stderrText, "fatal error:") {
		return errors.New(profilePanicCodeV694(stderrText))
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

// profilePanicCodeV694 fingerprints only the helper stack location/panic family.
// It never returns the panic message, stack trace, paths, UIDs, tokens or payloads.
func profilePanicCodeV694(stderrText string) string {
	switch {
	case strings.Contains(stderrText, "cloneprofilebatchobjectv69"),
		strings.Contains(stderrText, "cloneprofilebatcharrayv69"),
		strings.Contains(stderrText, "cloneprofilebatchvaluev69"),
		strings.Contains(stderrText, "replaceprofileuidvaluev69"):
		return "LASTWAR_PLAYER_PROFILE_PANIC_CLONE"
	case strings.Contains(stderrText, "sfs.encodeobject"),
		strings.Contains(stderrText, "writevaluepayload"):
		return "LASTWAR_PLAYER_PROFILE_PANIC_ENCODE"
	case strings.Contains(stderrText, "sfs.encodepacket"):
		return "LASTWAR_PLAYER_PROFILE_PANIC_FRAME"
	case strings.Contains(stderrText, "sfs.readpacket"):
		return "LASTWAR_PLAYER_PROFILE_PANIC_READ"
	case strings.Contains(stderrText, "sfs.decodeobject"):
		return "LASTWAR_PLAYER_PROFILE_PANIC_DECODE"
	case strings.Contains(stderrText, "findprofilev3"):
		return "LASTWAR_PLAYER_PROFILE_PANIC_PROFILE_PARSE"
	case strings.Contains(stderrText, "findplayerscanv3templates"):
		return "LASTWAR_PLAYER_PROFILE_PANIC_TEMPLATE_DISCOVERY"
	}

	// Fallbacks preserve useful crash-family information without exposing raw
	// runtime text if the panic originates in a function we do not know yet.
	switch {
	case strings.Contains(stderrText, "nil pointer"):
		return "LASTWAR_PLAYER_PROFILE_PANIC_NIL"
	case strings.Contains(stderrText, "interface conversion"):
		return "LASTWAR_PLAYER_PROFILE_PANIC_TYPE"
	case strings.Contains(stderrText, "index out of range"),
		strings.Contains(stderrText, "slice bounds out of range"):
		return "LASTWAR_PLAYER_PROFILE_PANIC_BOUNDS"
	case strings.Contains(stderrText, "assignment to entry in nil map"):
		return "LASTWAR_PLAYER_PROFILE_PANIC_MAP"
	default:
		return "LASTWAR_PLAYER_PROFILE_HELPER_PANIC"
	}
}
