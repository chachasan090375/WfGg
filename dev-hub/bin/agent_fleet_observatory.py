#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
import agent_evolution_controller as aec
import agent_observation_bus as aob

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def safe_load(path:Path)->dict[str,Any]|None:
    try:return load(path)
    except Exception:return None

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def verified_sha256_ref(value:Any)->bool:
    ref=str(value or "")
    if "#sha256:" not in ref:return False
    raw,digest=ref.rsplit("#sha256:",1)
    if len(digest)!=64:return False
    try:
        path=Path(raw)
        if not path.is_file():return False
        return hashlib.sha256(path.read_bytes()).hexdigest()==digest
    except Exception:
        return False

def normalize_role(role:str,inventory_ids:set[str],policy:dict[str,Any])->str|None:
    role=str(role or "").strip()
    if not role:return None
    if role in inventory_ids:return role
    alias=(policy.get("role_aliases") or {}).get(role)
    if alias in inventory_ids:return str(alias)
    return None

def task_role_index(runtime_root:Path,inventory_ids:set[str],policy:dict[str,Any])->dict[tuple[str,str],set[str]]:
    out:dict[tuple[str,str],set[str]]=defaultdict(set)
    for path in runtime_root.glob("plans/**/*.task-graph.json"):
        x=safe_load(path)
        if not x or x.get("schema")!="chacha.dev/task-graph/v1":continue
        project=str(x.get("project") or "")
        for task in x.get("tasks") or []:
            if not isinstance(task,dict):continue
            tid=str(task.get("id") or "")
            aid=normalize_role(str(task.get("owner_role") or ""),inventory_ids,policy)
            if project and tid and aid:out[(project,tid)].add(aid)
    return out

def unique_agent(index:dict[tuple[str,str],set[str]],project:str,task_id:str)->str|None:
    rows=index.get((project,task_id)) or set()
    return next(iter(rows)) if len(rows)==1 else None

def guardian_state(value:Any)->str|None:
    if isinstance(value,dict):
        value=value.get("verdict") or value.get("status")
    s=str(value or "").upper()
    return s if s in {"PASS","WARNING","BLOCK","CRITICAL"} else None

def pct(num:float,den:float)->float|None:
    if den<=0:return None
    return round(max(0.0,min(100.0,100.0*num/den)),1)

def measured(value:float|None,evidence_count:int,source_refs:list[str])->dict[str,Any]:
    if value is None or evidence_count<=0:
        return {"status":"UNMEASURED","value":None,"evidence_count":0,"source_refs":[]}
    return {"status":"MEASURED","value":round(float(value),1),"evidence_count":int(evidence_count),"source_refs":source_refs[:25]}

def build_metrics(inventory:dict[str,Any],runtime_root:Path,policy:dict[str,Any])->dict[str,dict[str,Any]]:
    agents=inventory.get("agents") or []
    ids={str(a.get("agent_id")) for a in agents if a.get("agent_id")}
    idx=task_role_index(runtime_root,ids,policy)
    declared={str(a.get("agent_id")):set(str(x) for x in (a.get("capabilities") or [])) for a in agents if a.get("agent_id")}
    scopes={str(a.get("agent_id")):str(a.get("scope") or "") for a in agents if a.get("agent_id")}
    agg={aid:{
      "exec_success":0,"exec_failure":0,"timeouts":0,"attempts":0,"exec_events":0,
      "guardian_checks":0,"guardian_points":0.0,
      "authority_checks":0,"authority_points":0.0,
      "verified_total":0,"verified_ok":0,"verified_with_evidence":0,
      "specialist_review_total":0,"specialist_review_quality_ok":0,
      "project_adapter_evidence_total":0,"project_adapter_evidence_quality_ok":0,
      "operational_accuracy_total":0,"operational_accuracy_ok":0,
      "operational_evidence_total":0,"operational_evidence_ok":0,
      "handoff_total":0,"handoff_ok":0,
      "observed_capabilities":set(),"refs":defaultdict(list)
    } for aid in ids}

    # Runtime execution evidence.
    for path in runtime_root.glob("runs/**/run-record.json"):
        x=safe_load(path)
        if not x or x.get("schema")!="chacha.dev/run-record/v1":continue
        project=str(x.get("project") or "")
        for wave in x.get("waves") or []:
            if not isinstance(wave,dict):continue
            for task in wave.get("tasks") or []:
                if not isinstance(task,dict):continue
                tid=str(task.get("task_id") or "")
                aid=unique_agent(idx,project,tid)
                if not aid:continue
                a=agg[aid]
                for binding in task.get("provider_bindings") or []:
                    if isinstance(binding,dict) and binding.get("capability"):
                        a["observed_capabilities"].add(str(binding["capability"]))
                status=str(task.get("status") or "").upper()
                if status in {"SUCCEEDED","FAILED","TIMED_OUT"}:
                    a["exec_events"]+=1
                    a["attempts"]+=max(1,int(task.get("attempts") or 0))
                    a["refs"]["robustness"].append(str(path))
                    a["refs"]["efficiency"].append(str(path))
                    if status=="SUCCEEDED":a["exec_success"]+=1
                    else:
                        a["exec_failure"]+=1
                        if status=="TIMED_OUT":a["timeouts"]+=1
                for field in ("guardian_pre","guardian_post"):
                    gs=guardian_state(task.get(field))
                    if gs:
                        a["guardian_checks"]+=1
                        a["guardian_points"]+=100.0 if gs=="PASS" else 75.0 if gs=="WARNING" else 0.0
                        a["authority_checks"]+=1
                        a["authority_points"]+=100.0 if gs=="PASS" else 75.0 if gs=="WARNING" else 0.0
                        a["refs"]["authority_discipline"].append(str(path))

    # Independently verified producer results.
    for path in runtime_root.glob("transactions/**/verified-task-result.json"):
        x=safe_load(path)
        if not x or x.get("schema")!="chacha.dev/task-result/v1":continue
        verification=x.get("verification") or {}
        if str(verification.get("status") or "").upper()!="VERIFIED":continue
        project=str(x.get("project") or "");tid=str(x.get("task_id") or "")
        aid=unique_agent(idx,project,tid)
        if not aid:continue
        a=agg[aid];a["verified_total"]+=1
        if str(x.get("status") or "").upper()=="OK":a["verified_ok"]+=1
        if isinstance(x.get("evidence"),list) and len(x.get("evidence") or [])>0:a["verified_with_evidence"]+=1
        a["refs"]["accuracy"].append(str(path));a["refs"]["evidence_quality"].append(str(path))

    # V6.48 common observation bus: adds exact capability coverage and independent handoff evidence.
    try:
        trusted_observed=set(((policy.get("observation_bus") or {}).get("trusted_observed_sources") or []))
        for event in aob.read_events(runtime_root):
            if not isinstance(event,dict):continue
            aid=normalize_role(str(event.get("subject_role") or ""),ids,policy)
            if not aid:continue
            a=agg[aid]
            independent=str(event.get("source_id") or "")!=str(event.get("subject_role") or "")
            verification=str(event.get("verification") or "")
            source=str(event.get("source_id") or "")
            source_trusted=(verification=="VERIFIED" or (verification=="OBSERVED" and source in trusted_observed))
            if independent and source_trusted:
                for cap in event.get("capabilities") or []:
                    if str(cap):a["observed_capabilities"].add(str(cap))
                if event.get("capabilities"):a["refs"]["coverage"].append("agent-observation:"+str(event.get("event_id") or ""))
            et=str(event.get("event_type") or "")
            if independent and et in {"TASK_RESULT_VERIFIED","HISTORICAL_TASK_RESULT_VERIFIED","FINAL_REVIEW_VERIFIED"} and verification=="VERIFIED":
                a["handoff_total"]+=1
                if str(event.get("outcome") or "").upper()=="OK":a["handoff_ok"]+=1
                a["refs"]["handoff_quality"].append("agent-observation:"+str(event.get("event_id") or ""))
            if independent and et=="STAGE_EXECUTION_OBSERVED" and verification=="OBSERVED" and str(event.get("source_id") or "")=="central-orchestrator":
                a["exec_events"]+=1;a["attempts"]+=1
                if str(event.get("outcome") or "").upper()=="OK":a["exec_success"]+=1
                else:a["exec_failure"]+=1
                a["refs"]["robustness"].append("agent-observation:"+str(event.get("event_id") or ""))
                a["refs"]["efficiency"].append("agent-observation:"+str(event.get("event_id") or ""))
    except Exception:
        pass

    # V6.57 independently re-verified external specialist reviews.
    review_cfg=policy.get("specialist_review_evidence") or {}
    if review_cfg.get("enabled") is True:
        eligible=set(str(x) for x in (review_cfg.get("eligible_agents") or []))
        review_glob=str(review_cfg.get("glob") or "plans/**/automatic-finalization/**/reviews/*-source-reverified-review.json")
        for path in runtime_root.glob(review_glob):
            x=safe_load(path)
            if not x or x.get("schema")!="chacha.dev/compromise-agent-review/v1":continue
            aid=normalize_role(str(x.get("agent") or ""),ids,policy)
            if not aid or (eligible and aid not in eligible):continue
            if str(x.get("source_authority") or "")!="EXTERNAL":continue
            if x.get("source_reverified") is not True or x.get("post_implementation_second_read") is not True:continue
            if x.get("implementation_verified") is not True:continue
            if str(x.get("verdict") or "") not in {"ACCEPT","REVISE","BLOCK"}:continue
            if not str(x.get("receipt_id") or "") or not str(x.get("project_id") or "") or not str(x.get("revision") or ""):continue
            if not str(x.get("compromise_digest") or "").startswith("sha256:"):continue
            a=agg[aid];a["specialist_review_total"]+=1
            structured=all(k in x for k in ("receipt_id","project_id","revision","verdict","hard_objections","soft_objections","evidence_refs"))
            digest_ok=str(x.get("source_payload_digest") or "").startswith("sha256:")
            if digest_ok:
                a["specialist_review_quality_ok"]+=1
                a["refs"]["evidence_quality"].append(str(path))
            a["handoff_total"]+=1
            if structured:a["handoff_ok"]+=1
            a["refs"]["handoff_quality"].append(str(path))
            a["authority_checks"]+=1
            if x.get("direct_mutation") is False:a["authority_points"]+=100.0
            a["refs"]["authority_discipline"].append(str(path))

    # V6.58 project-local Radar adapter promotion evidence: structural production truth only.
    project_cfg=policy.get("project_local_adapter_evidence") or {}
    if project_cfg.get("enabled") is True:
        aid=str(project_cfg.get("eligible_agent") or "")
        required=[str(x) for x in (project_cfg.get("required_evidence") or [])]
        expected_adapter=str(project_cfg.get("adapter") or "")
        required_scope=str(project_cfg.get("required_scope") or "PROJECT")
        evidence_glob=str(project_cfg.get("glob") or "adapter-promotions/radar-runtime-adapter/**/promotion-evidence.json")
        if aid in agg and scopes.get(aid)==required_scope:
            for path in runtime_root.glob(evidence_glob):
                x=safe_load(path)
                if not x or x.get("schema")!="chacha.dev/adapter-promotion-evidence/v1":continue
                if expected_adapter and str(x.get("adapter") or "")!=expected_adapter:continue
                evidence=x.get("evidence") or {}
                if not all(isinstance(evidence.get(k),dict) and evidence[k].get("status")=="PASS" for k in required):continue
                structured=all(
                    str((evidence.get(k) or {}).get("source") or "") and
                    str((evidence.get(k) or {}).get("observed_at") or "") and
                    isinstance((evidence.get(k) or {}).get("details"),dict)
                    for k in required
                )
                provisioning=(evidence.get("provisioning-pass") or {}).get("details") or {}
                probe_ok=str(provisioning.get("probe_status") or "")=="PASS"
                a=agg[aid];a["project_adapter_evidence_total"]+=1
                if structured and probe_ok:
                    a["project_adapter_evidence_quality_ok"]+=1
                    a["refs"]["evidence_quality"].append(str(path))
                sandbox=(evidence.get("sandbox-only") or {}).get("details") or {}
                authority_ok=(
                    str(sandbox.get("production_radar_mutation") or "")=="NO" and
                    str(sandbox.get("registry_mutation") or "")=="NO" and
                    str(sandbox.get("radar_sentinel_guard") or "")=="PASS" and
                    str(sandbox.get("collector_sentinel_guard") or "")=="PASS"
                )
                a["authority_checks"]+=1
                if authority_ok:a["authority_points"]+=100.0
                a["refs"]["authority_discipline"].append(str(path))

    # V6.59 real Golden Path operational evidence.
    gp_cfg=policy.get("golden_path_operational_evidence") or {}
    if gp_cfg.get("enabled") is True:
        # Guardian external functional assurance receipts.
        cfg=gp_cfg.get("guardian") or {}
        if "guardian" in agg:
            for path in runtime_root.glob(str(cfg.get("glob") or "golden-path-runs/**/external-assurance/guardian-functional-receipt.json")):
                x=safe_load(path)
                if not x or x.get("schema")!=cfg.get("required_schema"):continue
                if str(x.get("guardian") or "")!=str(cfg.get("required_guardian") or "external-worker"):continue
                verdict=str(x.get("verdict") or "")
                if verdict not in {"PASS","BLOCK","REVISE"}:continue
                required=int(x.get("required_criteria_count") or 0)
                passed=int(x.get("passed_required_criteria_count") or 0)
                delivery=(x.get("assurance_exchange_delivery") or {})
                delivered=str(delivery.get("status") or "")==str(cfg.get("required_delivery_status") or "DELIVERED")
                structured=(
                    bool(str(x.get("receipt_id") or "")) and bool(str(x.get("project_id") or "")) and
                    len(str(x.get("revision") or ""))==40 and len(str(x.get("contract_digest") or ""))==64 and
                    x.get("original_functional_contract_pinned") is True and required>0
                )
                a=agg["guardian"]
                if cfg.get("accuracy_inference") is True:
                    a["operational_accuracy_total"]+=1
                    if verdict=="PASS" and passed==required:a["operational_accuracy_ok"]+=1
                    a["refs"]["accuracy"].append(str(path))
                a["operational_evidence_total"]+=1
                if structured and delivered:a["operational_evidence_ok"]+=1
                a["refs"]["evidence_quality"].append(str(path))
                a["handoff_total"]+=1
                if delivered:a["handoff_ok"]+=1
                a["refs"]["handoff_quality"].append(str(path))
                a["authority_checks"]+=1
                if x.get("direct_application_mutation") is False and x.get("central_orchestrator_owns_remediation") is True:
                    a["authority_points"]+=100.0
                a["refs"]["authority_discipline"].append(str(path))

        # Sentinel external technical assurance receipts with workflow attestation.
        cfg=gp_cfg.get("sentinel") or {}
        if "sentinel" in agg:
            for path in runtime_root.glob(str(cfg.get("glob") or "golden-path-runs/**/external-assurance/sentinel-technical-receipt.json")):
                x=safe_load(path)
                if not x or x.get("schema")!=cfg.get("required_schema"):continue
                if str(x.get("sentinel") or "")!=str(cfg.get("required_sentinel") or "external-worker"):continue
                if str(x.get("technical_verification_source") or "")!=str(cfg.get("required_verification_source") or "D1_WORKFLOW_ATTESTATION"):continue
                verdict=str(x.get("verdict") or "")
                if verdict not in {"PASS","BLOCK","REVISE"}:continue
                delivery=(x.get("assurance_exchange_delivery") or {})
                delivered=str(delivery.get("status") or "")==str(cfg.get("required_delivery_status") or "DELIVERED")
                structured=(
                    bool(str(x.get("receipt_id") or "")) and bool(str(x.get("project_id") or "")) and
                    len(str(x.get("revision") or ""))==40 and str(x.get("audit_digest") or "").startswith("sha256:") and
                    bool(str(x.get("workflow_run_id") or ""))
                )
                a=agg["sentinel"]
                if cfg.get("accuracy_inference") is True:
                    a["operational_accuracy_total"]+=1
                    if verdict=="PASS":a["operational_accuracy_ok"]+=1
                    a["refs"]["accuracy"].append(str(path))
                a["operational_evidence_total"]+=1
                if structured and delivered:a["operational_evidence_ok"]+=1
                a["refs"]["evidence_quality"].append(str(path))
                a["handoff_total"]+=1
                if delivered:a["handoff_ok"]+=1
                a["refs"]["handoff_quality"].append(str(path))
                a["authority_checks"]+=1
                if x.get("direct_code_mutation") is False and x.get("central_orchestrator_owns_remediation") is True:
                    a["authority_points"]+=100.0
                a["refs"]["authority_discipline"].append(str(path))

        # Acceptance Engine real results: structural production truth only, never accuracy.
        cfg=gp_cfg.get("acceptance-engineer") or {}
        if "acceptance-engineer" in agg:
            peer_name=str(cfg.get("evidence_peer_filename") or "acceptance-evidence.json")
            for path in runtime_root.glob(str(cfg.get("glob") or "golden-path-runs/**/external-assurance/acceptance.json")):
                x=safe_load(path);peer=safe_load(path.with_name(peer_name))
                if not x or x.get("schema")!=cfg.get("required_schema") or not peer:continue
                rows=[r for r in (x.get("criteria") or []) if isinstance(r,dict)]
                peers={str(r.get("criterion_id")):r for r in (peer.get("criteria") or []) if isinstance(r,dict)}
                if not rows:continue
                evidence_bound=all(
                    str(r.get("criterion_id") or "") in peers and
                    str(r.get("state") or "")==str(peers[str(r.get("criterion_id"))].get("state") or "") and
                    str(r.get("evidence") or "")==str(peers[str(r.get("criterion_id"))].get("evidence") or "") and
                    verified_sha256_ref(r.get("evidence"))
                    for r in rows
                )
                gate_ok=(
                    x.get("final_delivery_allowed") is False and
                    str(x.get("final_delivery_gate") or "")=="seven-agent-final-compromise" and
                    x.get("final_delivery_receipt_required") is True
                )
                handoff_ok=bool(x.get("delivery_allowed") is True and x.get("local_acceptance_candidate") is True and gate_ok)
                a=agg["acceptance-engineer"]
                a["operational_evidence_total"]+=1
                if evidence_bound:a["operational_evidence_ok"]+=1
                a["refs"]["evidence_quality"].append(str(path))
                a["handoff_total"]+=1
                if handoff_ok:a["handoff_ok"]+=1
                a["refs"]["handoff_quality"].append(str(path))
                a["authority_checks"]+=1
                if gate_ok:a["authority_points"]+=100.0
                a["refs"]["authority_discipline"].append(str(path))

    # V6.51 promoted benchmark evidence: benchmark-only measurements may fill UNKNOWN dimensions,
    # but never overwrite production/runtime measurements.
    benchmark_evidence={}
    bench_cfg=policy.get("benchmark_evidence") or {}
    bench_root=runtime_root/str(bench_cfg.get("promoted_dir") or "agent-evolution/benchmark-evidence")
    if bench_root.is_dir():
        for path in sorted(bench_root.glob("**/*.json")):
            x=safe_load(path)
            if not x or x.get("schema")!="chacha.dev/agent-benchmark-verified-evidence/v1":continue
            aid=str(x.get("agent_id") or "")
            if aid not in ids:continue
            if x.get("truth_scope")!="BENCHMARK_ONLY" or x.get("production_truth_eligible") is not False:continue
            if x.get("verification")!="BENCHMARK_VERIFIED" or not x.get("oracle_complete"):continue
            if str(x.get("verifier") or "") in {"",aid}:continue
            if x.get("overwrite_production_measurement") is not False:continue
            current=benchmark_evidence.get(aid)
            current_stamp=str((current or (None,{}))[1].get("promoted_at") or (current or (None,{}))[1].get("observed_at") or "")
            candidate_stamp=str(x.get("promoted_at") or x.get("observed_at") or "")
            if current is None or candidate_stamp>=current_stamp:
                benchmark_evidence[aid]=(path,x)

    # Exact component-confidence entries only; no fuzzy attribution.
    conf_path=runtime_root/"knowledge/component-confidence.json"
    conf=safe_load(conf_path) if conf_path.is_file() else None
    confidence_scores=policy.get("confidence_state_scores") or {}
    if conf and conf.get("schema")=="chacha.dev/component-confidence-snapshot/v1":
        for row in conf.get("items") or []:
            if not isinstance(row,dict) or str(row.get("component_kind"))!="agent":continue
            aid=str(row.get("component_id") or "")
            if aid not in agg:continue
            state=str(row.get("state") or "").upper()
            if state in confidence_scores:
                agg[aid]["learning_quality_value"]=float(confidence_scores[state])
                agg[aid]["learning_quality_state"]=state
                agg[aid]["refs"]["learning_quality"].append(str(conf_path))

    out={}
    for aid,a in agg.items():
        robustness=pct(a["exec_success"],a["exec_success"]+a["exec_failure"])
        efficiency=pct(a["exec_events"],a["attempts"]) if a["exec_events"] else None
        accuracy=pct(a["verified_ok"]+a["operational_accuracy_ok"],a["verified_total"]+a["operational_accuracy_total"])
        evidence_total=a["verified_total"]+a["specialist_review_total"]+a["project_adapter_evidence_total"]+a["operational_evidence_total"]
        evidence_ok=a["verified_with_evidence"]+a["specialist_review_quality_ok"]+a["project_adapter_evidence_quality_ok"]+a["operational_evidence_ok"]
        evidence_quality=pct(evidence_ok,evidence_total)
        authority=(round(a["authority_points"]/a["authority_checks"],1) if a["authority_checks"] else None)
        learning=a.get("learning_quality_value")
        declared_caps=declared.get(aid) or set()
        observed_declared=set(a["observed_capabilities"]) & declared_caps
        coverage=pct(len(observed_declared),len(declared_caps)) if declared_caps and a["observed_capabilities"] else None
        handoff=pct(a["handoff_ok"],a["handoff_total"])
        dims={
          "accuracy":measured(accuracy,a["verified_total"]+a["operational_accuracy_total"],a["refs"]["accuracy"]),
          "coverage":measured(coverage,len(observed_declared),a["refs"]["coverage"]),
          "calibration":{"status":"UNMEASURED","value":None,"evidence_count":0,"source_refs":[]},
          "evidence_quality":measured(evidence_quality,evidence_total,a["refs"]["evidence_quality"]),
          "robustness":measured(robustness,a["exec_events"],a["refs"]["robustness"]),
          "efficiency":measured(efficiency,a["exec_events"],a["refs"]["efficiency"]),
          "handoff_quality":measured(handoff,a["handoff_total"],a["refs"]["handoff_quality"]),
          "learning_quality":measured(learning,1 if learning is not None else 0,a["refs"]["learning_quality"]),
          "drift_resistance":{"status":"UNMEASURED","value":None,"evidence_count":0,"source_refs":[]},
          "authority_discipline":measured(authority,a["authority_checks"],a["refs"]["authority_discipline"])
        }
        bench_path,bench=benchmark_evidence.get(aid,(None,None))
        if bench:
            per_dim_counts={}
            for case in bench.get("cases") or []:
                if isinstance(case,dict) and case.get("dimension"):
                    d=str(case["dimension"]);per_dim_counts[d]=per_dim_counts.get(d,0)+1
            for d,value in (bench.get("dimensions") or {}).items():
                if d not in dims or not isinstance(value,(int,float)):continue
                if dims[d].get("status")!="UNMEASURED":continue
                dims[d]={"status":"MEASURED","value":round(float(value),1),
                         "evidence_count":int(per_dim_counts.get(d) or 1),"source_refs":[str(bench_path)],
                         "evidence_scope":"BENCHMARK_ONLY","verification":"BENCHMARK_VERIFIED",
                         "production_truth_eligible":False}
        out[aid]={
          "schema":"chacha.dev/agent-observed-metrics/v1",
          "agent_id":aid,
          "dimensions":dims,
          "dimension_evidence":{k:v for k,v in dims.items()},
          "verified_failures":max(0,a["verified_total"]-a["verified_ok"]),
          "rollbacks":0,
          "handoff_failures":0,
          "technology_debt":0,
          "scope_overlap_risk":0,
          "signals":{
            "execution_events":a["exec_events"],"execution_successes":a["exec_success"],
            "execution_failures":a["exec_failure"],"timeouts":a["timeouts"],
            "attempts":a["attempts"],"verified_results":a["verified_total"],
            "verified_ok":a["verified_ok"],"guardian_checks":a["guardian_checks"],
            "authority_checks":a["authority_checks"],"specialist_reviews":a["specialist_review_total"],
            "project_adapter_evidence":a["project_adapter_evidence_total"],
            "operational_accuracy_evidence":a["operational_accuracy_total"],
            "operational_structural_evidence":a["operational_evidence_total"],
            "observed_capabilities":sorted(a["observed_capabilities"]),
            "declared_capabilities":sorted(declared.get(aid) or set()),
            "handoff_total":a["handoff_total"],"handoff_ok":a["handoff_ok"],
            "component_confidence_state":a.get("learning_quality_state"),
            "benchmark_evidence_present":aid in benchmark_evidence,
            "benchmark_evidence_scope":"BENCHMARK_ONLY" if aid in benchmark_evidence else None
          }
        }
    return out

def risk_for(agent:dict[str,Any],routing:dict[str,Any],policy:dict[str,Any])->str:
    aid=str(agent.get("agent_id") or "")
    if aid in (policy.get("default_agent_risk_overrides") or {}):
        return str(policy["default_agent_risk_overrides"][aid])
    if agent.get("scope")=="PLATFORM":
        r=(routing.get("roles") or {}).get(aid) or {}
        return str(r.get("default_risk") or "medium")
    return "medium"

def build_report(repo_root:Path,runtime_root:Path,policy:dict[str,Any],evolution_policy:dict[str,Any],
                 routing:dict[str,Any],seven:dict[str,Any],project_regs:list[dict[str,Any]])->dict[str,Any]:
    inventory=aec.build_inventory(routing,seven,project_regs)
    metrics=build_metrics(inventory,runtime_root,policy)
    rows=[]
    for agent in inventory.get("agents") or []:
        aid=str(agent["agent_id"]);m=metrics.get(aid) or {"dimensions":{}}
        sc=aec.score(aid,m,evolution_policy);pl=aec.plan(aid,sc,evolution_policy)
        rows.append({
          **agent,
          "risk":risk_for(agent,routing,policy),
          "metrics":m,
          "scorecard":sc,
          "plan":pl
        })
    opt_rank={"BLOCK_AND_REVIEW":0,"SHADOW_CANDIDATE":1,"OPTIMIZE":2}
    risk_rank={r:i for i,r in enumerate(policy.get("queues",{}).get("risk_priority") or ["critical","high","medium","low"])}
    optimization=[r for r in rows if r["scorecard"]["recommendation"] in set(policy.get("queues",{}).get("optimization_recommendations") or [])]
    optimization.sort(key=lambda r:(opt_rank.get(r["scorecard"]["recommendation"],9),
                                    -(r["scorecard"]["agent_debt"] if isinstance(r["scorecard"]["agent_debt"],(int,float)) else -1),
                                    r["agent_id"]))
    measurement=[r for r in rows if r["scorecard"]["recommendation"] in set(policy.get("queues",{}).get("measurement_recommendations") or [])]
    measurement.sort(key=lambda r:(risk_rank.get(r["risk"],99),r["scorecard"]["measurement_coverage_pct"],r["agent_id"]))
    summary=defaultdict(int)
    for r in rows:summary[r["scorecard"]["recommendation"]]+=1
    return {
      "schema":"chacha.dev/agent-fleet-observatory-report/v1",
      "generated_at":now_iso(),
      "agent_count":len(rows),
      "agents":rows,
      "summary":dict(summary),
      "optimization_queue":[{"agent_id":r["agent_id"],"scope":r["scope"],"risk":r["risk"],
                             "recommendation":r["scorecard"]["recommendation"],"agent_debt":r["scorecard"]["agent_debt"],
                             "measurement_coverage_pct":r["scorecard"]["measurement_coverage_pct"],
                             "weakest_dimension":r["scorecard"]["weakest_dimension"]} for r in optimization],
      "measurement_queue":[{"agent_id":r["agent_id"],"scope":r["scope"],"risk":r["risk"],
                            "recommendation":r["scorecard"]["recommendation"],
                            "measurement_coverage_pct":r["scorecard"]["measurement_coverage_pct"],
                            "unmeasured_dimensions":r["scorecard"]["unmeasured_dimensions"]} for r in measurement],
      "unknown_dimension_default_score":None,
      "read_only":True,
      "agent_self_scoring_authority":False,
      "architecture_council_final_authority":True,
      "automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime"))
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--evolution-policy",type=Path,required=True)
    ap.add_argument("--routing",type=Path,required=True)
    ap.add_argument("--seven",type=Path,required=True)
    ap.add_argument("--project-registry",type=Path,action="append",default=[])
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    report=build_report(a.repo_root,a.runtime_root,load(a.policy),load(a.evolution_policy),load(a.routing),load(a.seven),[load(p) for p in a.project_registry])
    save(a.output,report)
    print("CHACHA_DEV_V647_AGENT_FLEET_OBSERVATORY=PASS")
    print("AGENT_COUNT="+str(report["agent_count"]))
    print("OPTIMIZATION_QUEUE="+str(len(report["optimization_queue"])))
    print("MEASUREMENT_QUEUE="+str(len(report["measurement_queue"])))
    print("CHACHA_DEV_V647_UNKNOWN_DEFAULT_SCORE=NONE")
    print("CHACHA_DEV_V647_AGENT_SELF_SCORING_AUTHORITY=NO")
    print("CHACHA_DEV_V647_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0

if __name__=="__main__":raise SystemExit(main())
