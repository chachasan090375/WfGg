package protocol

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestExecReadonlySnapshotIsReadonlyAndRedactsSecrets(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell fixture")
	}
	dir := t.TempDir()
	bin := filepath.Join(dir, "fake-lastwar-client")
	script := `#!/bin/sh
set -eu
cfg=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -config) cfg="$2"; shift 2 ;;
    -list-buildings|-log-level) if [ "$1" = "-log-level" ]; then shift 2; else shift; fi ;;
    -collect|-interactive) echo "MUTATION FLAG FORBIDDEN" >&2; exit 9 ;;
    *) shift ;;
  esac
done
printf '%s\n' '{"time":"x","level":"INFO","msg":"login OK","username":"RadarOwner","token":"SHOULD-NOT-LEAK","deviceId":"SHOULD-NOT-LEAK"}' >&2
printf '%s\n' 'building uuid=1 level=30' >&1
# emulate a serverInfo redirect persisted by the reference client
python3 - "$cfg" <<'PY'
import json,sys
p=sys.argv[1]
x=json.load(open(p))
x['zone']='APS8092'; x['ip']='198.51.100.7'; x['port']=18092
json.dump(x,open(p,'w'))
PY
`
	if err := os.WriteFile(bin, []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	c := &ExecReadonly{Bin: bin, Context: SessionContext{IP: "203.0.113.2", Port: 17783, Zone: "APS783", GameUID: "uid-123", DeviceID: "dev-1", ShumeiBoxID: "fp-1", IOSMode: true}}
	snap, err := c.Snapshot(context.Background(), "FAKE-LIVE-TOKEN-123456")
	if err != nil {
		t.Fatal(err)
	}
	if !snap.Readonly {
		t.Fatal("snapshot must be readonly")
	}
	if !snap.Session.Redirected || snap.Session.ZoneID != "APS8092" || snap.Session.ServerID != "8092" {
		t.Fatalf("redirect not detected: %+v", snap.Session)
	}
	if snap.Identity == nil || snap.Identity.Pseudo != "RadarOwner" {
		t.Fatalf("identity not observed: %+v", snap.Identity)
	}
	for _, o := range snap.Observations {
		if o.Path == "runtime.token" || o.Path == "runtime.deviceId" {
			t.Fatalf("secret leaked in observations: %+v", o)
		}
	}
}

func TestExecReadonlyAuthRejectExitCode2(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell fixture")
	}
	dir := t.TempDir()
	bin := filepath.Join(dir, "fake")
	if err := os.WriteFile(bin, []byte("#!/bin/sh\nexit 2\n"), 0700); err != nil {
		t.Fatal(err)
	}
	c := &ExecReadonly{Bin: bin, Context: SessionContext{IP: "203.0.113.2", Port: 17783, Zone: "APS783", GameUID: "uid-123", DeviceID: "dev-1"}}
	_, err := c.Snapshot(context.Background(), "FAKE-LIVE-TOKEN-123456")
	if err == nil || err.Error() != "LASTWAR_AUTH_REJECTED" {
		t.Fatalf("got %v", err)
	}
}
