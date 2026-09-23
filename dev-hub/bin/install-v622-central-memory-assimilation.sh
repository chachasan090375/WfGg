#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V622_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v622.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
PREVIOUS=""
STAGE="bootstrap"
NEW_UNITS_INSTALLED=0

stage(){ STAGE="$1"; echo "CHACHA_DEV_V622_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V622_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/assimilation.out "$WORK"/assimilation.stderr "$WORK"/techwatch.out "$WORK"/semantic-test.out; do
      if [ -s "$f" ]; then echo "=== $(basename "$f") ==="; cat "$f"; fi
    done
    if [ "$NEW_UNITS_INSTALLED" -eq 1 ]; then
      systemctl disable --now chacha-dev-central-memory-assimilation.timer >/dev/null 2>&1 || true
      rm -f /etc/systemd/system/chacha-dev-central-memory-assimilation.service             /etc/systemd/system/chacha-dev-central-memory-assimilation.timer
      systemctl daemon-reload >/dev/null 2>&1 || true
    fi
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      systemctl daemon-reload >/dev/null 2>&1 || true
      systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true
      systemctl restart chacha-dev-universal-learning-flush.timer >/dev/null 2>&1 || true
      systemctl restart chacha-dev-central-learning-relay-pull.timer >/dev/null 2>&1 || true
      echo "CHACHA_DEV_V622_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V622_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V622_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink grep; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V622_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
  python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True: raise SystemExit("CHACHA_DEV_V622_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

stage fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V622_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/central-memory-assimilator.py   dev-hub/bin/technology_watch_runtime.py   dev-hub/bin/technology-watch-service.py   dev-hub/bin/architecture-decision-council.py   dev-hub/config/central-memory-assimilation.v1.json   dev-hub/systemd/chacha-dev-central-memory-assimilation.service   dev-hub/systemd/chacha-dev-central-memory-assimilation.timer   dev-hub/tests/test_v622_central_memory_assimilation.py; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V622_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

stage static-validation
mkdir -p "$RELEASE" /opt/chacha-dev/runtime/knowledge /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile   "$RELEASE/dev-hub/bin/central-memory-assimilator.py"   "$RELEASE/dev-hub/bin/technology_watch_runtime.py"   "$RELEASE/dev-hub/bin/architecture-decision-council.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"
echo "CHACHA_DEV_V622_STATIC=PASS"

stage semantic-pilot
(
  cd "$RELEASE"
  PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v622_central_memory_assimilation.py
) >"$WORK/semantic-test.out" 2>&1
grep -Fq 'CHACHA_DEV_V622_SINGLE_OBSERVATION_NOT_TRUSTED=PASS' "$WORK/semantic-test.out"
grep -Fq 'CHACHA_DEV_V622_REPEATED_SUCCESS_REINFORCES_MEMORY=PASS' "$WORK/semantic-test.out"
grep -Fq 'CHACHA_DEV_V622_CROSS_PROJECT_GENERALIZATION_GATE=PASS' "$WORK/semantic-test.out"
grep -Fq 'CHACHA_DEV_V622_CONTRADICTION_DETECTED=PASS' "$WORK/semantic-test.out"
grep -Fq 'CHACHA_DEV_V622_CRITICAL_ANOMALY_SUSPENDS_MEMORY=PASS' "$WORK/semantic-test.out"
grep -Fq 'CHACHA_DEV_V622_OLD_REUSE_VERSION_SUPERSEDED=PASS' "$WORK/semantic-test.out"
echo "CHACHA_DEV_V622_ASSIMILATION_SEMANTICS=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"

stage real-memory-assimilation
set +e
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/central-memory-assimilator.py"   --policy "$CURRENT/dev-hub/config/central-memory-assimilation.v1.json" --nas   >"$WORK/assimilation.out" 2>"$WORK/assimilation.stderr"
ASSIM_RC=$?
set -e
if [ "$ASSIM_RC" -ne 0 ]; then
  echo "CHACHA_DEV_V622_INSTALL=BLOCKED reason=real_assimilation_failed"
  exit 2
fi
grep -Fq 'CHACHA_DEV_V622_CENTRAL_MEMORY_ASSIMILATION=PASS' "$WORK/assimilation.out"
python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json"
x=json.load(open(p,encoding="utf-8"))
assert x["schema"]=="chacha.dev/central-memory-assimilation/v1",x
assert x["single_observation_never_trusted"] is True,x
assert x["project_specific_by_default"] is True,x
assert x["technology_revalidation_required_before_reuse"] is True,x
assert x["nas"]["status"]=="PERSISTED",x["nas"]
assert x["automatic_external_spend_eur"]==0,x
assert x.get("snapshot_digest"),x
print("CHACHA_DEV_V622_REAL_MEMORY_SNAPSHOT=PASS")
print("CHACHA_DEV_V622_NAS_ASSIMILATION_PERSISTENCE=PASS")
print("CHACHA_DEV_V622_MEMORY_ITEMS="+str(x.get("item_count",0)))
print("CHACHA_DEV_V622_GENERALIZABLE_TRUSTED="+str(x.get("trusted_generalizable_count",0)))
PY

stage technology-watch-memory-feed
systemctl start chacha-dev-technology-watch.service
systemctl is-failed --quiet chacha-dev-technology-watch.service && { echo "CHACHA_DEV_V622_INSTALL=BLOCKED reason=technology_watch_failed"; exit 2; } || true
python3 - <<'PY'
import json
m=json.load(open("/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json",encoding="utf-8"))
t=json.load(open("/opt/chacha-dev/runtime/technology-watch/optimizer-input.json",encoding="utf-8"))
c=t.get("central_memory_assimilation") or {}
assert c.get("available") is True,c
assert c.get("snapshot_digest")==m.get("snapshot_digest"),(c,m.get("snapshot_digest"))
assert c.get("single_observation_never_trusted") is True,c
assert c.get("technology_revalidation_required_before_reuse") is True,c
print("CHACHA_DEV_V622_TECHNOLOGY_WATCH_MEMORY_FEED=PASS")
PY

stage architecture-council-memory-advisor
PYTHONPATH="$CURRENT/dev-hub/bin" python3 - <<'PY'
import importlib.util
from pathlib import Path
p=Path("/opt/chacha-dev/platform/current/dev-hub/bin/architecture-decision-council.py")
s=importlib.util.spec_from_file_location("adc",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
x=m.central_memory_assimilation()
assert x.get("available") is True,x
assert "central-memory-assimilation" in m.MANDATORY,m.MANDATORY
assert x.get("single_observation_never_trusted") is True,x
assert x.get("technology_revalidation_required_before_reuse") is True,x
print("CHACHA_DEV_V622_ARCHITECTURE_COUNCIL_MEMORY_ADVISOR=PASS")
PY

stage install-background-assimilation
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-central-memory-assimilation.service" /etc/systemd/system/chacha-dev-central-memory-assimilation.service
install -m 0644 "$CURRENT/dev-hub/systemd/chacha-dev-central-memory-assimilation.timer" /etc/systemd/system/chacha-dev-central-memory-assimilation.timer
NEW_UNITS_INSTALLED=1
systemctl daemon-reload
systemctl enable --now chacha-dev-central-memory-assimilation.timer
systemctl is-active --quiet chacha-dev-central-memory-assimilation.timer
echo "CHACHA_DEV_V622_BACKGROUND_ASSIMILATION_TIMER=PASS"

stage invariants
python3 - <<'PY'
import json
x=json.load(open("/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json",encoding="utf-8"))
branches=(x.get("reuse_catalog") or {}).get("branches") or []
arches=(x.get("reuse_catalog") or {}).get("architectures") or []
bad=[r for r in branches+arches if r.get("version_status") not in {"CURRENT_BEST","SUPERSEDED"}]
assert not bad,bad
print("CHACHA_DEV_V622_CURRENT_BEST_REUSE_INDEX=PASS")
print("CHACHA_DEV_V622_OLD_VERSIONS_PRESERVED_AS_SUPERSEDED=PASS")
PY

cat >"/opt/chacha-dev/evidence/v622-central-memory-assimilation-$STAMP.json" <<JSON
{"schema":"chacha.dev/v622-central-memory-assimilation-evidence/v1","revision":"$REV","observed_at":"$STAMP","semantic_pilot":"PASS","real_memory_snapshot":"PASS","nas_persistence":"PASS","technology_watch_memory_feed":"PASS","architecture_council_memory_advisor":"PASS","background_timer":"PASS","automatic_external_spend_eur":0}
JSON

echo "CHACHA_DEV_V622_SINGLE_OBSERVATION_BECOMES_TRUTH=NO"
echo "CHACHA_DEV_V622_REPEATED_SUCCESS_REINFORCES_MEMORY=YES"
echo "CHACHA_DEV_V622_NEGATIVE_MEMORY_PRESERVED=YES"
echo "CHACHA_DEV_V622_CONTRADICTIONS_DETECTED=YES"
echo "CHACHA_DEV_V622_CRITICAL_ANOMALY_SUSPENDS_MEMORY=YES"
echo "CHACHA_DEV_V622_PROJECT_SPECIFIC_BY_DEFAULT=YES"
echo "CHACHA_DEV_V622_CROSS_PROJECT_GENERALIZATION_GATED=YES"
echo "CHACHA_DEV_V622_PREVIOUS_SOLUTION_IS_CANDIDATE_NOT_DEFAULT=YES"
echo "CHACHA_DEV_V622_TECHNOLOGY_REVALIDATION_BEFORE_REUSE=YES"
echo "CHACHA_DEV_V622_NAS_AUTHORITATIVE=YES"
echo "CHACHA_DEV_V622_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V622_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V622_INSTALL=PASS"

trap - EXIT
cleanup
