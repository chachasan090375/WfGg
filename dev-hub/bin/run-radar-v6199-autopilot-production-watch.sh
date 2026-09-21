#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_DEV_HUB_RADAR_V6199_AUTOPILOT_WATCH_REV:-}"
EXPECTED_CONNECTOR="5058159307ccb99e8e631fe71014608934b8575e69d5599e4388550306baab7f"
EXPECTED_NATIVE="274d040f5294cb09422e5d55cc4b5335ac7739924c33dcb67b3f279645814900"
COLLECTOR_DB="${WFGG_COLLECTOR_DB:-/opt/wfgg-collector/data/collector.db}"
TARGET_CYCLE_ID=67

die(){ echo "RADAR_V6199_AUTOPILOT_WATCH=BLOCKED reason=$1"; exit 2; }

[ "$(id -u)" -eq 0 ] || die root_required
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || die pinned_revision_required
for c in python3 sha256sum systemctl; do command -v "$c" >/dev/null 2>&1 || die "missing_command:$c"; done
[ -r "$COLLECTOR_DB" ] || die collector_db_unreadable

echo "=== CHACHA DEV RADAR V6.19.9 AUTOPILOT PRODUCTION WATCH ==="
echo "SOURCE_REV=$REV"
echo "TARGET_CYCLE_ID=$TARGET_CYCLE_ID"

test "$(sha256sum /opt/wfgg-radar/bin/radar-connector | awk '{print $1}')" = "$EXPECTED_CONNECTOR" || die connector_sha_mismatch
test "$(sha256sum /opt/wfgg-radar/bin/radar-native-template | awk '{print $1}')" = "$EXPECTED_NATIVE" || die native_sha_mismatch
test "$(systemctl is-active wfgg-radar-connector)" = "active" || die radar_service_not_active
test "$(systemctl is-active wfgg-radar-sentinel.timer)" = "active" || die sentinel_timer_not_active
test "$(systemctl is-enabled wfgg-radar-sentinel.timer)" = "enabled" || die sentinel_not_enabled
echo "RADAR_V6199_AUTOPILOT_WATCH_PREFLIGHT=PASS"

python3 - "$COLLECTOR_DB" "$TARGET_CYCLE_ID" <<'PY'
import sqlite3,sys,time
db=sys.argv[1]; target=int(sys.argv[2]); deadline=time.time()+1200
last=None; target_terminal=False; next_seen=False

while time.time()<deadline:
    con=sqlite3.connect('file:'+db+'?mode=ro',uri=True)
    con.row_factory=sqlite3.Row
    target_row=con.execute(
      "SELECT id,query,status,COALESCE(error,'') error,COALESCE(started_at,'') started_at,"
      "COALESCE(finished_at,'') finished_at FROM cycles WHERE id=?",(target,)
    ).fetchone()
    next_row=con.execute(
      "SELECT id,query,status,COALESCE(error,'') error,COALESCE(started_at,'') started_at,"
      "COALESCE(finished_at,'') finished_at FROM cycles "
      "WHERE id>? AND lower(query) LIKE '@federated:%' ORDER BY id ASC LIMIT 1",(target,)
    ).fetchone()
    con.close()

    if not target_row:
        print("RADAR_V6199_AUTOPILOT_WATCH_FAIL=TARGET_CYCLE_NOT_FOUND",flush=True)
        raise SystemExit(3)

    state=(str(target_row['status']),str(target_row['error']),str(target_row['finished_at']),
           int(next_row['id']) if next_row else 0,
           str(next_row['status']) if next_row else 'NONE')
    if state != last:
        print("RADAR_V6199_AUTOPILOT_CYCLE_67_STATUS="+str(target_row['status']),flush=True)
        print("RADAR_V6199_AUTOPILOT_CYCLE_67_ERROR="+(str(target_row['error']) or 'NONE'),flush=True)
        print("RADAR_V6199_AUTOPILOT_CYCLE_67_FINISHED_AT="+(str(target_row['finished_at']) or 'NONE'),flush=True)
        if next_row:
            print("RADAR_V6199_AUTOPILOT_NEXT_CYCLE_ID="+str(next_row['id']),flush=True)
            print("RADAR_V6199_AUTOPILOT_NEXT_QUERY="+str(next_row['query']),flush=True)
            print("RADAR_V6199_AUTOPILOT_NEXT_STATUS="+str(next_row['status']),flush=True)
        last=state

    status=str(target_row['status']).upper()
    finished=str(target_row['finished_at'] or '')
    if status in ('SUCCESS','FAILED') and finished:
        target_terminal=True
        print("RADAR_V6199_AUTOPILOT_CYCLE_67_TERMINAL=PASS",flush=True)
        if status=='FAILED':
            err=str(target_row['error'] or '')
            if not err:
                print("RADAR_V6199_AUTOPILOT_WATCH_FAIL=FAILED_WITHOUT_ERROR",flush=True)
                raise SystemExit(4)
            if err.endswith('_CYCLE_TERMINALIZATION_FAILED'):
                print("RADAR_V6199_AUTOPILOT_WATCH_FAIL=TERMINALIZATION_RETRIES_EXHAUSTED",flush=True)
                raise SystemExit(5)

    if next_row:
        next_seen=True
        print("RADAR_V6199_AUTOPILOT_CONTINUATION_OBSERVED=PASS",flush=True)

    if target_terminal and next_seen:
        print("RADAR_V6199_AUTOPILOT_PRODUCTION_WATCH=PASS",flush=True)
        raise SystemExit(0)

    # If the cycle terminalizes successfully but no next cycle appears yet,
    # allow Autopilot time for confirmation/Seed Scout/history reuse.
    if target_terminal:
        time.sleep(5)
    else:
        time.sleep(5)

print("RADAR_V6199_AUTOPILOT_WATCH_FAIL=TIMEOUT",flush=True)
raise SystemExit(6)
PY

echo "LASTWAR_CONTACT=NO"
echo "RADAR_PRODUCTION_MUTATION=NO"
echo "COLLECTOR_DATA_MUTATION=NO"
echo "RADAR_V6199_AUTOPILOT_WATCH=PASS"
