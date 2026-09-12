#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
WINDOW="${PLAYER_ORACLE_SENTINEL_WINDOW:-20 minutes ago}"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERROR=%s\n' "$*" >&2; exit 1; }
for cmd in ssh grep sed awk tail; do command -v "$cmd" >/dev/null 2>&1 || die "${cmd}_MISSING"; done

SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say 'PLAYER_ORACLE_SENTINEL_SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die VPS_UNREACHABLE
  say 'PLAYER_ORACLE_SENTINEL_SSH_ROUTE=PUBLIC_IPV4'
fi

say '=== WfGg Sentinel · Player Oracle route ==='
LOG="$(ssh "${SSH_OPTS[@]}" -T "$REMOTE" "journalctl -u wfgg-radar-connector.service --since '$WINDOW' --no-pager -o cat 2>/dev/null | grep 'PLAYER_ORACLE_' | tail -n 180" </dev/null || true)"
[[ -n "$LOG" ]] || die NO_SENTINEL_TRACE_RUN_A_RADAR_SEARCH_FIRST

LAST_JOB="$(printf '%s\n' "$LOG" | grep 'PLAYER_ORACLE_SENTINEL' | sed -n 's/.*jobId=\([^ ]*\).*/\1/p' | tail -n 1)"
[[ -n "$LAST_JOB" ]] || die SENTINEL_JOB_ID_NOT_FOUND
TRACE="$(printf '%s\n' "$LOG" | grep "jobId=$LAST_JOB")"
PROTO="$(printf '%s\n' "$LOG" | grep 'PLAYER_ORACLE_PROTOCOL_SENTINEL' | tail -n 12 || true)"

say "PLAYER_ORACLE_SENTINEL_JOB=$LAST_JOB"
say '--- ROUTE TRACE ---'
printf '%s\n' "$TRACE"
if [[ -n "$PROTO" ]]; then
  say '--- PROTOCOL TRACE ---'
  printf '%s\n' "$PROTO"
fi
say '--- VERDICT ---'

has(){ printf '%s\n' "$TRACE" | grep -q "$1"; }
line(){ printf '%s\n' "$TRACE" | grep -n "$1" | head -n1 | cut -d: -f1; }

if has 'stage=START' && has 'priority=1'; then
  say 'SENTINEL_P1_UID_INDEX=OK'
else
  say 'SENTINEL_P1_UID_INDEX=BAD'
fi

if has 'stage=UID_RESOLVED'; then
  say 'SENTINEL_UID_RESOLVED=YES'
  if has 'stage=DIRECT_PROFILE_START' && has 'priority=2'; then
    say 'SENTINEL_P2_DIRECT_PROFILE_ATTEMPTED=YES'
  else
    say 'SENTINEL_P2_DIRECT_PROFILE_ATTEMPTED=NO'
  fi
else
  say 'SENTINEL_UID_RESOLVED=NO'
fi

if has 'stage=DIRECT_PROFILE_SUCCESS'; then
  say 'SENTINEL_P2_DIRECT_PROFILE_SUCCESS=YES'
elif has 'stage=DIRECT_PROFILE_FAILED'; then
  say 'SENTINEL_P2_DIRECT_PROFILE_SUCCESS=NO'
else
  say 'SENTINEL_P2_DIRECT_PROFILE_SUCCESS=UNKNOWN'
fi

if has 'stage=BROAD_SCAN_SELECTED'; then
  say 'SENTINEL_P3_BROADSCAN_USED=YES'
  B="$(line 'stage=BROAD_SCAN_SELECTED')"
  if has 'stage=DIRECT_PROFILE_START'; then
    D="$(line 'stage=DIRECT_PROFILE_START')"
    if [[ "$D" -lt "$B" ]]; then
      say 'SENTINEL_PRIORITY_ORDER=OK'
    else
      say 'SENTINEL_PRIORITY_ORDER=BAD'
    fi
  elif has 'stage=UID_INDEX_MISS' || has 'stage=UID_MISSING'; then
    say 'SENTINEL_PRIORITY_ORDER=OK'
  else
    say 'SENTINEL_PRIORITY_ORDER=BAD'
  fi
else
  say 'SENTINEL_P3_BROADSCAN_USED=NO'
  if has 'stage=DIRECT_PROFILE_SUCCESS' && has 'stage=DONE'; then
    say 'SENTINEL_PRIORITY_ORDER=OK'
  else
    say 'SENTINEL_PRIORITY_ORDER=INCOMPLETE'
  fi
fi

if has 'stage=DIRECT_PROFILE_SUCCESS'; then
  say 'SENTINEL_ROUTE=UID_INDEX->DIRECT_PROFILE->DONE'
elif has 'stage=DIRECT_PROFILE_FAILED' && has 'stage=BROAD_SCAN_SELECTED'; then
  say 'SENTINEL_ROUTE=UID_INDEX->DIRECT_PROFILE_FAILED->BROAD_SCAN_V4'
elif has 'stage=UID_INDEX_MISS' && has 'stage=BROAD_SCAN_SELECTED'; then
  say 'SENTINEL_ROUTE=UID_INDEX_MISS->BROAD_SCAN_V4'
elif has 'stage=UID_MISSING' && has 'stage=BROAD_SCAN_SELECTED'; then
  say 'SENTINEL_ROUTE=UID_MISSING->BROAD_SCAN_V4'
else
  say 'SENTINEL_ROUTE=UNCLASSIFIED'
fi

if [[ -n "$PROTO" ]]; then
  CODE="$(printf '%s\n' "$PROTO" | sed -n 's/.*nativeCode=\([^ ]*\).*/\1/p' | tail -n 1)"
  [[ -n "$CODE" ]] && say "SENTINEL_NATIVE_PROFILE_CODE=$CODE"
fi

say 'PLAYER_ORACLE_SENTINEL_INSPECTION=OK'
