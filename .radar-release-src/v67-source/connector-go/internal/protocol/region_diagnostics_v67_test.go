package protocol

import "testing"

func TestParseRegionDiagnosticV67(t *testing.T) {
	raw := []byte("noise\nWFGG_SCAN_V67 requests=20 packets=14 decode_errors=2 objects=31 arrays=7 blobs=44 proto=40 kind6=12 detail3_present=11 detail_parse_ok=10 uid_present=9 name14_present=8 decoded_players=7 query_matches=7 origins=1 read_timeouts=1\n")
	d := parseRegionDiagnosticV67(raw, 4)
	if d.OriginIndex != 4 || d.OriginX != 1000 || d.OriginY != 1000 {
		t.Fatalf("unexpected center origin: %+v", d)
	}
	if d.Requests != 20 || d.Packets != 14 || d.PlayerCities != 12 || d.DetailParsed != 10 || d.PlayersDecoded != 7 || d.QueryMatches != 7 {
		t.Fatalf("unexpected counters: %+v", d)
	}
}

func TestParseRegionDiagnosticV67IgnoresUntrustedStderr(t *testing.T) {
	raw := []byte("token=secret\nWFGG_SCAN_V43 packets=999\n")
	d := parseRegionDiagnosticV67(raw, 8)
	if d.Packets != 0 {
		t.Fatalf("legacy or untrusted line must not be parsed: %+v", d)
	}
	if d.OriginX != 2000 || d.OriginY != 2000 {
		t.Fatalf("unexpected region 9 origin: %+v", d)
	}
}
