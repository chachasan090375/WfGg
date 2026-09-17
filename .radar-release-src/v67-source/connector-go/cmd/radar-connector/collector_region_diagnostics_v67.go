package main

import (
	"context"

	"wfgg-radar-connector/internal/protocol"
)

// collectorRegionDiagnosticV67 is deliberately aggregate-only. It is safe to
// expose through the Radar job status and contains no raw protocol payload.
type collectorRegionDiagnosticV67 struct {
	Region         int `json:"region"`
	OriginX        int `json:"originX"`
	OriginY        int `json:"originY"`
	Requests       int `json:"requests"`
	Packets        int `json:"packets"`
	DecodeErrors   int `json:"decodeErrors"`
	Blobs          int `json:"blobs"`
	ProtoValid     int `json:"protoValid"`
	PlayerCities   int `json:"playerCities"`
	DetailParsed   int `json:"detailParsed"`
	UIDPresent     int `json:"uidPresent"`
	NamePresent    int `json:"namePresent"`
	PlayersDecoded int `json:"playersDecoded"`
	QueryMatches   int `json:"queryMatches"`
	ReadTimeouts   int `json:"readTimeouts"`
	Accepted       int `json:"accepted"`
}

func scanCollectorRegionV67(ctx context.Context, game protocol.Client, fallback protocol.RegionScanner, token string, region int) ([]protocol.Player, protocol.RegionScanDiagnostic, error) {
	if scanner, ok := game.(protocol.RegionDiagnosticScanner); ok {
		return scanner.ScanPlayerRegionDiagnostic(ctx, token, "*", region)
	}
	players, err := fallback.ScanPlayerRegion(ctx, token, "*", region)
	return players, protocol.RegionScanDiagnostic{OriginIndex: region}, err
}

func publicCollectorRegionDiagnosticV67(region int, d protocol.RegionScanDiagnostic, accepted int) collectorRegionDiagnosticV67 {
	return collectorRegionDiagnosticV67{
		Region:         region + 1,
		OriginX:        d.OriginX,
		OriginY:        d.OriginY,
		Requests:       d.Requests,
		Packets:        d.Packets,
		DecodeErrors:   d.DecodeErrors,
		Blobs:          d.Blobs,
		ProtoValid:     d.ProtoValid,
		PlayerCities:   d.PlayerCities,
		DetailParsed:   d.DetailParsed,
		UIDPresent:     d.UIDPresent,
		NamePresent:    d.NamePresent,
		PlayersDecoded: d.PlayersDecoded,
		QueryMatches:   d.QueryMatches,
		ReadTimeouts:   d.ReadTimeouts,
		Accepted:       accepted,
	}
}
