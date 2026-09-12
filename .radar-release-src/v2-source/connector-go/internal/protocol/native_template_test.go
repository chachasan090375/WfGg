package protocol

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestNativeTemplateSnapshotUsesPhase5ReportAndNeverExposesToken(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell fixture")
	}
	dir := t.TempDir()
	capture := filepath.Join(dir, "native.pcap")
	if err := os.WriteFile(capture, []byte("fixture"), 0600); err != nil {
		t.Fatal(err)
	}
	bin := filepath.Join(dir, "probe")
	script := `#!/bin/sh
set -eu
capture="$1"
session="$2"
[ -s "$capture" ]
python3 - "$session" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x['accessToken']=='PHASE5-LIVE-TOKEN-123456'
assert x['zone']=='APS783'
PY
printf '%s\n' '{"ok":true,"mode":"native-template-readonly-v1","loginResponse":"OK","initReceived":true,"nativeFields":41,"copiedNative":35,"freshDynamic":6,"zone":"APS783","serverId":"783","resolvedAddress":"203.0.113.8:17783","topFields":246,"heroes":31,"buildings":44,"science":12,"pseudo":"RadarOwner","initTopKeys":["userHero","building_new","science_new"]}'
`
	if err := os.WriteFile(bin, []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	c := &NativeTemplateReadonly{Bin: bin, CapturePath: capture, Context: SessionContext{Zone: "APS783", GameUID: "game-123", DeviceID: "dev-1", ShumeiBoxID: "shumei-1"}}
	snap, err := c.Snapshot(context.Background(), "PHASE5-LIVE-TOKEN-123456")
	if err != nil {
		t.Fatal(err)
	}
	if !snap.Readonly || snap.Source != "wfgg/master-v3/phase5-native-template" {
		t.Fatalf("unexpected snapshot %+v", snap)
	}
	if snap.Identity == nil || snap.Identity.Pseudo != "RadarOwner" || snap.Identity.GameUID != "game-123" {
		t.Fatalf("identity %+v", snap.Identity)
	}
	if snap.Session.ServerID != "783" || snap.Session.ResolvedAddress != "203.0.113.8:17783" {
		t.Fatalf("session %+v", snap.Session)
	}
	if len(snap.Observations) < 10 {
		t.Fatalf("too few observations %d", len(snap.Observations))
	}
	for _, o := range snap.Observations {
		if strings.Contains(strings.ToLower(o.Path), "token") || strings.Contains(strings.ToLower(toString(o.Value)), "phase5-live-token") {
			t.Fatalf("token leaked in observation %+v", o)
		}
	}
}

func TestNativeTemplateRejectedMapsToAuthRejected(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell fixture")
	}
	dir := t.TempDir()
	capture := filepath.Join(dir, "native.pcap")
	_ = os.WriteFile(capture, []byte("fixture"), 0600)
	bin := filepath.Join(dir, "probe")
	script := `#!/bin/sh
printf '%s\n' '{"ok":false,"mode":"native-template-readonly-v1","loginResponse":"REJECTED","errorCode":28}'
exit 2
`
	if err := os.WriteFile(bin, []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	c := &NativeTemplateReadonly{Bin: bin, CapturePath: capture, Context: SessionContext{Zone: "APS783", GameUID: "game-123", DeviceID: "dev-1", ShumeiBoxID: "shumei-1"}}
	_, err := c.Snapshot(context.Background(), "PHASE5-LIVE-TOKEN-123456")
	if err == nil || err.Error() != "LASTWAR_AUTH_REJECTED" {
		t.Fatalf("got %v", err)
	}
}

func toString(v any) string {
	switch x := v.(type) {
	case string:
		return x
	default:
		return ""
	}
}
