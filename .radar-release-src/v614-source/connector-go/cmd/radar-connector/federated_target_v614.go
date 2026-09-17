package main

import (
	"context"
	"errors"
	"strconv"
	"strings"

	"wfgg-radar-connector/internal/protocol"
)

// WFGG_RADAR_TARGETED_FEDERATED_SERVER_V614
func federatedServerTargetV614(query string) (string, bool) {
	q := strings.TrimSpace(query)
	const prefix = "@federated:"
	if len(q) < len(prefix) || !strings.EqualFold(q[:len(prefix)], prefix) {
		return "", false
	}
	raw := strings.TrimSpace(q[len(prefix):])
	raw = strings.TrimPrefix(strings.ToUpper(raw), "APS")
	if raw == "" || len(raw) > 8 {
		return "", false
	}
	for _, r := range raw {
		if r < '0' || r > '9' {
			return "", false
		}
	}
	n, err := strconv.Atoi(raw)
	if err != nil || n <= 0 {
		return "", false
	}
	return strconv.Itoa(n), true
}

func scanCollectorRegionTargetV614(ctx context.Context, game protocol.Client, fallback protocol.RegionScanner, token string, region int, query string) ([]protocol.Player, protocol.RegionScanDiagnostic, error) {
	target, targeted := federatedServerTargetV614(query)
	if !targeted {
		return scanCollectorRegionV67(ctx, game, fallback, token, region)
	}
	if scanner, ok := game.(protocol.FederatedRegionDiagnosticScanner); ok {
		return scanner.ScanPlayerRegionDiagnosticOnServer(ctx, token, "*", region, target)
	}
	return nil, protocol.RegionScanDiagnostic{OriginIndex: region}, errors.New("FEDERATED_TARGET_SCANNER_UNAVAILABLE")
}
