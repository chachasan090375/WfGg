package main

import (
	"context"
	"fmt"
	"strings"
	"unicode"
)

// FEDERATED_DIAGNOSTICS_V65 preserves only bounded machine-safe failure codes.
// Raw stderr/stdout, credentials, session material and request payloads are never
// copied into Collector jobs or returned to the browser.
type collectorFailureDiagnosticV65 struct {
	Category     string
	Code         string
	Cause        string
	FailurePhase string
	ServerTarget string
	AuthState    string
}

func safeCollectorCodeV65(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return "UNKNOWN"
	}
	var b strings.Builder
	for _, r := range strings.ToUpper(value) {
		if unicode.IsLetter(r) || unicode.IsDigit(r) || r == '_' || r == '-' || r == ':' {
			b.WriteRune(r)
		} else if unicode.IsSpace(r) {
			b.WriteByte('_')
		}
		if b.Len() >= 96 {
			break
		}
	}
	out := strings.Trim(b.String(), "_-:")
	if out == "" {
		return "UNKNOWN"
	}
	return out
}

func safeCollectorCauseV65(err error, fallback string) string {
	if err == nil {
		return safeCollectorCodeV65(fallback)
	}
	if err == context.DeadlineExceeded || err == context.Canceled {
		return "TIMEOUT"
	}
	raw := strings.TrimSpace(err.Error())
	low := strings.ToLower(raw)
	if strings.HasPrefix(low, "collector http ") {
		var status int
		if _, scanErr := fmt.Sscanf(low, "collector http %d", &status); scanErr == nil && status >= 100 && status <= 599 {
			return fmt.Sprintf("COLLECTOR_HTTP_%d", status)
		}
	}
	return safeCollectorCodeV65(raw)
}

func federatedServerTargetV65(query string) string {
	q := strings.TrimSpace(query)
	const prefix = "@federated:"
	if !strings.HasPrefix(strings.ToLower(q), prefix) {
		return ""
	}
	tail := strings.TrimSpace(q[len(prefix):])
	if len(tail) >= 3 && strings.EqualFold(tail[:3], "APS") {
		tail = tail[3:]
	}
	var digits strings.Builder
	for _, r := range tail {
		if r < '0' || r > '9' {
			break
		}
		digits.WriteRune(r)
		if digits.Len() >= 8 {
			break
		}
	}
	if digits.Len() == 0 {
		return ""
	}
	return digits.String()
}

func classifyCollectorFailureV65(code, cause string) string {
	joined := safeCollectorCodeV65(code) + ":" + safeCollectorCodeV65(cause)
	has := func(parts ...string) bool {
		for _, part := range parts {
			if strings.Contains(joined, part) {
				return true
			}
		return false
	}

	switch {
	case has("AUTH_REJECTED", "GAME_TOKEN_REQUIRED", "CREDENTIAL_REJECTED"):
		return "AUTH"
	case has("INGEST", "DELTA_READ", "COLLECTOR_HTTP_4", "COLLECTOR_HTTP_5"):
		return "INGEST"
	case has("REPORT_INVALID", "CAPTURE_INVALID", "DECODE", "JSON_FAILED", "PARSE_FAILED"):
		return "DECODE"
	case has("DIAL_FAILED", "READ_FAILED", "SEND_FAILED", "WRITE_FAILED", "TIMEOUT", "CONNECTION", "NETWORK"):
		return "NETWORK"
	case has("SERVER_TARGET", "REGION_INVALID", "ORIGIN_INDEX", "FEDERATED_TARGET"):
		return "SERVER_TARGET"
	default:
		return "PROTOCOL"
	}
}

func buildCollectorFailureDiagnosticV65(query, phase string, region int, code string, cause error) collectorFailureDiagnosticV65 {
	causeCode := safeCollectorCauseV65(cause, code)
	category := classifyCollectorFailureV65(code, causeCode)
	authState := "UNKNOWN"
	if category == "AUTH" {
		authState = "REJECTED"
	}
	return collectorFailureDiagnosticV65{
		Category:     category,
		Code:         safeCollectorCodeV65(code),
		Cause:        causeCode,
		FailurePhase: safeCollectorCodeV65(phase),
		ServerTarget: federatedServerTargetV65(query),
		AuthState:    authState,
	}
}
