#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,hashlib
from pathlib import Path

import technology_watch_runtime as tw
import planning_memory_runtime as pmr

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def slug(s):
    return re.sub(r"[^a-z0-9]+","-",s.lower()).strip("-")[:64] or "capability"

def generated_domain(owner,cid):
    dslug=slug(owner or cid)
    domain="domain-"+dslug if not str(owner).startswith("domain-") else str(owner)
    role=f"{dslug}-specialist"
    return domain,role,{
      "orchestrator":f"{domain}-orchestrator",
      "roles":[role],
      "capabilities":[cid],
      "keywords":[cid,dslug],
      "toolchain":[],
      "reviews":["qa","cybersecurity"],
      "generated_by":"capability-foundry",
      "promotion_state":"PROJECT_LOCAL"
    }

def generated_capability(cid,domain):
    return {
      "class":"execution",
      "providers":[{
        "id":"chacha-dev-architect",
        "status":"PILOT",
        "health":"runtime-check",
        "cost_class":"local",
        "scope":"project",
        "fallback":[]
      }],
      "generated_by":"capability-foundry",
      "owner_domain":domain,
      "promotion_state":"PROJECT_LOCAL"
    }

def platform_component_reassessment(contract,governance,watch):
    if contract.get("target_contract")!="chacha.dev/capability-foundry-platform-component-reassessment/v1":
        raise ValueError("CAPABILITY_FOUNDRY_PLATFORM_CONTRACT_INVALID")
    if str(contract.get("target_foundry") or "")!="capability-foundry":
        raise ValueError("CAPABILITY_FOUNDRY_PLATFORM_OWNER_INVALID")
    if str(governance.get("evolution_owner") or "")!="capability-foundry":
        raise ValueError("CAPABILITY_FOUNDRY_GOVERNANCE_OWNER_MISMATCH")
    cid=str(contract.get("component_id") or "")
    freshness=str(watch.get("snapshot_freshness") or "")
    watch_ok=freshness=="FRESH" or bool(watch.get("targeted_refresh_performed") is True)
    candidates=[x for x in watch.get("eligible_provider_candidates") or [] if isinstance(x,dict)]
    zero=[x for x in candidates if bool(x.get("zero_external_spend") is True) or float(x.get("external_spend_eur") or 0)==0]
    state="SHADOW_ASSESSED" if watch_ok else "BLOCKED_TECHNOLOGY_WATCH"
    return {
      "schema":"chacha.dev/capability-foundry-platform-component-shadow/v1",
      "mode":"PLATFORM_COMPONENT_REASSESSMENT","stage":"SHADOW","state":state,
      "component_id":cid,"governance_component_id":governance.get("component_id"),
      "governance_class":governance.get("governance_class"),"candidate_owner":"capability-foundry",
      "trigger_reasons":list(contract.get("trigger_reasons") or []),
      "required_controls":list(governance.get("required_controls") or []),
      "incumbent_is_control_group":True,
      "technology_watch":{
        "consulted":True,"snapshot_freshness":freshness,
        "targeted_refresh_performed":bool(watch.get("targeted_refresh_performed") is True),
        "source_snapshot_digest":watch.get("source_snapshot_digest"),
        "candidate_count":len(candidates),"zero_spend_candidate_count":len(zero),
        "automatic_external_spend_eur":0},
      "shadow_candidate_signals":[str(x.get("id") or x.get("provider_id") or "") for x in zero[:10] if str(x.get("id") or x.get("provider_id") or "")],
      "pilot_required":bool(contract.get("pilot_required") is True),
      "next_stage":"SHADOW_EVIDENCE_COLLECTION" if watch_ok else "TECHNOLOGY_WATCH_REVALIDATION",
      "materialization_authorized":False,"active_component_mutation":False,
      "promotion_authorized":False,"permission_expansion":False,
      "guardian_required":True,"sentinel_required":True,
      "logician_falsification_required":True,
      "architecture_council_final_authority":True,
      "automatic_external_spend_eur":0}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--request",required=True);ap.add_argument("--policy",required=True)
    ap.add_argument("--domains",required=True);ap.add_argument("--capabilities",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--domain-overlay")
    ap.add_argument("--capability-overlay")
    ap.add_argument("--routing-overlay")
    ap.add_argument("--memory-brief")
    a=ap.parse_args()
    req,policy,domains,caps=map(load,[a.request,a.policy,a.domains,a.capabilities])
    memory_brief=load(a.memory_brief) if a.memory_brief else {}
    existing_domains=domains.get("domains") or {}
    existing_caps=caps.get("capabilities") or {}
    project=str(req.get("project_id") or "unknown")
    repo_root=Path(__file__).resolve().parents[2]
    plans=[];domain_overlay={};cap_overlay={};roles={}
    for gap in req.get("missing_capabilities") or []:
        cid=str(gap.get("id") or "").strip()
        if not cid:continue
        owner_hint=str(gap.get("domain") or "").strip()
        watch=tw.consult(
            repo_root,
            consumer="capability-foundry",
            domain=owner_hint,
            capabilities=[cid],
        )
        memory_pkg={"id":"capability:"+cid,"domain":owner_hint,"kind":"capability-gap",
                    "capabilities":[cid],"roles":[],"toolchain":[]}
        advice=pmr.package_advice(memory_brief,memory_pkg)
        avoid_ids=pmr.avoid_ids(advice)
        already=cid in existing_caps
        if owner_hint in existing_domains:
            owner=owner_hint;create_domain=False;role=None;domain_def=None
        else:
            owner,role,domain_def=generated_domain(owner_hint,cid);create_domain=not already
        candidates=[
          x for x in (gap.get("architecture_candidates") or [])
          if not (isinstance(x,dict) and str(x.get("id") or "") in avoid_ids)
        ]
        memory_reuse=advice.get("reuse_candidates") or []
        technology_candidates=list(watch.get("eligible_provider_candidates") or [])
        # V6.41: an explicit build hint may come from the functional contract.
        # It is never inferred from the capability name and remains subject to
        # Technology Watch consultation, V6.40 fail-closed closure, the final
        # Architecture Council, and the V6.41 safe-build policy.
        build_profile=str(gap.get("build_profile") or "").strip()
        build_provider=str(gap.get("provider_id") or "").strip()
        if build_profile and build_provider:
            technology_candidates.append({
              "id":build_provider,
              "provider_id":build_provider,
              "adapter_id":gap.get("adapter_id"),
              "capability":cid,
              "build_profile":build_profile,
              "execution":gap.get("execution"),
              "supports":gap.get("supports"),
              "network_access":gap.get("network_access"),
              "credentials_required":gap.get("credentials_required"),
              "production_capable":gap.get("production_capable"),
              "external_spend_eur":gap.get("automatic_external_spend_eur",0),
              "zero_external_spend":gap.get("automatic_external_spend_eur",0)==0,
              "admissible_for_automatic_selection":False,
              "evidence":"functional-contract-build-hint-reviewed-by-technology-watch"
            })
        if create_domain and domain_def:
            domain_overlay[owner]=domain_def
            roles[role]={"capabilities":[cid],"default_risk":"medium","generated_by":"capability-foundry","promotion_state":"PROJECT_LOCAL"}
        if not already:
            cap_overlay[cid]=generated_capability(cid,owner)
        plans.append({
          "capability":cid,"already_registered":already,"owner_domain":owner,
          "create_domain":create_domain,
          "domain_factory_id":owner if create_domain else None,
          "generated_role":role,
          "technology_watch_required":True,
          "technology_candidates":technology_candidates,
          "technology_watch":{
            "consulted":True,
            "snapshot_freshness":watch.get("snapshot_freshness"),
            "targeted_refresh_performed":watch.get("targeted_refresh_performed"),
            "source_snapshot_digest":watch.get("source_snapshot_digest"),
            "zero_spend_candidate_available":watch.get("zero_spend_candidate_available"),
            "selection_rule":watch.get("selection_rule"),
            "automatic_external_spend_eur":0
          },
          "architecture_competition_required":(len(candidates)+len(memory_reuse))>=2,
          "architecture_candidates":candidates,
          "memory_reuse_proposals":memory_reuse,
          "memory_guided_planning":advice,
          "memory_avoid_components":sorted(avoid_ids),
          "memory_guided_candidate_count":len(memory_reuse),
          "sandbox_required":not already,
          "generic_collector":f"generic-domain-collector:{owner}",
          "project_domain_collector":f"project-domain-collector:{project}:{owner}",
          "contracts_required":["component","integration"],
          "fixtures_required":True,"rollback_required":True,
          "universal_materialization":{
            "required":not already,
            "governance_class":"OWNED_ARTIFACT",
            "owner_foundry":"capability-foundry",
            "status":"REUSED" if already else "PENDING_CANONICAL_REGISTRATION",
            "retention_policy":"OWNER_LIFECYCLE",
            "purge_policy":"UNIVERSAL_HYGIENE",
            "materialization_gate_required":not already,
            "birth_contract":{"schema":"chacha.dev/component-birth-contract/v1",
              "status":"REUSED" if already else "PENDING_CANONICAL_REGISTRATION",
              "owner_foundry":"capability-foundry","automatic_external_spend_eur":0},
            "automatic_external_spend_eur":0
          },
          "state":"REUSE" if already else "PROJECT_LOCAL_PILOT"
        })
    result={
      "schema":"chacha.dev/capability-foundry-plan/v1","project_id":project,"plans":plans,
      "domain_overlay":domain_overlay,"capability_overlay":cap_overlay,"role_overlay":roles,
      "created_domain_count":len(domain_overlay),"created_capability_count":len(cap_overlay),
      "technology_watch_consulted":True,
      "central_memory_recall_consumed":bool(memory_brief),
      "central_memory_brief_digest":memory_brief.get("brief_digest"),
      "memory_guided_plans":sum(1 for x in plans if x.get("memory_guided_candidate_count") or x.get("memory_avoid_components")),
      "core_replan_required":bool(cap_overlay or domain_overlay),
      "agent_foundry_rerun_required":bool(cap_overlay or domain_overlay),
      "promotion_requires_qualification":True
    }
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    if a.domain_overlay:
        Path(a.domain_overlay).write_text(json.dumps({"schema":"chacha.dev/domain-overlay/v1","domains":domain_overlay},indent=2,ensure_ascii=False)+"\n")
    if a.capability_overlay:
        Path(a.capability_overlay).write_text(json.dumps({"schema":"chacha.dev/capability-overlay/v1","capabilities":cap_overlay},indent=2,ensure_ascii=False)+"\n")
    if a.routing_overlay:
        Path(a.routing_overlay).write_text(json.dumps({"schema":"chacha.dev/agent-routing-overlay/v1","roles":roles},indent=2,ensure_ascii=False)+"\n")
    print("CHACHA_CAPABILITY_FOUNDRY=PASS")
    print("CHACHA_CAPABILITY_FOUNDRY_TECHNOLOGY_WATCH=CONSULTED")
    print("CAPABILITY_FOUNDRY_NEW="+str(result["created_capability_count"]))
    print("CAPABILITY_FOUNDRY_DOMAINS="+str(result["created_domain_count"]))
    print("CHACHA_CAPABILITY_FOUNDRY_CENTRAL_MEMORY_RECALL="+("CONSUMED" if result.get("central_memory_recall_consumed") else "ABSENT"))
    print("MEMORY_GUIDED_PLANS="+str(result["memory_guided_plans"]))
    print("CAPABILITY_FOUNDRY_PROJECT_LOCAL_OVERLAY=YES")
if __name__=="__main__":main()
