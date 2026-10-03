#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path

def load(p:Path):
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise ValueError("JSON_OBJECT_REQUIRED:"+str(p))
    return x

def check(root:Path)->dict:
    cfg=root/"dev-hub/config"; r=load(cfg/"canonical-route-authority.v1.json")
    issues=[]
    if r.get("schema")!="chacha.dev/canonical-route-authority/v1":issues.append("SCHEMA_MISMATCH")
    p=r.get("principles") or {}
    required=["unknown_route_fails_closed","agents_cannot_expand_own_authority","guardian_sentinel_and_stop_cannot_be_bypassed","security_gate_unavailable_blocks_instead_of_fallback","fallback_must_be_predeclared","fallback_preserves_or_reduces_authority","ingress_components_have_no_technical_decision_authority","functional_intent_and_technical_execution_are_separate_authority_classes"]
    issues += ["PRINCIPLE_FALSE:"+k for k in required if p.get(k) is not True]
    routes={x.get("route_id"):x for x in r.get("routes") or [] if isinstance(x,dict)}
    for rid in ["direct-operator-functional-build","remote-mcp-functional-build","remote-mcp-governed-read","third-party-remote-fallback","internal-governed-execution"]:
        if rid not in routes:issues.append("ROUTE_MISSING:"+rid)
    mcp=routes.get("remote-mcp-functional-build") or {}; chain=mcp.get("chain") or []
    expected=["chacha-remote-operator-mcp","direct-operator-m2m","functional-translator","central-orchestrator","scheduler","run-controller","registered-adapter"]
    pos=-1
    for node in expected:
        try:n=chain.index(node,pos+1)
        except ValueError:issues.append("MCP_CHAIN_MISSING_OR_ORDER:"+node);break
        pos=n
    fb=routes.get("third-party-remote-fallback") or {}
    if "policy-denied-bypass" not in (fb.get("forbidden") or []):issues.append("FALLBACK_POLICY_DENIAL_NOT_BLOCKED")
    dop=load(cfg/"direct-operator.v1.json"); inv=dop.get("invariants") or {}
    for k in ["direct_operator_has_no_technical_decision_authority","canonical_route_authority_required","direct_central_orchestrator_bypass_forbidden","fallback_cannot_expand_authority","voice_gateway_has_no_build_auto_switch"]:
        if inv.get(k) is not True:issues.append("DIRECT_OPERATOR_INVARIANT:"+k)
    sch=load(cfg/"execution-scheduler.v1.json"); fail=sch.get("failover") or {}
    for k in ["preserve_authority_contract","fallback_cannot_expand_permissions","policy_denied_never_falls_back","security_gate_unavailable_never_falls_back"]:
        if fail.get(k) is not True:issues.append("SCHEDULER_FAILOVER:"+k)
    gr=load(cfg/"guardian-role-contracts.v1.json")
    for c in gr.get("contracts") or []:
        forb=c.get("forbidden_actions") or []
        for a in ["MODIFY_ROUTE_AUTHORITY_POLICY","BYPASS_CANONICAL_ROUTE","EXPAND_ROUTE_AUTHORITY"]:
            if a not in forb:issues.append("GUARDIAN_ROUTE_GUARD_MISSING:"+str(c.get("contract_id"))+":"+a)
    return {"schema":"chacha.dev/canonical-route-authority-verification/v1","status":"PASS" if not issues else "BLOCK","issue_count":len(issues),"issues":issues,"production_mutation_authorized":False,"automatic_external_spend_eur":0}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",type=Path,required=True);ap.add_argument("--output",type=Path);a=ap.parse_args()
    out=check(a.repo_root.resolve())
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print(json.dumps(out,sort_keys=True));return 0 if out["status"]=="PASS" else 20
if __name__=="__main__":raise SystemExit(main())
