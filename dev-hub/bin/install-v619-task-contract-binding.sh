#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V619_REV:-}"
BASE="/opt/chacha-dev/platform"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v619.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
PRIVATE_KEY="/opt/chacha-dev/runtime/secrets/central-learning-key.pem"
GUARDIAN_URL="https://chacha-dev-guardian.chachasan090375.workers.dev"
PREVIOUS=""

cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ] && [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
    ln -sfn "$PREVIOUS" "$CURRENT"
    systemctl daemon-reload >/dev/null 2>&1 || true
    systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true
    systemctl restart chacha-dev-guardian-alert-pull.timer >/dev/null 2>&1 || true
    systemctl restart chacha-dev-guardian-coverage-heartbeat.timer >/dev/null 2>&1 || true
    echo "CHACHA_DEV_V619_ROLLBACK=PASS"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V619_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V619_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 ln systemctl readlink openssl base64 grep chmod; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V619_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
[ -s "$PRIVATE_KEY" ] || { echo "CHACHA_DEV_V619_INSTALL=BLOCKED reason=central_private_key_missing"; exit 2; }

if [ -f /opt/chacha-dev/runtime/control/emergency-stop.json ]; then
  python3 - <<'PY'
import json
p="/opt/chacha-dev/runtime/control/emergency-stop.json"
try:x=json.load(open(p))
except Exception:x={}
if x.get("active") is True: raise SystemExit("CHACHA_DEV_V619_INSTALL=BLOCKED reason=emergency_stop_active")
PY
fi
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT" || true)"; fi

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V619_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

for required in   dev-hub/bin/guardian-client.py   dev-hub/bin/task-contract-binder.py   dev-hub/bin/execution-scheduler.py   dev-hub/bin/run-controller.py   dev-hub/bin/agent_role_contracts.py   dev-hub/bin/dynamic_component_contracts.py   dev-hub/config/guardian-role-contracts.v1.json   dev-hub/config/guardian-runtime-policy.v1.json   dev-hub/config/guardian-coverage-manifest.v1.json   dev-hub/config/run-controller.v1.json   dev-hub/config/worker-learning-central-identity.v1.json; do
  [ -f "$SRC/$required" ] || { echo "CHACHA_DEV_V619_INSTALL=BLOCKED reason=missing:$required"; exit 2; }
done

mkdir -p "$RELEASE" /opt/chacha-dev/runtime/guardian/alerts /opt/chacha-dev/runtime/control /opt/chacha-dev/evidence
cp -a "$SRC/dev-hub" "$RELEASE/dev-hub"
python3 -m py_compile   "$RELEASE/dev-hub/bin/guardian-client.py"   "$RELEASE/dev-hub/bin/task-contract-binder.py"   "$RELEASE/dev-hub/bin/execution-scheduler.py"   "$RELEASE/dev-hub/bin/run-controller.py"   "$RELEASE/dev-hub/bin/agent_role_contracts.py"   "$RELEASE/dev-hub/bin/dynamic_component_contracts.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"

ACTUAL_PUB="$(openssl pkey -in "$PRIVATE_KEY" -pubout -outform DER | base64 -w0)"
EXPECTED_PUB="$(python3 - "$RELEASE/dev-hub/config/worker-learning-central-identity.v1.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding="utf-8"))["public_key_spki_b64"])
PY
)"
[ "$ACTUAL_PUB" = "$EXPECTED_PUB" ] || { echo "CHACHA_DEV_V619_INSTALL=BLOCKED reason=central_key_mismatch"; exit 2; }
echo "CHACHA_DEV_V619_CENTRAL_KEY_MATCH=PASS"

curl -fsS "$GUARDIAN_URL/healthz" -o "$WORK/guardian-health.json"
grep -Fq '"external_governance_plane":true' "$WORK/guardian-health.json"
grep -Fq '"task_contract_binding_protocol":true' "$WORK/guardian-health.json"
grep -Fq '"task_contract_identity_lease":true' "$WORK/guardian-health.json"
echo "CHACHA_DEV_V619_EXTERNAL_GUARDIAN_HEALTH=PASS"
echo "CHACHA_DEV_V619_TASK_CONTRACT_PROTOCOL=PASS"

ln -sfn "$RELEASE" "$CURRENT"

# Build and register one dynamic agent contract and one dynamic branch contract.
PYTHONPATH="$CURRENT/dev-hub/bin" python3 - "$WORK" <<'PY'
import json,sys
from pathlib import Path
import agent_role_contracts as arc
import dynamic_component_contracts as dcc
w=Path(sys.argv[1])
agent=arc.build_contract(
  agent_id="v619-runtime-pilot:graphics:ephemeral-agent",
  project_id="v619-runtime-pilot",domain="graphics",package_id="domain:graphics",
  capabilities=["image-generation"],tools=[],scope="project")
row={
  "package_id":"domain:graphics","branch_id":"v619-runtime-pilot:graphics:primary",
  "domain":"graphics","decision":"MATERIALIZE_EPHEMERAL_BRANCH","runtime_required":True,
  "orchestrator_strategy":"SHARED","architecture":{}
}
branch=dcc.build_branch_contract(
  row=row,project_id="v619-runtime-pilot",capabilities=["layout-design"])
(w/"agent-contract.json").write_text(json.dumps(agent,indent=2)+"\n")
(w/"component-contract.json").write_text(json.dumps(branch,indent=2)+"\n")
(w/"agent-contracts.json").write_text(json.dumps({"contracts":[agent]},indent=2)+"\n")
(w/"component-contracts.json").write_text(json.dumps({"contracts":[branch]},indent=2)+"\n")
PY

python3 "$CURRENT/dev-hub/bin/guardian-client.py"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   register-contract --contract "$WORK/agent-contract.json" >"$WORK/register-agent.out"
grep -Eq '"status"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/register-agent.out"

python3 "$CURRENT/dev-hub/bin/guardian-client.py"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   register-component-contract --contract "$WORK/component-contract.json" >"$WORK/register-component.out"
grep -Eq '"status"[[:space:]]*:[[:space:]]*"PASS"' "$WORK/register-component.out"
echo "CHACHA_DEV_V619_DYNAMIC_SUBJECT_CONTRACTS_REGISTERED=PASS"

cat >"$WORK/task-graph.json" <<'JSON'
{
  "schema":"chacha.dev/task-graph/v1",
  "project":"v619-runtime-pilot",
  "transition":"DESIGN->IMPLEMENTATION",
  "tasks":[
    {
      "id":"task:agent-image",
      "kind":"artifact",
      "description":"V6.19 agent-bound task",
      "owner_role":"v619-runtime-pilot:graphics:ephemeral-agent",
      "capabilities":["image-generation"],
      "permission":"read",
      "depends_on":[],
      "outputs":[],
      "verification":{"mode":"machine","self_certification_allowed":false}
    },
    {
      "id":"task:branch-layout",
      "kind":"artifact",
      "description":"V6.19 branch-bound task",
      "owner_role":"v619-runtime-pilot:graphics:primary",
      "capabilities":["layout-design"],
      "permission":"read",
      "depends_on":[],
      "outputs":[],
      "verification":{"mode":"machine","self_certification_allowed":false}
    }
  ]
}
JSON

cat >"$WORK/registry.json" <<'JSON'
{
  "schema":"chacha.dev/capability-registry/v1",
  "capabilities":{
    "image-generation":{"providers":[{"id":"v619-local-pilot","status":"ADOPT"}]},
    "layout-design":{"providers":[{"id":"v619-local-pilot","status":"ADOPT"}]}
  }
}
JSON
cat >"$WORK/health.json" <<'JSON'
{
  "schema":"chacha.dev/provider-health-snapshot/v1",
  "providers":{"v619-local-pilot":{"state":"HEALTHY"}}
}
JSON
cat >"$WORK/scheduler-policy.json" <<'JSON'
{
  "schema":"chacha.dev/execution-scheduler/v1",
  "provider_selection":{"allow_unknown":false,"allow_degraded_for_non_production":false,"allow_degraded_for_production":false},
  "failover":{"approval_required_for_permissions":[]},
  "resource_classes":{"light":{"storage_preflight":false}},
  "concurrency":{"serialize_permissions":[],"max_parallel_read_tasks":8,"allow_read_tasks_during_write":false}
}
JSON

python3 "$CURRENT/dev-hub/bin/execution-scheduler.py"   --graph "$WORK/task-graph.json"   --registry "$WORK/registry.json"   --health "$WORK/health.json"   --policy "$WORK/scheduler-policy.json"   --agent-contracts "$WORK/agent-contracts.json"   --component-contracts "$WORK/component-contracts.json"   --role-contracts "$CURRENT/dev-hub/config/guardian-role-contracts.v1.json"   --bound-graph-output "$WORK/task-graph-bound.json"   --require-guardian-binding   --output "$WORK/execution-plan.json" >"$WORK/scheduler.out"

grep -Fq 'TASK_GUARDIAN_BINDING=PASS' "$WORK/scheduler.out"
python3 - "$WORK/task-graph-bound.json" "$WORK/execution-plan.json" <<'PY'
import json,sys
g=json.load(open(sys.argv[1]));p=json.load(open(sys.argv[2]))
assert g["guardian_binding"]["all_tasks_bound"] is True,g
assert g["guardian_binding"]["dynamic_task_count"]==2,g
assert g["guardian_binding"]["blocked_task_count"]==0,g
assert p["guardian_binding"]["all_tasks_bound"] is True,p
tasks=[t for w in p["waves"] for t in w["tasks"]]
assert len(tasks)==2,tasks
assert all((t.get("guardian_binding") or {}).get("binding_digest") for t in tasks),tasks
PY
echo "CHACHA_DEV_V619_GRAPH_TO_PLAN_BINDING=PASS"

cat >"$WORK/pilot-adapter.py" <<'PY'
#!/usr/bin/env python3
import json,sys,datetime
e=json.load(sys.stdin)
out={
 "schema":"chacha.dev/task-result/v1",
 "project":e["project"],
 "task_id":e["task"]["id"],
 "status":"OK",
 "producer":"v619-pilot-adapter",
 "observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "summary":"V6.19 task contract binding pilot",
 "evidence":[],
 "verification":{"status":"UNVERIFIED","method":"none","verifier":"pending-independent-verifier","observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat()},
 "outputs":[]
}
print(json.dumps(out,separators=(",",":")))
PY
chmod 0755 "$WORK/pilot-adapter.py"

cat >"$WORK/adapters.json" <<JSON
{
  "schema":"chacha.dev/provider-adapters/v1",
  "providers":{"v619-local-pilot":{"adapter":"v619-pilot-adapter","execution":"vps"}},
  "adapters":{
    "v619-pilot-adapter":{
      "status":"ENABLED",
      "kind":"local-pilot",
      "supports":["read"],
      "executable":"$WORK/pilot-adapter.py"
    }
  }
}
JSON
cat >"$WORK/ledger.json" <<'JSON'
{
  "schema":"chacha.dev/evidence-ledger/v1",
  "project":"v619-runtime-pilot",
  "artifacts":{},
  "approvals":{}
}
JSON

RUNROOT="$WORK/runs"
python3 "$CURRENT/dev-hub/bin/run-controller.py"   --plan "$WORK/execution-plan.json"   --graph "$WORK/task-graph-bound.json"   --ledger "$WORK/ledger.json"   --policy "$CURRENT/dev-hub/config/run-controller.v1.json"   --adapters "$WORK/adapters.json"   --output-dir "$RUNROOT"   --execute >"$WORK/run-controller.out"

RUN_RECORD="$(find "$RUNROOT" -name run-record.json -type f | head -1)"
[ -n "$RUN_RECORD" ] && [ -f "$RUN_RECORD" ]
python3 - "$RUN_RECORD" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x["summary"]["succeeded"]==2,x
assert x["summary"]["blocked"]==0,x
for w in x["waves"]:
  for t in w["tasks"]:
    assert t["status"]=="SUCCEEDED",t
    assert (t["guardian_pre"] or {}).get("verdict")=="PASS",t
    assert (t["guardian_post"] or {}).get("verdict")=="PASS",t
PY
echo "CHACHA_DEV_V619_PLAN_TO_REAL_DISPATCH_BINDING=PASS"
echo "CHACHA_DEV_V619_EXTERNAL_GUARDIAN_PRE_POST_EXACT_CONTRACT=PASS"

# Negative control: mutate the plan binding after scheduling. Run Controller must fail closed
# before dispatch because graph and execution plan no longer carry the same signed-by-content binding.
python3 - "$WORK/execution-plan.json" "$WORK/execution-plan-tampered.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
t=x["waves"][0]["tasks"][0]
t["guardian_binding"]=dict(t["guardian_binding"])
t["guardian_binding"]["domain"]="tampered-domain"
json.dump(x,open(sys.argv[2],"w"),indent=2)
PY
TAMPER_RUNROOT="$WORK/tamper-runs"
python3 "$CURRENT/dev-hub/bin/run-controller.py"   --plan "$WORK/execution-plan-tampered.json"   --graph "$WORK/task-graph-bound.json"   --ledger "$WORK/ledger.json"   --policy "$CURRENT/dev-hub/config/run-controller.v1.json"   --adapters "$WORK/adapters.json"   --output-dir "$TAMPER_RUNROOT"   --execute >"$WORK/tamper-run.out" || true
TAMPER_RECORD="$(find "$TAMPER_RUNROOT" -name run-record.json -type f | head -1)"
[ -n "$TAMPER_RECORD" ] && [ -f "$TAMPER_RECORD" ]
python3 - "$TAMPER_RECORD" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
rows=[t for w in x["waves"] for t in w["tasks"]]
assert rows[0]["status"]=="BLOCKED",rows
assert any("TASK_GUARDIAN_BINDING_DRIFT" in b for b in rows[0].get("blockers") or []),rows[0]
assert x["summary"]["succeeded"]==0,x
PY
echo "CHACHA_DEV_V619_PLAN_BINDING_TAMPER_BLOCK=PASS"

python3 "$CURRENT/dev-hub/bin/guardian-coverage-heartbeat.py"   --repo-root "$CURRENT"   --manifest "$CURRENT/dev-hub/config/guardian-coverage-manifest.v1.json"   --policy "$CURRENT/dev-hub/config/guardian-runtime-policy.v1.json"   --client "$CURRENT/dev-hub/bin/guardian-client.py"   --output /opt/chacha-dev/runtime/guardian/coverage-latest.json >"$WORK/coverage.out"
grep -Fq 'CHACHA_DEV_GUARDIAN_COVERAGE_HEARTBEAT=PASS' "$WORK/coverage.out"
grep -Fq 'ALL_HOOKS_ACTIVE=YES' "$WORK/coverage.out"
echo "CHACHA_DEV_V619_GUARDIAN_COVERAGE_WITH_TASK_BINDER=PASS"

systemctl restart chacha-dev-guardian-coverage-heartbeat.timer >/dev/null 2>&1 || true
systemctl restart chacha-dev-guardian-alert-pull.timer >/dev/null 2>&1 || true
systemctl restart chacha-dev-technology-watch.timer >/dev/null 2>&1 || true

cat >"/opt/chacha-dev/evidence/v619-task-contract-binding-$STAMP.json" <<JSON
{"schema":"chacha.dev/v619-task-contract-binding-evidence/v1","revision":"$REV","observed_at":"$STAMP","graph_to_plan":"PASS","real_dispatch":"PASS","external_guardian_pre_post":"PASS","tamper_block":"PASS","automatic_external_spend_eur":0}
JSON

echo "CHACHA_DEV_V619_EVERY_TASK_GUARDIAN_BOUND=YES"
echo "CHACHA_DEV_V619_DYNAMIC_AGENT_TASK_CONTRACT=PASS"
echo "CHACHA_DEV_V619_DYNAMIC_COMPONENT_TASK_CONTRACT=PASS"
echo "CHACHA_DEV_V619_BINDING_DIGEST_ENFORCED=YES"
echo "CHACHA_DEV_V619_PRE_POST_EXACT_CONTRACT_IDENTITY=YES"
echo "CHACHA_DEV_V619_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V619_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V619_INSTALL=PASS"

trap - EXIT
cleanup
