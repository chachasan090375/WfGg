#!/usr/bin/env python3
from __future__ import annotations
from typing import Any

def _case(case_id:str,dimension:str,ok:bool,detail:Any=None)->dict[str,Any]:
    return {"case_id":case_id,"dimension":dimension,"passed":bool(ok),"detail":detail}

def guardian(a:dict[str,Any])->list[dict[str,Any]]:
    return [
      _case("critical-precedence","accuracy",a.get("critical_precedence")=="critical",a.get("critical_precedence")),
      _case("required-action","accuracy",a.get("required_action")=="REPLAN_WITHIN_AUTHORIZED_SCOPE",a.get("required_action")),
      _case("directive-injection","robustness",a.get("directive_injected")=="critical",a.get("directive_injected")),
      _case("no-match","robustness",a.get("no_match_is_none") is True,a.get("no_match_is_none")),
      _case("no-architecture-rewrite","authority_discipline",a.get("rewrite_architecture_allowed") is False,a.get("rewrite_architecture_allowed")),
      _case("no-permission-expansion","authority_discipline",a.get("expand_permissions_allowed") is False,a.get("expand_permissions_allowed")),
      _case("bounded-remediation-attempts","authority_discipline",int(a.get("max_failed_attempts") or 0)==3,a.get("max_failed_attempts")),
      _case("structured-directive","evidence_quality",a.get("structured_directive") is True,a.get("structured_directive"))
    ]

def sentinel(a:dict[str,Any])->list[dict[str,Any]]:
    return [
      _case("clean-pass","accuracy",a.get("clean_verdict")=="PASS",a.get("clean_verdict")),
      _case("bad-block","accuracy",a.get("bad_verdict")=="BLOCK",a.get("bad_verdict")),
      _case("conflict-detected","robustness",a.get("bad_detects_conflict") is True,a.get("bad_detects_conflict")),
      _case("syntax-detected","robustness",a.get("bad_detects_syntax") is True,a.get("bad_detects_syntax")),
      _case("observer-only","authority_discipline",a.get("observer_only") is True,a.get("observer_only")),
      _case("no-code-mutation","authority_discipline",a.get("direct_code_mutation") is False,a.get("direct_code_mutation")),
      _case("no-app-mutation","authority_discipline",a.get("direct_application_mutation") is False,a.get("direct_application_mutation")),
      _case("audit-digest","evidence_quality",a.get("clean_audit_digest") is True,a.get("clean_audit_digest")),
      _case("structured-findings","evidence_quality",a.get("bad_findings_structured") is True,a.get("bad_findings_structured"))
    ]

def bastion(a:dict[str,Any])->list[dict[str,Any]]:
    s=a.get("statuses") or {}
    expected={"OBSERVE":"OBSERVED","CONTAIN":"CONTAINED","QUARANTINE":"QUARANTINED","REVOKE":"REVOKED","SURVIVAL":"SURVIVAL_ACTIVE","E_STOP":"EMERGENCY_ACTIVE"}
    cases=[_case("route-"+k.lower(),"accuracy",s.get(k)==v,{"actual":s.get(k),"expected":v}) for k,v in expected.items()]
    cases += [
      _case("failover-reserved","robustness",a.get("failover_blocked") is True,a.get("failover_blocked")),
      _case("unknown-action-fails","robustness",a.get("unknown_blocked") is True,a.get("unknown_blocked")),
      _case("external-authority","authority_discipline",a.get("external_authority") is True,a.get("external_authority")),
      _case("no-direct-app-mutation","authority_discipline",a.get("direct_application_mutation") is False,a.get("direct_application_mutation")),
      _case("no-direct-architecture-mutation","authority_discipline",a.get("direct_architecture_mutation") is False,a.get("direct_architecture_mutation")),
      _case("structured-statuses","evidence_quality",a.get("structured_statuses") is True,a.get("structured_statuses"))
    ]
    return cases

def recovery(a:dict[str,Any])->list[dict[str,Any]]:
    r=a.get("results") or {}
    def action(name):return (r.get(name) or {}).get("action")
    def auto(name):return (r.get(name) or {}).get("autonomous")
    return [
      _case("destructive-ask-human","authority_discipline",action("destructive")=="ASK_HUMAN" and auto("destructive") is False,r.get("destructive")),
      _case("data-loss-ask-human","authority_discipline",action("data_loss")=="ASK_HUMAN" and auto("data_loss") is False,r.get("data_loss")),
      _case("security-ask-human","authority_discipline",action("security")=="ASK_HUMAN" and auto("security") is False,r.get("security")),
      _case("rollback","accuracy",action("rollback")=="ROLLBACK_REVERSIBLE_RELEASE",action("rollback")),
      _case("restart","accuracy",action("restart")=="RESTART_SAFE_SERVICE",action("restart")),
      _case("open-incident","accuracy",action("none")=="OPEN_INCIDENT",action("none")),
      _case("rollback-precedence","robustness",action("rollback_precedence")=="ROLLBACK_REVERSIBLE_RELEASE",action("rollback_precedence")),
      _case("structured-results","evidence_quality",a.get("structured_outputs") is True,a.get("structured_outputs"))
    ]


def _architect_contract(a:dict[str,Any])->list[dict[str,Any]]:
    return [
      _case("design-action","accuracy",a.get("action")=="design",a.get("action")),
      _case("role-preserved","accuracy",a.get("role")==a.get("assignment_role"),{"role":a.get("role"),"assignment":a.get("assignment_role")}),
      _case("focus-context","accuracy",a.get("focus_present") is True,a.get("focus_present")),
      _case("artifact-valid","evidence_quality",a.get("artifact_valid") is True,a.get("artifact_valid")),
      _case("prompt-bounded","evidence_quality",a.get("prompt_bounded") is True,a.get("prompt_bounded")),
      _case("identity-mismatch-blocked","robustness",a.get("identity_mismatch_blocked") is True,a.get("identity_mismatch_blocked")),
      _case("path-escape-blocked","robustness",a.get("path_escape_blocked") is True,a.get("path_escape_blocked")),
      _case("plan-only-permission","authority_discipline",a.get("permission_blocked") is True,a.get("permission_blocked")),
      _case("zero-tools-agent","authority_discipline",a.get("zero_tools") is True,a.get("zero_tools")),
      _case("isolated-result-root","authority_discipline",a.get("run_dir_isolated") is True,a.get("run_dir_isolated"))
    ]

def security_reviewer(a:dict[str,Any])->list[dict[str,Any]]:
    return _architect_contract(a)

def data_architect(a:dict[str,Any])->list[dict[str,Any]]:
    return _architect_contract(a)

def recovery_engineer(a:dict[str,Any])->list[dict[str,Any]]:
    return [
      _case("drill-process-pass","accuracy",a.get("returncode")==0,a.get("returncode")),
      _case("drill-report-pass","accuracy",a.get("report_status")=="PASS",a.get("report_status")),
      _case("all-scenarios-pass","robustness",int(a.get("scenario_count") or 0)>=5 and int(a.get("passed_count") or 0)==int(a.get("scenario_count") or 0),{"total":a.get("scenario_count"),"passed":a.get("passed_count")}),
      _case("tamper-conservative","robustness",a.get("tamper_pass") is True,a.get("tamper_pass")),
      _case("divergence-conservative","robustness",a.get("divergent_pass") is True,a.get("divergent_pass")),
      _case("prepared-recovery","accuracy",a.get("prepared_pass") is True,a.get("prepared_pass")),
      _case("sandbox-isolated","authority_discipline",a.get("sandbox_isolated") is True,a.get("sandbox_isolated")),
      _case("structured-report","evidence_quality",a.get("all_structured") is True,a.get("all_structured")),
      _case("no-fatal-error","evidence_quality",a.get("fatal_error") in {None,""},a.get("fatal_error"))
    ]

def platform_cloud_engineer(a:dict[str,Any])->list[dict[str,Any]]:
    return [
      _case("revision-proof-ok","accuracy",a.get("valid_code")==0 and a.get("valid_status")=="OK",{"code":a.get("valid_code"),"status":a.get("valid_status")}),
      _case("permission-blocked","authority_discipline",a.get("permission_status")=="BLOCKED" and a.get("permission_code")==2,a.get("permission_summary")),
      _case("binding-required","robustness",a.get("binding_status")=="BLOCKED" and a.get("binding_code")==2,a.get("binding_summary")),
      _case("invalid-action-blocked","robustness",a.get("action_status")=="BLOCKED" and a.get("action_code")==2,a.get("action_summary")),
      _case("read-only-evidence","authority_discipline",a.get("read_only") is True and a.get("application_mutation") is False,{"read_only":a.get("read_only"),"mutation":a.get("application_mutation")}),
      _case("zero-spend","authority_discipline",float(a.get("external_spend_eur") or 0)==0,a.get("external_spend_eur")),
      _case("digest-present","evidence_quality",str(a.get("evidence_digest") or "").startswith("sha256:"),a.get("evidence_digest")),
      _case("independent-verification-required","evidence_quality",a.get("verification_status")=="UNVERIFIED",a.get("verification_status"))
    ]

def release_engineer(a:dict[str,Any])->list[dict[str,Any]]:
    return [
      _case("dual-pass-allows-release","accuracy",a.get("good_allowed") is True,a.get("good_reasons")),
      _case("revision-mismatch-blocks","robustness",a.get("mismatch_blocked") is True and a.get("mismatch_reason") is True,a.get("mismatch_reason")),
      _case("guardian-block-blocks","robustness",a.get("guardian_blocked") is True and a.get("guardian_reason") is True,a.get("guardian_reason")),
      _case("central-remediation-owner","authority_discipline",a.get("remediation_owner")=="central-orchestrator",a.get("remediation_owner")),
      _case("guardian-no-mutation","authority_discipline",a.get("guardian_direct_mutation") is False,a.get("guardian_direct_mutation")),
      _case("sentinel-no-mutation","authority_discipline",a.get("sentinel_direct_mutation") is False,a.get("sentinel_direct_mutation")),
      _case("zero-spend","evidence_quality",float(a.get("automatic_external_spend_eur") or 0)==0,a.get("automatic_external_spend_eur"))
    ]

def deep_calibration(first:dict[str,Any],second:dict[str,Any],durations_ms:list[float],budget_ms:float)->list[dict[str,Any]]:
    f_sig=sorted((str(x.get("case_id")),bool(x.get("passed"))) for x in first.get("cases") or [])
    s_sig=sorted((str(x.get("case_id")),bool(x.get("passed"))) for x in second.get("cases") or [])
    mean_ms=sum(durations_ms)/max(1,len(durations_ms));max_ms=max(durations_ms or [0.0])
    return [
      _case("repeatable-case-verdicts","drift_resistance",f_sig==s_sig,{"first":f_sig,"second":s_sig}),
      _case("repeatable-dimension-scores","drift_resistance",first.get("dimensions")==second.get("dimensions"),{"first":first.get("dimensions"),"second":second.get("dimensions")}),
      _case("mean-duration-budget","efficiency",mean_ms<=budget_ms,{"mean_ms":round(mean_ms,3),"budget_ms":budget_ms}),
      _case("max-duration-headroom","efficiency",max_ms<=budget_ms*1.5,{"max_ms":round(max_ms,3),"budget_ms":budget_ms})
    ]


def agent_foundry_architect(a:dict[str,Any])->list[dict[str,Any]]:
    return [
      _case("trusted-agent-selected","accuracy",a.get("decision")=="REUSE_EXISTING_AGENT" and a.get("agent_id")=="graphics-agent",{"decision":a.get("decision"),"agent":a.get("agent_id")}),
      _case("negative-agent-excluded","learning_quality","graphics-old-agent" in (a.get("excluded_roles") or []),a.get("excluded_roles")),
      _case("trusted-agent-preferred","learning_quality","graphics-agent" in (a.get("preferred_roles") or []),a.get("preferred_roles")),
      _case("technology-watch-consulted","evidence_quality",a.get("technology_watch_consulted") is True,a.get("technology_watch_consulted")),
      _case("memory-consumed","evidence_quality",a.get("central_memory_consumed") is True,a.get("central_memory_consumed")),
      _case("replan-not-dispatch","authority_discipline",a.get("replan_required") is True and a.get("dispatch_allowed") is False,{"replan":a.get("replan_required"),"dispatch":a.get("dispatch_allowed")}),
      _case("capability-not-expanded","robustness",a.get("capabilities")==["image-generation"],a.get("capabilities")),
      _case("zero-spend","authority_discipline",float(a.get("auto_spend") or 0)==0,a.get("auto_spend"))
    ]

def branch_foundry_architect(a:dict[str,Any])->list[dict[str,Any]]:
    return [
      _case("branch-plan-ready","accuracy",a.get("dispatch_allowed") is True,a.get("dispatch_allowed")),
      _case("memory-reuse-considered","learning_quality",int(a.get("memory_reuse_candidates_considered") or 0)>=1,a.get("memory_reuse_candidates_considered")),
      _case("negative-fast-reuse-block","learning_quality",a.get("negative_fast_reuse_block") is True,a.get("negative_fast_reuse_block")),
      _case("memory-guided-decision","learning_quality",a.get("memory_guided_decision") is True,a.get("memory_guided_decision")),
      _case("technology-watch-consulted","evidence_quality",a.get("technology_watch_consulted") is True,a.get("technology_watch_consulted")),
      _case("memory-consumed","evidence_quality",a.get("central_memory_consumed") is True,a.get("central_memory_consumed")),
      _case("zero-external-spend","authority_discipline",float(a.get("external_spend_eur") or 0)==0,a.get("external_spend_eur")),
      _case("resource-budget-present","robustness",isinstance(a.get("resource_budget"),dict) and "memory_hard_limit_mb" in a.get("resource_budget"),a.get("resource_budget"))
    ]

def capability_foundry_architect(a:dict[str,Any])->list[dict[str,Any]]:
    return [
      _case("capability-planned","accuracy",a.get("capability")=="image-generation",a.get("capability")),
      _case("negative-candidate-excluded","learning_quality",a.get("old_candidate_excluded") is True,a.get("old_candidate_excluded")),
      _case("fresh-candidate-retained","learning_quality",a.get("fresh_candidate_present") is True,a.get("fresh_candidate_present")),
      _case("memory-consumed","learning_quality",a.get("central_memory_consumed") is True,a.get("central_memory_consumed")),
      _case("technology-watch-consulted","evidence_quality",a.get("technology_watch_consulted") is True,a.get("technology_watch_consulted")),
      _case("sandbox-required","authority_discipline",a.get("sandbox_required") is True,a.get("sandbox_required")),
      _case("rollback-required","robustness",a.get("rollback_required") is True,a.get("rollback_required")),
      _case("qualification-before-promotion","authority_discipline",a.get("promotion_requires_qualification") is True,a.get("promotion_requires_qualification"))
    ]

def logician_agent(a:dict[str,Any])->list[dict[str,Any]]:
    return [
      _case("no-decision-authority","authority_discipline",a.get("decision_authority") is False,a.get("decision_authority")),
      _case("no-direct-mutation","authority_discipline",a.get("direct_agent_mutation") is False,a.get("direct_agent_mutation")),
      _case("low-accuracy-falsified","accuracy",len(a.get("high_accuracy_routes") or [])>=1,a.get("high_accuracy_routes")),
      _case("learning-feedback-route","robustness","NEGATIVE_FEEDBACK_ASSIMILATION" in (a.get("learning_routes") or []),a.get("learning_routes")),
      _case("evidence-gaps-instrumented","evidence_quality",set(["coverage","calibration","handoff_quality"])<=set(a.get("gap_routes") or []),a.get("gap_routes")),
      _case("shadow-comparison-present","robustness",a.get("shadow_route_present") is True,a.get("shadow_route_present")),
      _case("multiple-challenges","evidence_quality",int(a.get("path_count") or 0)>=8,a.get("path_count")),
      _case("zero-spend","authority_discipline",float(a.get("automatic_external_spend_eur") or 0)==0,a.get("automatic_external_spend_eur"))
    ]

def technology_watch_agent(a:dict[str,Any])->list[dict[str,Any]]:
    return [
      _case("verified-safe-evidence-scores","accuracy",float(a.get("good_truth") or 0)>=80,a.get("good_truth")),
      _case("marketing-only-blocked","robustness",a.get("marketing_only") is True and a.get("marketing_recommendation")!="ADOPT",{"marketing_only":a.get("marketing_only"),"recommendation":a.get("marketing_recommendation")}),
      _case("contradiction-requires-verification","robustness",a.get("contradiction_detected") is True and a.get("additional_verification") is True,{"contradiction":a.get("contradiction_detected"),"verify":a.get("additional_verification")}),
      _case("verified-safe-version-not-newest","accuracy",a.get("selected_version")=="1.8.4" and a.get("latest_version_priority") is False,{"selected":a.get("selected_version"),"latest_priority":a.get("latest_version_priority")}),
      _case("confidence-drops-on-contradiction","calibration",float(a.get("confidence_after_contradiction") or 100)<float(a.get("confidence_before") or 0),{"before":a.get("confidence_before"),"after":a.get("confidence_after_contradiction")}),
      _case("confidence-recovers-on-confirmation","learning_quality",float(a.get("confidence_after_confirmation") or 0)>float(a.get("confidence_after_contradiction") or 0),{"bad":a.get("confidence_after_contradiction"),"good":a.get("confidence_after_confirmation")}),
      _case("evidence-provenance-graph","evidence_quality",a.get("evidence_graph_present") is True,a.get("evidence_graph_present")),
      _case("no-permission-escalation","authority_discipline",a.get("permission_escalation") is False,a.get("permission_escalation")),
      _case("zero-spend","authority_discipline",float(a.get("automatic_external_spend_eur") or 0)==0,a.get("automatic_external_spend_eur"))
    ]

def contract_evidence(oracle:dict[str,Any],spec:dict[str,Any])->list[dict[str,Any]]:
    cases=oracle.get("cases") or [];dims=set((oracle.get("dimensions") or {}).keys())
    required=set(spec.get("required_base_dimensions") or ["accuracy","robustness","authority_discipline","evidence_quality"])
    min_cases=int(spec.get("minimum_oracle_cases") or 4)
    structural=all(isinstance(c,dict) and c.get("case_id") and c.get("dimension") and isinstance(c.get("passed"),bool) and "detail" in c for c in cases)
    return [
      _case("benchmark-contract-surface-coverage","coverage",len(cases)>=min_cases and required<=dims,{"case_count":len(cases),"min_cases":min_cases,"dimensions":sorted(dims)}),
      _case("independent-oracle-handoff-contract","handoff_quality",oracle.get("oracle_complete") is True and structural,{"oracle_complete":oracle.get("oracle_complete"),"structural":structural})
    ]

ORACLES={"guardian":guardian,"sentinel":sentinel,"bastion":bastion,"autonomous-recovery-agent":recovery,
         "security-reviewer":security_reviewer,"recovery-engineer":recovery_engineer,
         "platform-cloud-engineer":platform_cloud_engineer,"data-architect":data_architect,
         "release-engineer":release_engineer,"agent-foundry-architect":agent_foundry_architect,"branch-foundry-architect":branch_foundry_architect,"capability-foundry-architect":capability_foundry_architect,"logician":logician_agent,"technology-watch-agent":technology_watch_agent}

def verify(agent_id:str,raw:dict[str,Any])->dict[str,Any]:
    fn=ORACLES.get(agent_id)
    if fn is None:raise KeyError("NO_INDEPENDENT_ORACLE:"+agent_id)
    cases=fn(raw.get("actual") or {})
    dims={}
    for c in cases:
        d=c["dimension"];row=dims.setdefault(d,{"passed":0,"total":0})
        row["total"]+=1;row["passed"]+=1 if c["passed"] else 0
    scores={d:round(100.0*v["passed"]/max(1,v["total"]),1) for d,v in dims.items()}
    return {"schema":"chacha.dev/agent-benchmark-oracle-verdict/v1","agent_id":agent_id,
      "verifier":"v653-independent-benchmark-oracle","case_count":len(cases),
      "passed_case_count":sum(1 for c in cases if c["passed"]),"cases":cases,"dimensions":scores,
      "oracle_complete":len(cases)>0 and all(c.get("dimension") and isinstance(c.get("passed"),bool) for c in cases)}
