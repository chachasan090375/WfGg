#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

TRIGGER="${1:-MANUAL}"
QUERY="${2:-}"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/collector-v1/collector"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
BASE="$TMP/incremental-base.sh"
ENRICH="$TMP/profile-enrich.sh"

curl -fsSL "$RAW/incremental-update-v2-from-termux.sh" -o "$BASE"
curl -fsSL "$RAW/profile-enrich-direct-from-termux.sh" -o "$ENRICH"
chmod 0755 "$BASE" "$ENRICH"

python3 - "$BASE" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
# Keep JSON headers intact across the Termux -> ssh -> VPS command boundary.
s=s.replace("-H 'Content-Type: application/json'", "-H Content-Type:application/json")
s=s.replace("-H Content-Type: application/json", "-H Content-Type:application/json")
marker='''if [[ "$FAIL" -eq 0 ]]; then\n  FIN_BODY="$(printf '{\\"cycleId\\":%s,\\"status\\":\\"SUCCESS\\"}' "$CYCLE_ID")"\n'''
insert='''if [[ "$FAIL" -eq 0 ]]; then\n  echo 'COLLECTOR_ENRICHMENT_START=YES'\n  ENRICH_OUT="$(bash "$WFGG_PROFILE_ENRICH_SCRIPT" "$CYCLE_ID" "$QUERY" 2>&1 || true)"\n  printf '%s\\n' "$ENRICH_OUT" | grep -E '^(COLLECTOR_DIRECT_CANDIDATES|COLLECTOR_DIRECT_RETURNED|COLLECTOR_DIRECT_CACHE_ACCEPTED|COLLECTOR_DIRECT_FAILED_BATCHES|COLLECTOR_DIRECT_BATCH_RC)=' || true\n  CAND="$(printf '%s\\n' "$ENRICH_OUT" | sed -n 's/^COLLECTOR_DIRECT_CANDIDATES=//p' | tail -n1)"\n  RET="$(printf '%s\\n' "$ENRICH_OUT" | sed -n 's/^COLLECTOR_DIRECT_RETURNED=//p' | tail -n1)"\n  FB="$(printf '%s\\n' "$ENRICH_OUT" | sed -n 's/^COLLECTOR_DIRECT_FAILED_BATCHES=//p' | tail -n1)"\n  [[ -n "$CAND" ]] || CAND=0\n  [[ -n "$RET" ]] || RET=0\n  [[ -n "$FB" ]] || FB=0\n  if [[ "$FB" -eq 0 && "$RET" -eq "$CAND" ]]; then\n    echo 'COLLECTOR_ENRICHMENT_STATUS=SUCCESS'\n  else\n    echo 'COLLECTOR_ENRICHMENT_STATUS=PARTIAL'\n  fi\nfi\n\nif [[ "$FAIL" -eq 0 ]]; then\n  FIN_BODY="$(printf '{\\"cycleId\\":%s,\\"status\\":\\"SUCCESS\\"}' "$CYCLE_ID")"\n'''
if marker not in s:
    raise SystemExit('PATCH_MARKER_NOT_FOUND')
s=s.replace(marker,insert,1)
p.write_text(s)
PY

export WFGG_PROFILE_ENRICH_SCRIPT="$ENRICH"
bash "$BASE" "$TRIGGER" "$QUERY"
