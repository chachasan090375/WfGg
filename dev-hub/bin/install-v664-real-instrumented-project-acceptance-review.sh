#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V664_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V664_SOURCE_ROOT:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SHORTREV="${REV:0:12}"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v664.XXXXXX)"
RUN_ROOT="/opt/chacha-dev/runtime/golden-path-runs/$STAMP-v664-real-instrumented-$SHORTREV"
PLAN_DIR="$RUN_ROOT/planning"
INTENT="$RUN_ROOT/intent.json"
COUNCIL_DIR="/opt/chacha-dev/runtime/agent-evolution/candidate-reviews/acceptance-engineer/v664/$REV"
PREVIOUS=""
ACTIVATED=0
COUNCIL_WRITTEN=0
PROJECT_WRITTEN=0
FLEET_TIMER="chacha-dev-agent-fleet-observatory.timer"
BUS_TIMER="chacha-dev-agent-observation-bus-health.timer"
FLEET_ACTIVE=0
BUS_ACTIVE=0
STAGE="bootstrap"

stage(){ STAGE="$1";echo "CHACHA_DEV_V664_STAGE=$STAGE"; }
restore_timers(){
  [ "$FLEET_ACTIVE" -eq 1 ] && systemctl start "$FLEET_TIMER" >/dev/null 2>&1 || true
  [ "$BUS_ACTIVE" -eq 1 ] && systemctl start "$BUS_TIMER" >/dev/null 2>&1 || true
}
backup_runtime(){
  mkdir -p "$WORK/backup"
  for p in     /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json     /opt/chacha-dev/runtime/agent-evolution/profiles/index.json     /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json     /opt/chacha-dev/runtime/guardian/coverage-latest.json; do
    if [ -f "$p" ]; then
      mkdir -p "$WORK/backup$(dirname "$p")"
      cp -a "$p" "$WORK/backup$p"
    fi
  done
  [ -d /opt/chacha-dev/runtime/agent-observation ] && cp -a /opt/chacha-dev/runtime/agent-observation "$WORK/backup-agent-observation"
  [ -d /opt/chacha-dev/runtime/learning ] && cp -a /opt/chacha-dev/runtime/learning "$WORK/backup-learning"
}
restore_runtime(){
  for p in     /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json     /opt/chacha-dev/runtime/agent-evolution/profiles/index.json     /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json     /opt/chacha-dev/runtime/guardian/coverage-latest.json; do
    if [ -f "$WORK/backup$p" ]; then
      mkdir -p "$(dirname "$p")"
      cp -a "$WORK/backup$p" "$p"
    fi
  done
  if [ -d "$WORK/backup-agent-observation" ]; then
    rm -rf /opt/chacha-dev/runtime/agent-observation
    cp -a "$WORK/backup-agent-observation" /opt/chacha-dev/runtime/agent-observation
  fi
  if [ -d "$WORK/backup-learning" ]; then
    rm -rf /opt/chacha-dev/runtime/learning
    cp -a "$WORK/backup-learning" /opt/chacha-dev/runtime/learning
  fi
  [ "$COUNCIL_WRITTEN" -eq 1 ] && rm -rf "$COUNCIL_DIR" || true
  [ "$PROJECT_WRITTEN" -eq 1 ] && rm -rf "$RUN_ROOT" || true
}
cleanup(){ restore_timers;rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V664_FAILURE_STAGE=$STAGE"
    for f in "$WORK"/*.out "$WORK"/*.err "$WORK"/*.json; do
      [ -s "$f" ] || continue
      echo "=== $(basename "$f") ==="
      tail -320 "$f" || true
    done
    restore_runtime
    if [ "$ACTIVATED" -eq 1 ] && [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
      ln -sfn "$PREVIOUS" "$CURRENT"
      echo "CHACHA_DEV_V664_ROLLBACK=PASS"
    fi
    rm -rf "$RELEASE" 2>/dev/null || true
    echo "CHACHA_DEV_V664_OBSERVATION_BUS_ROLLBACK=PASS"
    echo "CHACHA_DEV_V664_LEARNING_STATE_ROLLBACK=PASS"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V664_INSTALL=BLOCKED reason=root_required";exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V664_INSTALL=BLOCKED reason=pinned_revision_required";exit 2; }
[ -L "$CURRENT" ] || { echo "CHACHA_DEV_V664_INSTALL=BLOCKED reason=current_release_symlink_missing";exit 2; }
PREVIOUS="$(readlink -f "$CURRENT")"

stage v663-real-baseline
python3 - "$PREVIOUS" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]);rev=(root/".revision").read_text().strip()
assert rev=="a3803180a64f1ea95d94466b7b10529a7a4af92f",rev
src=(root/"dev-hub/bin/autonomous-project-orchestrator.py").read_text()
assert '"version":"6.63.0"' in src
ev=sorted(pathlib.Path("/opt/chacha-dev/evidence").glob("v663-runtime-surface-instrumentation-readiness-*.json"))
assert ev,"V663_REAL_EVIDENCE_MISSING"
x=json.loads(ev[-1].read_text())
assert x.get("revision")==rev,x
assert (x.get("radar") or {}).get("central_brain_role") is False,x
assert (x.get("radar") or {}).get("sre_release_execution_credit") is False,x
assert (x.get("acceptance_readiness") or {}).get("production_activation") is False,x
assert (x.get("acceptance_readiness") or {}).get("promotion") is False,x
print("CHACHA_DEV_V664_V663_REAL_BASELINE=PASS")
PY
ACCEPT_BEFORE="$(sha256sum "$PREVIOUS/dev-hub/bin/acceptance-engine.py" | awk '{print $1}')"

stage source-preflight
if [ -n "$SOURCE_ROOT" ]; then
  SRC="$(readlink -f "$SOURCE_ROOT")"
  [ -d "$SRC/dev-hub" ] || exit 2
else
  curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
  mkdir -p "$WORK/src"
  tar -xzf "$WORK/repo.tar.gz" -C "$WORK/src" --strip-components=1
  SRC="$WORK/src"
fi
for p in   dev-hub/bin/install-v664-real-instrumented-project-acceptance-review.sh   dev-hub/bin/autonomous-project-orchestrator.py   dev-hub/bin/contract-registry.py   dev-hub/bin/integration-architecture-review.py   dev-hub/bin/architecture-council-agent-candidate-review-v664.py   dev-hub/bin/agent_fleet_observatory.py   dev-hub/bin/agent_evolution_profile.py   dev-hub/bin/component_evolution_governance.py   dev-hub/bin/guardian-coverage-heartbeat.py   dev-hub/bin/technology-watch-service.py   dev-hub/bin/acceptance-engine.py   dev-hub/config/architecture-decision-council.v1.json   dev-hub/config/agent-fleet-observatory.v1.json   dev-hub/projects/wfgg-radar/project-agent-registry.v1.json   dev-hub/tests/test_v664_real_instrumented_project_acceptance_council.py; do
  [ -f "$SRC/$p" ] || { echo "CHACHA_DEV_V664_INSTALL=BLOCKED reason=missing:$p";exit 2; }
done

stage candidate-release
mkdir -p "$RELEASE"
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
printf '%s\n' "$REV" >"$RELEASE/.revision"
bash -n "$RELEASE/dev-hub/bin/install-v664-real-instrumented-project-acceptance-review.sh"
python3 -m py_compile   "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"   "$RELEASE/dev-hub/bin/contract-registry.py"   "$RELEASE/dev-hub/bin/integration-architecture-review.py"   "$RELEASE/dev-hub/bin/architecture-council-agent-candidate-review-v664.py"   "$RELEASE/dev-hub/tests/test_v664_real_instrumented_project_acceptance_council.py"
python3 -m json.tool "$RELEASE/dev-hub/config/architecture-decision-council.v1.json" >/dev/null
grep -Fq '"version":"6.64.0"' "$RELEASE/dev-hub/bin/autonomous-project-orchestrator.py"
[ "$ACCEPT_BEFORE" = "$(sha256sum "$RELEASE/dev-hub/bin/acceptance-engine.py" | awk '{print $1}')" ] || { echo "ACCEPTANCE_PRODUCTION_ENTRYPOINT_CHANGED";exit 46; }
(cd "$RELEASE";PYTHONPATH="$RELEASE/dev-hub/bin" python3 dev-hub/tests/test_v664_real_instrumented_project_acceptance_council.py) >"$WORK/v664.out" 2>"$WORK/v664.err"
for m in   CHACHA_DEV_V664_PROJECT_BOUND_STAGE_EVIDENCE=PASS   CHACHA_DEV_V664_CONTRACT_INTEGRATOR_OBSERVATION=PASS   CHACHA_DEV_V664_INTEGRATION_ARCHITECT_OBSERVATION=PASS   CHACHA_DEV_V664_ACTIVITY_ACCURACY_INFERENCE=NO   CHACHA_DEV_V664_ACCEPTANCE_ARCHITECTURE_COUNCIL_REVIEW=PASS   CHACHA_DEV_V664_HUMAN_PROMOTION_APPROVAL_PRESENT=NO   CHACHA_DEV_V664_ACCEPTANCE_PRODUCTION_ACTIVATION=NO   CHACHA_DEV_V664_ACCEPTANCE_PROMOTION=NO   CHACHA_DEV_V664_RADAR_PROJECT_ONLY=PASS; do
  grep -Fq "$m" "$WORK/v664.out"
done
echo "CHACHA_DEV_V664_STATIC_AND_SEMANTIC=PASS"

stage exact-sha-external-assurance
python3 - "$REV" "$WORK/github-runs.json" <<'PY'
import json,sys,urllib.parse,urllib.request
rev,out=sys.argv[1:3]
q=urllib.parse.urlencode({"head_sha":rev,"per_page":50})
req=urllib.request.Request("https://api.github.com/repos/chachasan090375/WfGg/actions/runs?"+q,
 headers={"User-Agent":"ChaCha-DEV-V664-Installer/1.0","Accept":"application/vnd.github+json"})
with urllib.request.urlopen(req,timeout=20) as r:x=json.loads(r.read().decode())
open(out,"w").write(json.dumps(x))
need={
 "ChaCha DEV V6.64 real instrumented project and Acceptance Council gate qualification",
 "ChaCha DEV Sentinel technical assurance"
}
rows=x.get("workflow_runs") or []
for name in need:
    assert any(w.get("name")==name and w.get("head_sha")==rev and w.get("status")=="completed" and w.get("conclusion")=="success" for w in rows),name
print("CHACHA_DEV_V664_EXACT_SHA_GITHUB_ASSURANCE=PASS")
PY

stage acceptance-council-review
READINESS="/opt/chacha-dev/runtime/agent-evolution/candidate-readiness/acceptance-engineer/v663/a3803180a64f1ea95d94466b7b10529a7a4af92f/readiness.json"
[ -f "$READINESS" ] || { echo "V663_READINESS_MISSING";exit 47; }
PYTHONPATH="$RELEASE/dev-hub/bin" python3 "$RELEASE/dev-hub/bin/architecture-council-agent-candidate-review-v664.py"   --repo-root "$RELEASE" --runtime-root /opt/chacha-dev/runtime   --readiness "$READINESS" --revision "$REV"   --github-runs-json "$WORK/github-runs.json"   --output "$WORK/acceptance-council-review.json" >"$WORK/council.out" 2>"$WORK/council.err"
grep -Fq 'CHACHA_DEV_V664_ACCEPTANCE_ARCHITECTURE_COUNCIL_REVIEW=PASS' "$WORK/council.out"
grep -Fq 'CHACHA_DEV_V664_HUMAN_PROMOTION_APPROVAL_PRESENT=NO' "$WORK/council.out"
grep -Fq 'CHACHA_DEV_V664_ACCEPTANCE_PRODUCTION_ACTIVATION=NO' "$WORK/council.out"
grep -Fq 'CHACHA_DEV_V664_ACCEPTANCE_PROMOTION=NO' "$WORK/council.out"
python3 - "$WORK/acceptance-council-review.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["decision"]=="TECHNICALLY_ADMISSIBLE_AWAIT_EXPLICIT_HUMAN_PROMOTION_APPROVAL",x
assert x["architecture_council_review_complete"] is True,x
assert x["architecture_council_technical_admissibility"] is True,x
assert x["architecture_council_promotion_approval_present"] is False,x
assert x["human_explicit_promotion_approval_present"] is False,x
assert x["production_activation_allowed"] is False and x["promotion_allowed"] is False,x
print("CHACHA_DEV_V664_COUNCIL_GATE_PREFLIGHT=PASS")
PY

stage runtime-backup-and-bus-baseline
if systemctl is-active --quiet "$FLEET_TIMER"; then FLEET_ACTIVE=1;systemctl stop "$FLEET_TIMER";fi
if systemctl is-active --quiet "$BUS_TIMER"; then BUS_ACTIVE=1;systemctl stop "$BUS_TIMER";fi
backup_runtime
BENCH_BEFORE="$(python3 - <<'PY'
import hashlib,pathlib
root=pathlib.Path("/opt/chacha-dev/runtime/agent-evolution/benchmark-evidence");h=hashlib.sha256()
for p in sorted(root.glob("**/*.json")):
    h.update(str(p.relative_to(root)).encode());h.update(p.read_bytes())
print(h.hexdigest())
PY
)"
python3 - "$WORK/bus-before.json" <<'PY'
import hashlib,json,sqlite3,sys
p="/opt/chacha-dev/runtime/agent-observation/observations.db";con=sqlite3.connect(p)
rows=con.execute("select seq,event_id,event_digest from observations order by seq").fetchall()
h=hashlib.sha256()
for row in rows:h.update(("|".join(map(str,row))+"\n").encode())
x={"count":len(rows),"max_seq":max([r[0] for r in rows],default=0),"prefix_digest":h.hexdigest()}
open(sys.argv[1],"w").write(json.dumps(x))
print("CHACHA_DEV_V664_BUS_BASELINE="+json.dumps(x,sort_keys=True))
PY

stage activate-release
ln -sfn "$RELEASE" "$CURRENT"
ACTIVATED=1
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
[ "$ACCEPT_BEFORE" = "$(sha256sum "$CURRENT/dev-hub/bin/acceptance-engine.py" | awk '{print $1}')" ] || { echo "ACCEPTANCE_PRODUCTION_ENTRYPOINT_CHANGED";exit 48; }
echo "CHACHA_DEV_V664_RELEASE_ACTIVATED=PASS"
echo "CHACHA_DEV_V664_ACCEPTANCE_PRODUCTION_ENTRYPOINT_CHANGED=NO"

stage real-instrumented-project
mkdir -p "$PLAN_DIR"
PROJECT_WRITTEN=1
cat >"$INTENT" <<'JSON'
{
  "name": "V664 Real Instrumented Runtime Evidence App",
  "text": "Crée une petite application frontend accessible et responsive avec un bouton qui change un état visible. Le projet doit inclure tests unitaires et e2e, sécurité, documentation, build reproductible, preview local, release contrôlée, rollback et recovery. Aucun coût externe automatique.",
  "golden_path_profile": "static-interaction-v1",
  "constraints": {
    "requires_authentication": false,
    "requires_database": false,
    "requires_external_api": false
  }
}
JSON
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/autonomous-project-orchestrator.py"   --repo-root "$CURRENT" --intent "$INTENT" --output-dir "$PLAN_DIR" >"$WORK/project.out" 2>"$WORK/project.err"
grep -Fq 'CHACHA_AUTONOMOUS_PROJECT_BOOTSTRAP=PASS' "$WORK/project.out"
python3 - "$PLAN_DIR/bootstrap-result.json" "$REV" <<'PY'
import json,sys,pathlib
x=json.load(open(sys.argv[1]));rev=sys.argv[2]
assert x["version"]=="6.64.0",x
assert x["contract_reconciliation_compatible"] is True,x
assert x["integration_architecture_ready"] is True,x
assert float(x.get("external_spend_eur") or 0)==0,x
for k in ("contract_reconciliation","integration_architecture_review"):
    p=pathlib.Path(x[k]);assert p.is_file(),(k,p)
print("CHACHA_DEV_V664_REAL_PROJECT_BOOTSTRAP=PASS")
print("PROJECT_ID="+str(x["project_id"]))
PY
PROJECT_ID="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["project_id"])' "$PLAN_DIR/bootstrap-result.json")"
echo "CHACHA_DEV_V664_REAL_PROJECT_ID=$PROJECT_ID"

stage canonical-observation-proof
python3 - "$WORK/bus-before.json" "$PROJECT_ID" "$REV" "$PLAN_DIR" "$WORK/bus-proof.json" <<'PY'
import hashlib,json,pathlib,sqlite3,sys
before=json.load(open(sys.argv[1]));project,rev,plan,out=sys.argv[2:6]
con=sqlite3.connect("/opt/chacha-dev/runtime/agent-observation/observations.db")
prefix=con.execute("select seq,event_id,event_digest from observations where seq<=? order by seq",(before["max_seq"],)).fetchall()
h=hashlib.sha256()
for row in prefix:h.update(("|".join(map(str,row))+"\n").encode())
assert h.hexdigest()==before["prefix_digest"],(h.hexdigest(),before)
rows=con.execute("select seq,event_id,subject_role,event_type,verification,event_digest,payload_json from observations where seq>? order by seq",(before["max_seq"],)).fetchall()
assert rows,"NO_NEW_OBSERVATION_EVENTS"
wanted={"contract-integrator":["contract-reconciliation"],"integration-architect":["integration-design","api-contract-review"]}
matched={}
for seq,eid,role,etype,verification,event_digest,payload_json in rows:
    if role not in wanted:continue
    p=json.loads(payload_json)
    if p.get("event_type")!="STAGE_EXECUTION_OBSERVED":continue
    if p.get("source_id")!="central-orchestrator" or p.get("source_surface")!="autonomous-project-orchestrator":continue
    if p.get("project_id")!=project or p.get("revision")!=rev:continue
    if p.get("verification")!="OBSERVED" or p.get("outcome")!="OK":continue
    if sorted(p.get("capabilities") or [])!=sorted(wanted[role]):continue
    refs=[str(x) for x in p.get("evidence_refs") or [] if "#sha256:" in str(x)]
    valid=[]
    for ref in refs:
        raw,digest=ref.rsplit("#sha256:",1);path=pathlib.Path(raw)
        if not path.is_file():continue
        got=hashlib.sha256(path.read_bytes()).hexdigest()
        if got==digest and str(path).startswith(str(pathlib.Path(plan).resolve())):valid.append(ref)
    if valid:matched[role]={"seq":seq,"event_id":eid,"event_digest":event_digest,"evidence_refs":valid,"capabilities":p.get("capabilities")}
assert set(matched)==set(wanted),(matched,[(r[0],r[2]) for r in rows])
proof={"before":before,"new_event_count":len(rows),"project_id":project,"revision":rev,"matched":matched,
       "historical_prefix_unchanged":True,"append_only":True}
open(out,"w").write(json.dumps(proof,indent=2)+"\n")
print("CHACHA_DEV_V664_CANONICAL_OBSERVATION_PROOF=PASS")
print("CHACHA_DEV_V664_HISTORICAL_BUS_REWRITE=NO")
print("CHACHA_DEV_V664_CONTRACT_INTEGRATOR_REAL_EVENT=PASS")
print("CHACHA_DEV_V664_INTEGRATION_ARCHITECT_REAL_EVENT=PASS")
PY

stage fleet-rebuild
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_fleet_observatory.py"   --repo-root "$CURRENT" --runtime-root /opt/chacha-dev/runtime   --policy "$CURRENT/dev-hub/config/agent-fleet-observatory.v1.json"   --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"   --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"   --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"   --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"   --output /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json >"$WORK/fleet.out" 2>"$WORK/fleet.err"
python3 - /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));by={a["agent_id"]:a for a in x["agents"]}
for aid,coverage in (("contract-integrator",33.3),("integration-architect",66.7)):
    a=by[aid];sc=a["scorecard"];d=sc["dimension_evidence"]
    assert sc["production_measurement_coverage_pct"]==30.0,(aid,sc)
    assert sc["benchmark_measurement_coverage_pct"]==50.0,(aid,sc)
    assert sc["production_weighted_maturity_pct"]==36.0,(aid,sc)
    assert sc["evidence_maturity_label"]=="MIXED_EVIDENCE",(aid,sc)
    assert set(sc["production_measured_dimensions"])=={"coverage","efficiency","robustness"},(aid,sc)
    assert d["coverage"]["value"]==coverage,(aid,d["coverage"])
    assert d["robustness"]["value"]==100.0 and d["efficiency"]["value"]==100.0,(aid,d)
    assert d["accuracy"].get("evidence_scope")=="BENCHMARK_ONLY",(aid,d["accuracy"])
for aid in ("knowledge-compiler-agent","uncertainty-resolution-agent"):
    a=by[aid];assert a["scorecard"]["production_measurement_coverage_pct"]==0.0,(aid,a["scorecard"])
    assert a["scorecard"]["evidence_maturity_label"]=="BENCHMARK_HEAVY",(aid,a["scorecard"])
r=by["technology-radar-agent"];assert r["scope"]=="PROJECT",r
assert r["scorecard"]["production_measurement_coverage_pct"]==20.0,r["scorecard"]
assert r["scorecard"]["evidence_maturity_label"]=="BENCHMARK_HEAVY",r["scorecard"]
labels={}
for a in x["agents"]:labels[a["scorecard"]["evidence_maturity_label"]]=labels.get(a["scorecard"]["evidence_maturity_label"],0)+1
assert labels=={"BENCHMARK_HEAVY":9,"MIXED_EVIDENCE":26},labels
assert sum(1 for a in x["agents"] if a["scorecard"].get("recommendation")=="MEASURE_FIRST")==0
print("CHACHA_DEV_V664_REAL_FLEET_EVIDENCE=PASS")
print("CHACHA_DEV_V664_MIXED_EVIDENCE=26")
print("CHACHA_DEV_V664_BENCHMARK_HEAVY=9")
print("CHACHA_DEV_V664_ACTIVITY_ACCURACY_INFERENCE=NO")
PY

stage materialize-council-review
rm -rf "$COUNCIL_DIR";mkdir -p "$COUNCIL_DIR"
cp "$WORK/acceptance-council-review.json" "$COUNCIL_DIR/architecture-council-review.json"
COUNCIL_WRITTEN=1
echo "CHACHA_DEV_V664_COUNCIL_REVIEW_MATERIALIZED=PASS"

stage benchmark-immutability
BENCH_AFTER="$(python3 - <<'PY'
import hashlib,pathlib
root=pathlib.Path("/opt/chacha-dev/runtime/agent-evolution/benchmark-evidence");h=hashlib.sha256()
for p in sorted(root.glob("**/*.json")):
    h.update(str(p.relative_to(root)).encode());h.update(p.read_bytes())
print(h.hexdigest())
PY
)"
[ "$BENCH_BEFORE" = "$BENCH_AFTER" ] || { echo "BENCHMARK_EVIDENCE_MUTATED"; exit 49; }
echo "CHACHA_DEV_V664_BENCHMARK_EVIDENCE_MUTATION=NO"

stage universal-regeneration
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/agent_evolution_profile.py"   --fleet /opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json   --routing "$CURRENT/dev-hub/config/agent-routing.v1.json"   --seven "$CURRENT/dev-hub/config/seven-agent-final-compromise.v1.json"   --project-registry "$CURRENT/dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"   --adapter-config "$CURRENT/dev-hub/config/agent-benchmark-adapters.v1.json"   --evolution-policy "$CURRENT/dev-hub/config/agent-evolution.v1.json"   --profile-policy "$CURRENT/dev-hub/config/agent-evolution-profile.v1.json"   --output-root /opt/chacha-dev/runtime/agent-evolution/profiles >"$WORK/profiles.out"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_AGENT_PROFILES=PASS' "$WORK/profiles.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/component_evolution_governance.py"   --agent-profiles /opt/chacha-dev/runtime/agent-evolution/profiles/index.json   --core-watch "$CURRENT/dev-hub/config/technology-core-watch.v1.json"   --provider-adapters "$CURRENT/dev-hub/config/provider-adapters.v1.json"   --mcp-catalog "$CURRENT/dev-hub/config/mcp-provider-catalog.v1.json"   --embedded-assurance "$CURRENT/dev-hub/config/project-embedded-assurance.v1.json"   --policy "$CURRENT/dev-hub/config/universal-evolution-governance.v1.json"   --output /opt/chacha-dev/runtime/agent-evolution/component-governance-latest.json >"$WORK/components.out"
grep -Fq 'CHACHA_DEV_V654_UNIVERSAL_COMPONENT_GOVERNANCE=PASS' "$WORK/components.out"

stage guardian-watch-post
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/guardian.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/guardian.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/guardian.out"
PYTHONPATH="$CURRENT/dev-hub/bin" python3 "$CURRENT/dev-hub/bin/technology-watch-service.py" --repo-root "$CURRENT" status >"$WORK/watch.out"
grep -Fq 'CHACHA_TECHNOLOGY_WATCH_STATUS=FRESH' "$WORK/watch.out"
restore_timers
systemctl is-active --quiet "$FLEET_TIMER"
systemctl is-active --quiet chacha-dev-agent-observation-bus-health.timer
systemctl is-active --quiet chacha-remote-desktop-commander.service

stage evidence
mkdir -p /opt/chacha-dev/evidence
python3 - "/opt/chacha-dev/evidence/v664-real-instrumented-project-acceptance-review-$STAMP.json" "$REV" "$STAMP" "$PROJECT_ID" "$RUN_ROOT" "$WORK/bus-proof.json" "$COUNCIL_DIR/architecture-council-review.json" <<'PY'
import json,sys
out,rev,stamp,project,run_root,bus_path,council_path=sys.argv[1:8]
f=json.load(open("/opt/chacha-dev/runtime/agent-evolution/fleet-observatory-latest.json"));by={a["agent_id"]:a for a in f["agents"]}
bus=json.load(open(bus_path));council=json.load(open(council_path))
result={
 "schema":"chacha.dev/v664-real-instrumented-project-acceptance-review-evidence/v1",
 "revision":rev,"observed_at":stamp,"project_id":project,"run_root":run_root,
 "real_project_bootstrap":True,"canonical_observation_bus_append_only":True,
 "historical_observation_bus_rewrite":False,"observation_bus_proof":bus,
 "contract_integrator":{
   "production":by["contract-integrator"]["scorecard"]["production_measurement_coverage_pct"],
   "benchmark":by["contract-integrator"]["scorecard"]["benchmark_measurement_coverage_pct"],
   "weighted":by["contract-integrator"]["scorecard"]["production_weighted_maturity_pct"],
   "label":by["contract-integrator"]["scorecard"]["evidence_maturity_label"],
   "production_dimensions":by["contract-integrator"]["scorecard"]["production_measured_dimensions"]
 },
 "integration_architect":{
   "production":by["integration-architect"]["scorecard"]["production_measurement_coverage_pct"],
   "benchmark":by["integration-architect"]["scorecard"]["benchmark_measurement_coverage_pct"],
   "weighted":by["integration-architect"]["scorecard"]["production_weighted_maturity_pct"],
   "label":by["integration-architect"]["scorecard"]["evidence_maturity_label"],
   "production_dimensions":by["integration-architect"]["scorecard"]["production_measured_dimensions"]
 },
 "knowledge_compiler_production_promotion":False,
 "uncertainty_resolver_production_promotion":False,
 "technology_radar_project_only":True,
 "acceptance_council_review":{
   "decision":council["decision"],"technical_admissibility":council["architecture_council_technical_admissibility"],
   "human_explicit_promotion_approval_present":False,
   "production_activation":False,"promotion":False,"incumbent_control_group":True
 },
 "mixed_evidence_count":sum(1 for a in f["agents"] if a["scorecard"].get("evidence_maturity_label")=="MIXED_EVIDENCE"),
 "benchmark_heavy_count":sum(1 for a in f["agents"] if a["scorecard"].get("evidence_maturity_label")=="BENCHMARK_HEAVY"),
 "active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
 "architecture_council_final_authority":True,"automatic_external_spend_eur":0
}
open(out,"w").write(json.dumps(result,indent=2)+"\n")
PY

echo "CHACHA_DEV_V664_REAL_INSTRUMENTED_PROJECT=PASS"
echo "CHACHA_DEV_V664_CONTRACT_INTEGRATOR_REAL_EVENT=PASS"
echo "CHACHA_DEV_V664_INTEGRATION_ARCHITECT_REAL_EVENT=PASS"
echo "CHACHA_DEV_V664_CANONICAL_OBSERVATION_BUS_APPEND_ONLY=YES"
echo "CHACHA_DEV_V664_HISTORICAL_BUS_REWRITE=NO"
echo "CHACHA_DEV_V664_BENCHMARK_EVIDENCE_MUTATION=NO"
echo "CHACHA_DEV_V664_ACTIVITY_ACCURACY_INFERENCE=NO"
echo "CHACHA_DEV_V664_ACCEPTANCE_ARCHITECTURE_COUNCIL_REVIEW=PASS"
echo "CHACHA_DEV_V664_ACCEPTANCE_TECHNICAL_ADMISSIBILITY=PASS"
echo "CHACHA_DEV_V664_HUMAN_PROMOTION_APPROVAL_PRESENT=NO"
echo "CHACHA_DEV_V664_ACCEPTANCE_PRODUCTION_ACTIVATION=NO"
echo "CHACHA_DEV_V664_ACCEPTANCE_PROMOTION=NO"
echo "CHACHA_DEV_V664_RADAR_PROJECT_ONLY=YES"
echo "CHACHA_DEV_V664_SELF_MUTATION=NO"
echo "CHACHA_DEV_V664_SELF_PROMOTION=NO"
echo "CHACHA_DEV_V664_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES"
echo "CHACHA_DEV_V664_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V664_INSTALL=PASS"

trap - EXIT
cleanup
