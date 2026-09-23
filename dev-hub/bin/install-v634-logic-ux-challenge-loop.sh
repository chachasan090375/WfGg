#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V634_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v634.XXXXXX)"
PREVIOUS=""
STAGE="bootstrap"
PROJECT="v634-logic-ux-pilot-$STAMP"

stage(){ STAGE="$1"; echo "CHACHA_DEV_V634_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V634_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err; do
      [ -s "$f" ] && { echo "=== $(basename "$f") ==="; cat "$f"; }
    done
    if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V634_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || {
  echo "CHACHA_DEV_V634_INSTALL=BLOCKED reason=root_required"; exit 2;
}
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "CHACHA_DEV_V634_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2;
}
for cmd in curl tar python3 git ln readlink grep find; do
  command -v "$cmd" >/dev/null || {
    echo "CHACHA_DEV_V634_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2;
  }
done
[ -f "$CURRENT/dev-hub/bin/project-assurance-relay.py" ] || {
  echo "CHACHA_DEV_V634_INSTALL=BLOCKED reason=v633_baseline_missing"; exit 2;
}
[ -L "$CURRENT" ] && PREVIOUS="$(readlink -f "$CURRENT" || true)"
echo "CHACHA_DEV_V634_V633_BASELINE=PASS"

stage fetch-pinned-release
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tgz"
tar -xzf "$WORK/repo.tgz" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || {
  echo "CHACHA_DEV_V634_INSTALL=BLOCKED reason=archive_invalid"; exit 2;
}
for required in \
  dev-hub/bin/logic-search-engine.py \
  dev-hub/bin/ux-planning-engine.py \
  dev-hub/bin/multi-agent-compromise-engine.py \
  dev-hub/bin/compromise-release-gate.py \
  dev-hub/bin/autonomous-project-orchestrator.py \
  dev-hub/bin/architecture-decision-council.py \
  dev-hub/bin/guardian-client.py \
  dev-hub/config/logic-search.v1.json \
  dev-hub/config/ux-planning.v1.json \
  dev-hub/config/decision-challenge.v1.json \
  dev-hub/config/compromise-release-gate.v1.json \
  dev-hub/config/lifecycle.v1.json \
  dev-hub/config/quality-gates.v1.json \
  dev-hub/config/guardian-runtime-policy.v1.json \
  dev-hub/tests/test_v634_logic_ux_compromise_release.py; do
  [ -f "$SRC/$required" ] || {
    echo "CHACHA_DEV_V634_INSTALL=BLOCKED reason=missing:$required"; exit 2;
  }
done

stage static-validation
mkdir -p "$RELEASE" /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"
PYTHONPATH="$RELEASE/dev-hub/bin" python3 -m py_compile \
  "$RELEASE/dev-hub/bin/logic-search-engine.py" \
  "$RELEASE/dev-hub/bin/ux-planning-engine.py" \
  "$RELEASE/dev-hub/bin/multi-agent-compromise-engine.py" \
  "$RELEASE/dev-hub/bin/compromise-release-gate.py" \
  "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py" \
  "$RELEASE/dev-hub/bin/architecture-decision-council.py"
for f in \
  "$RELEASE/dev-hub/config/logic-search.v1.json" \
  "$RELEASE/dev-hub/config/ux-planning.v1.json" \
  "$RELEASE/dev-hub/config/decision-challenge.v1.json" \
  "$RELEASE/dev-hub/config/compromise-release-gate.v1.json" \
  "$RELEASE/dev-hub/config/lifecycle.v1.json" \
  "$RELEASE/dev-hub/config/quality-gates.v1.json"; do
  python3 -m json.tool "$f" >/dev/null
done
echo "CHACHA_DEV_V634_STATIC=PASS"

stage semantic-pilot
(
  cd "$RELEASE"
  PYTHONPATH=dev-hub/bin python3 dev-hub/tests/test_v634_logic_ux_compromise_release.py
) >"$WORK/semantic.out" 2>&1
for marker in \
  CHACHA_DEV_V634_LOGICIAN_ADAPTIVE_SEARCH=PASS \
  CHACHA_DEV_V634_ERGONOMIST_UX_CHALLENGE=PASS \
  CHACHA_DEV_V634_CENTRAL_COMPROMISE_FIRST=PASS \
  CHACHA_DEV_V634_AGENT_REVISION_ONLY_AFTER_FAILED_COMPROMISE=PASS \
  CHACHA_DEV_V634_ARCHITECTURE_COUNCIL_CONSUMES_COMPROMISE=PASS \
  CHACHA_DEV_V634_SEVEN_AGENT_RELEASE_GATE=PASS \
  CHACHA_DEV_V634_RELEASE_LIFECYCLE_ENFORCEMENT=PASS \
  CHACHA_DEV_V634_MISSING_AGENT_FAIL_CLOSED=PASS; do
  grep -Fq "$marker" "$WORK/semantic.out"
done
echo "CHACHA_DEV_V634_SEMANTIC_PILOT=PASS"

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"

stage external-guardian-governance
GUARDIAN_URL="$(python3 -c 'import json;print(json.load(open("'"$CURRENT"'/dev-hub/config/guardian-runtime-policy.v1.json"))["external_url"])')"
curl -fsS "$GUARDIAN_URL/healthz" -o "$WORK/guardian-health.json"
python3 - "$WORK/guardian-health.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x.get("logic_ux_compromise_evidence_required") is True,x
assert x.get("compromise_release_gate_external_enforcement_ready") is True,x
print("CHACHA_DEV_V634_REAL_EXTERNAL_GUARDIAN_COMPROMISE_GOVERNANCE=PASS")
PY

stage external-guardian-compromise-proof
python3 - "$WORK/guardian-negative.json" "$PROJECT" <<'PY'
import json,sys,uuid
keys=["technology_watch_pre","technology_watch_final","central_memory_assimilation","component_confidence",
      "central_memory_recall","reuse_memory","architecture_memory","architecture_portfolio","branch_foundry",
      "agent_foundry","capability_foundry","constraint_policy"]
x={
 "schema":"chacha.dev/governance-action/v1","event_id":"gov-"+uuid.uuid4().hex,
 "action_id":"v634-negative","phase":"POST_ACTION","actor":"central-orchestrator",
 "subject_role":"architecture-decision-council","action":"FINAL_ARCHITECTURE_DECISION",
 "task_kind":"architecture-decision-council","permission":"plan","project_id":sys.argv[2],
 "run_id":None,"adapters":[],"evidence":{k:True for k in keys},
 "context":{"resource_class":"light","human_approval_required":False,
            "storage_preflight_required":False,"deadline_seconds":180,"external_spend_eur":0}
}
json.dump(x,open(sys.argv[1],"w"),indent=2)
PY
set +e
python3 "$CURRENT/dev-hub/bin/guardian-client.py" \
  --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" \
  check --event "$WORK/guardian-negative.json" >"$WORK/guardian-negative.out" 2>"$WORK/guardian-negative.err"
neg_rc=$?
set -e
test "$neg_rc" -eq 20
python3 - "$WORK/guardian-negative.out" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x.get("verdict")=="BLOCK",x
assert any("ARCHITECTURE_COUNCIL_EVIDENCE_MISSING:logic_ux_compromise" in str(r) for r in x.get("reason_codes") or []),x
PY
python3 - "$WORK/guardian-negative.json" "$WORK/guardian-positive.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));x["event_id"]=x["event_id"]+"-positive";x["action_id"]="v634-positive"
x["evidence"]["logic_ux_compromise"]=True
json.dump(x,open(sys.argv[2],"w"),indent=2)
PY
python3 "$CURRENT/dev-hub/bin/guardian-client.py" \
  --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json" \
  check --event "$WORK/guardian-positive.json" >"$WORK/guardian-positive.out"
python3 - "$WORK/guardian-positive.out" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));assert x.get("verdict")=="PASS",x
print("CHACHA_DEV_V634_REAL_EXTERNAL_GUARDIAN_COMPROMISE_GATE=PASS")
PY

stage release-lifecycle-proof
python3 - "$CURRENT/dev-hub/config/lifecycle.v1.json" "$CURRENT/dev-hub/config/quality-gates.v1.json" <<'PY'
import json,sys
l,q=[json.load(open(p)) for p in sys.argv[1:]]
t=l["transitions"]["PREVIEW->RELEASE"]
assert "compromise-release-receipt" in t["required_artifacts"],t
assert "compromise-release" in t["required_gates"],t
assert l["release_policy"]["compromise_release_receipt_required"] is True,l
assert q["gates"]["compromise-release"]["default_blocking"] is True,q
print("CHACHA_DEV_V634_REAL_RELEASE_LIFECYCLE_GATE=PASS")
PY

stage build-real-search-dossier
mkdir -p "$WORK/search-repo"
(
  cd "$WORK/search-repo"
  git init -q
  git config user.email v634@local.invalid
  git config user.name V634
  printf 'VALUE=1\n' > alpha_component.py
  printf 'VALUE=1\n' > bravo_component.py
  printf 'VALUE=1\n' > charlie_component.py
  printf 'VALUE=1\n' > delta_component.py
  git add .
  git commit -qm seed
)
cat >"$WORK/intent.json" <<JSON
{"name":"V6.34 real pilot","text":"Build a simple mobile user interface with a reliable backend"}
JSON
cat >"$WORK/contract.json" <<JSON
{
  "schema":"chacha.dev/functional-contract/v1",
  "contract_id":"contract-$PROJECT",
  "functional_intent":"Build a simple mobile user interface with a reliable backend",
  "audiences":["user"],
  "styles":["simple","direct"]
}
JSON
python3 - "$WORK/preplan.json" <<'PY'
import json,sys
names=["alpha","bravo","charlie","delta","echo","foxtrot"]
x={"packages":[
  {"id":"pkg-"+str(i),"domain":name,"kind":"frontend-web","capabilities":[name]}
  for i,name in enumerate(names)
],"primary_domains":names}
json.dump(x,open(sys.argv[1],"w"),indent=2)
PY
cat >"$WORK/memory.json" <<JSON
{"current_best_reuse_candidates":[{"kind":"branch","branch_id":"pilot-branch","version":"1"}]}
JSON

python3 "$CURRENT/dev-hub/bin/logic-search-engine.py" \
  --repo-root "$WORK/search-repo" \
  --intent "$WORK/intent.json" \
  --contract "$WORK/contract.json" \
  --preplan "$WORK/preplan.json" \
  --memory-brief "$WORK/memory.json" \
  --policy "$CURRENT/dev-hub/config/logic-search.v1.json" \
  --output "$WORK/logic.json" >"$WORK/logic.out"

python3 "$CURRENT/dev-hub/bin/ux-planning-engine.py" \
  --intent "$WORK/intent.json" \
  --contract "$WORK/contract.json" \
  --preplan "$WORK/preplan.json" \
  --policy "$CURRENT/dev-hub/config/ux-planning.v1.json" \
  --output "$WORK/ux.json" >"$WORK/ux.out"

python3 - "$WORK/logic.json" "$WORK/ux.json" <<'PY'
import json,sys
l=json.load(open(sys.argv[1]));u=json.load(open(sys.argv[2]))
assert 1 <= int(l["evaluated_path_count"]) <= 50000,l
assert int(l["virtual_space_size"]) >= int(l["evaluated_path_count"]),l
assert l["central_brain_response_required"] is True,l
assert u["user_facing"] is True,u
assert u["challenge_status"]=="REPLAN_REQUIRED",u
assert u["central_brain_response_required"] is True,u
assert u["ux_contract"]["curator_handoff_required"] is True,u
print("CHACHA_DEV_V634_REAL_LOGICIAN_SEARCH=PASS")
print("CHACHA_DEV_V634_REAL_ERGONOMIST_CHALLENGE=PASS")
PY

stage central-compromise-first
python3 "$CURRENT/dev-hub/bin/multi-agent-compromise-engine.py" \
  --policy "$CURRENT/dev-hub/config/decision-challenge.v1.json" \
  --logic-report "$WORK/logic.json" \
  --ux-report "$WORK/ux.json" \
  --output "$WORK/compromise.json" >"$WORK/compromise.out"
python3 - "$WORK/compromise.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["central_compromise_search_attempted"] is True,x
assert x["central_compromise_found"] is True,x
assert x["revision_requests"]==[],x
assert x["continuation_allowed"] is True,x
assert x["revision_request_only_after_failed_compromise"] is True,x
print("CHACHA_DEV_V634_REAL_CENTRAL_COMPROMISE_FIRST=PASS")
print("CHACHA_DEV_V634_REAL_UNNECESSARY_REVISION_REQUEST=NO")
PY

stage failed-compromise-targeted-revision
cat >"$WORK/guardian-position.json" <<JSON
{
  "agent":"guardian","status":"RECONSIDER","proposal":{"kind":"functional"},
  "hard_constraints":[{"key":"pilot.storage.mode","value":"local"}],
  "evidence_refs":["pilot:guardian"]
}
JSON
cat >"$WORK/bastion-position.json" <<JSON
{
  "agent":"bastion","status":"RECONSIDER","proposal":{"kind":"security"},
  "hard_constraints":[{"key":"pilot.storage.mode","value":"isolated"}],
  "evidence_refs":["pilot:bastion"]
}
JSON
python3 "$CURRENT/dev-hub/bin/multi-agent-compromise-engine.py" \
  --policy "$CURRENT/dev-hub/config/decision-challenge.v1.json" \
  --logic-report "$WORK/logic.json" \
  --ux-report "$WORK/ux.json" \
  --agent-report "$WORK/guardian-position.json" \
  --agent-report "$WORK/bastion-position.json" \
  --output "$WORK/conflict.json" >"$WORK/conflict.out"
python3 - "$WORK/conflict.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["central_compromise_search_attempted"] is True,x
assert x["central_compromise_found"] is False,x
assert x["continuation_allowed"] is False,x
assert len(x["revision_requests"])==1,x
r=x["revision_requests"][0]
assert set(r["target_agents"])=={"guardian","bastion"},r
assert r["reason"]=="NO_ADMISSIBLE_CENTRAL_COMPROMISE",r
assert r["must_preserve_prior_evidence"] is True,r
print("CHACHA_DEV_V634_REAL_REVISION_ONLY_AFTER_FAILED_COMPROMISE=PASS")
print("CHACHA_DEV_V634_REAL_TARGETED_REVISION_REQUEST=PASS")
PY

stage release-gate-fail-closed
DIGEST="$(python3 -c 'import json;print(json.load(open("'"$WORK"'/compromise.json"))["dossier_digest"])')"
cat >"$WORK/council.json" <<JSON
{
  "schema":"chacha.dev/architecture-decision-council/v1",
  "dispatch_allowed":true,
  "logic_ux_compromise":{"required":true,"valid":true,"dossier_digest":"$DIGEST"}
}
JSON
cat >"$WORK/implementation.json" <<JSON
{
  "schema":"chacha.dev/implementation-verification/v1",
  "project_id":"$PROJECT",
  "revision":"$REV",
  "compromise_digest":"$DIGEST",
  "status":"PASS",
  "non_dominated_compromise_verified":true,
  "hard_constraints_satisfied":true,
  "architecture_changed":false
}
JSON
for agent in logician ergonomist guardian sentinel; do
  cat >"$WORK/review-$agent.json" <<JSON
{
  "schema":"chacha.dev/compromise-agent-review/v1",
  "agent":"$agent",
  "project_id":"$PROJECT",
  "revision":"$REV",
  "compromise_digest":"$DIGEST",
  "verdict":"ACCEPT",
  "hard_objections":[],
  "soft_objections":[],
  "evidence_refs":["pilot:$agent"],
  "implementation_verified":true,
  "source_authority":"PILOT"
}
JSON
done
set +e
python3 "$CURRENT/dev-hub/bin/compromise-release-gate.py" \
  --project-id "$PROJECT" --revision "$REV" \
  --policy "$CURRENT/dev-hub/config/compromise-release-gate.v1.json" \
  --compromise "$WORK/compromise.json" \
  --council "$WORK/council.json" \
  --implementation-verification "$WORK/implementation.json" \
  --agent-review "$WORK/review-logician.json" \
  --agent-review "$WORK/review-ergonomist.json" \
  --agent-review "$WORK/review-guardian.json" \
  --agent-review "$WORK/review-sentinel.json" \
  --output "$WORK/release.json" >"$WORK/release.out" 2>"$WORK/release.err"
gate_rc=$?
set -e
test "$gate_rc" -eq 20
python3 - "$WORK/release.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["release_allowed"] is False,x
missing=[r for r in x["reason_codes"] if r.startswith("REQUIRED_AGENT_REVIEW_MISSING:")]
assert missing, x
assert "curator" in missing[0] and "bastion" in missing[0] and "intendant" in missing[0],missing
assert x["unanimous_preferences_required"] is False,x
assert x["majority_vote_used"] is False,x
print("CHACHA_DEV_V634_REAL_RELEASE_GATE_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V634_REAL_CENTRAL_SPECIALISTS_PENDING=curator,bastion,intendant")
PY

cat >"/opt/chacha-dev/evidence/v634-logic-ux-challenge-$STAMP.json" <<JSON
{
  "schema":"chacha.dev/v634-logic-ux-challenge-evidence/v1",
  "revision":"$REV",
  "project_id":"$PROJECT",
  "observed_at":"$STAMP",
  "logician_real_search":"PASS",
  "ergonomist_real_challenge":"PASS",
  "central_compromise_first":"PASS",
  "targeted_revision_only_after_failed_compromise":"PASS",
  "external_guardian_compromise_governance":"PASS",
  "external_guardian_compromise_gate":"PASS",
  "release_lifecycle_gate":"PASS",
  "release_gate_fail_closed_pending_central_specialists":"PASS",
  "pending_specialists":["curator","bastion","intendant"],
  "direct_mutation":false,
  "automatic_external_spend_eur":0
}
JSON

echo "CHACHA_DEV_V634_LOGICIAN=ACTIVE"
echo "CHACHA_DEV_V634_ERGONOMIST=ACTIVE"
echo "CHACHA_DEV_V634_CENTRAL_COMPROMISE_FIRST=YES"
echo "CHACHA_DEV_V634_AGENT_REVISION_ONLY_AFTER_FAILED_COMPROMISE=YES"
echo "CHACHA_DEV_V634_CURRENT_PLAN_INCUMBENCY_PRIVILEGE=NO"
echo "CHACHA_DEV_V634_EXTERNAL_GUARDIAN_COMPROMISE_GOVERNANCE=PASS"
echo "CHACHA_DEV_V634_EXTERNAL_GUARDIAN_COMPROMISE_GATE=PASS"
echo "CHACHA_DEV_V634_RELEASE_LIFECYCLE_GATE=PASS"
echo "CHACHA_DEV_V634_RELEASE_GATE=FAIL_CLOSED_UNTIL_7_REAL_REVIEWS"
echo "CHACHA_DEV_V634_PENDING_CENTRAL_SPECIALISTS=curator,bastion,intendant"
echo "CHACHA_DEV_V634_DIRECT_MUTATION=NO"
echo "CHACHA_DEV_V634_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V634_INSTALL=PASS"

trap - EXIT
cleanup
