package protocol

import (
	"errors"
	"strconv"
	"strings"
)

// WFGG_RADAR_NATIVE_PROFILE_EXEC_DIAGNOSTICS_V692
// WFGG_RADAR_PROFILE_PANIC_FINGERPRINT_V694
// WFGG_RADAR_PROFILE_PANIC_SOURCE_LINE_V695
// profileExecutionFailureV692 classifies failures that happen before the native
// helper can return a valid JSON report. It deliberately exposes only stable,
// non-secret aggregate error codes; stderr contents are never propagated.
func profileExecutionFailureV692(runErr error, stdout, stderr []byte) error {
	stderrText := strings.ToLower(string(stderr))
	if strings.Contains(stderrText, "panic:") || strings.Contains(stderrText, "fatal error:") {
		return errors.New(profilePanicCodeV695(stderrText))
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

// profilePanicCodeV695 fingerprints only safe crash provenance. It never
// returns the panic message, stack trace, paths, UIDs, tokens or payloads.
func profilePanicCodeV695(stderrText string) string {
	// V6.9.4 known semantic locations.
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

	// The pinned lastwar-client SFS encoder deliberately panics on an unknown
	// encode tag. This message contains no user data and is safe to classify.
	if strings.Contains(stderrText, "unsupported encode type") {
		return "LASTWAR_PLAYER_PROFILE_PANIC_SFS_UNSUPPORTED_ENCODE_TYPE"
	}

	// V6.9.5: if a new panic family appears, keep only the first application
	// source basename + line number. Paths and raw stack contents never leave
	// the connector. This gives us a deterministic repair coordinate without
	// exposing secrets or payload data.
	if code := profilePanicSourceLineV695(stderrText); code != "" {
		return code
	}

	// Safe crash-family fallbacks.
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
		return "LASTWAR_PLAYER_PROFILE_PANIC_UNKNOWN_V695"
	}
}

func profilePanicSourceLineV695(stderrText string) string {
	for _, rawLine := range strings.Split(stderrText, "\n") {
		line := strings.ToLower(strings.TrimSpace(rawLine))
		if line == "" {
			continue
		}
		if code := sourceComponentLineCodeV695(line, "/cmd/wfgg-radar-native-template/", "LASTWAR_PLAYER_PROFILE_PANIC_NATIVE_"); code != "" {
			return code
		}
		if code := sourceComponentLineCodeV695(line, "/internal/sfs/", "LASTWAR_PLAYER_PROFILE_PANIC_SFS_"); code != "" {
			return code
		}
		if code := sourceComponentLineCodeV695(line, "/internal/auth/", "LASTWAR_PLAYER_PROFILE_PANIC_AUTH_"); code != "" {
			return code
		}
		if code := sourceComponentLineCodeV695(line, "/internal/pcap/", "LASTWAR_PLAYER_PROFILE_PANIC_PCAP_"); code != "" {
			return code
		}
		if code := sourceComponentLineCodeV695(line, "/internal/", "LASTWAR_PLAYER_PROFILE_PANIC_INTERNAL_"); code != "" {
			return code
		}
	}
	return ""
}

func sourceComponentLineCodeV695(line, segment, prefix string) string {
	idx := strings.LastIndex(line, segment)
	if idx < 0 {
		return ""
	}
	tail := line[idx+len(segment):]
	colon := strings.IndexByte(tail, ':')
	if colon <= 0 || colon+1 >= len(tail) {
		return ""
	}
	fileToken := sourceFileTokenV695(tail[:colon])
	if fileToken == "" {
		return ""
	}
	n := 0
	digits := 0
	for i := colon + 1; i < len(tail); i++ {
		c := tail[i]
		if c < '0' || c > '9' {
			break
		}
		n = n*10 + int(c-'0')
		digits++
		if n > 99999 {
			return ""
		}
	}
	if digits == 0 || n <= 0 {
		return ""
	}
	return prefix + fileToken + "_L" + strconv.Itoa(n)
}

func sourceFileTokenV695(name string) string {
	name = strings.TrimSpace(strings.TrimSuffix(name, ".go"))
	if slash := strings.LastIndexByte(name, '/'); slash >= 0 {
		name = name[slash+1:]
	}
	var b strings.Builder
	for i := 0; i < len(name); i++ {
		c := name[i]
		switch {
		case c >= 'a' && c <= 'z':
			b.WriteByte(c - ('a' - 'A'))
		case c >= 'A' && c <= 'Z', c >= '0' && c <= '9':
			b.WriteByte(c)
		case c == '_' || c == '-':
			b.WriteByte('_')
		}
	}
	return strings.Trim(b.String(), "_")
}
