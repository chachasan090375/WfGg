#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/adaptive-cognitive-routing-policy/v1"
CATALOG_SCHEMA="chacha.dev/cognitive-model-catalog/v1"
GATEWAY_SCHEMA="chacha.dev/cognitive-gateway-catalog/v1"
ECON_SCHEMA="chacha.dev/provider-economics/v1"
REQUEST_SCHEMA="chacha.dev/cognitive-task-request/v1"
HEALTH_SCORE={"HEALTHY":100,"DEGRADED":55,"UNKNOWN":0,"UNAVAILABLE":-100}
STATUS_SCORE={"ADOPT":100,"PILOT":85,"WATCH":65,"ASSESS":45,"DISCOVER":25,"DEPRECATE":5,"RETIRE":-100}

def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return value

def require_schema(value:dict[str,Any],expected:str,label:str)->None:
    if value.get("schema")!=expected:
        raise ValueError(f"SCHEMA_MISMATCH:{label}:{value.get('schema')}")

def as_int(value:Any,default:int=0)->int:
    try:return int(value)
    except Exception:return default

def classify(request:dict[str,Any],policy:dict[str,Any])->str:
    cfg=policy.get("classification") or {}
    classes=policy.get("task_classes") or {}
    privacy=str(request.get("privacy") or "normal").lower()
    if privacy in set(cfg.get("strict_local_privacy_values") or []): return "private-local"
    modalities={str(x).lower() for x in (request.get("modalities") or ["text"])}
    if modalities & set(cfg.get("multimodal_values") or []): return "multimodal"
    context=as_int(request.get("context_tokens"))
    long_cfg=classes.get("long-context") or {}
    if context>=as_int(long_cfg.get("minimum_context_tokens"),64000): return "long-context"
    explicit=str(request.get("task_class") or "")
    if explicit and explicit in classes: return explicit
    caps={str(x) for x in (request.get("capabilities") or [])}
    ranked=[]
    for name,item in classes.items():
        required=set(item.get("capabilities") or []) if isinstance(item,dict) else set()
        if required and caps & required:
            ranked.append((as_int(item.get("priority")),name))
    if ranked:return sorted(ranked,reverse=True)[0][1]
    complexity=str(request.get("complexity") or "").lower()
    if complexity in set(cfg.get("high_complexity_values") or []): return "deep-reasoning"
    return str(cfg.get("default_class") or "light-conversation")

def task_fit(model:dict[str,Any],tiers:list[str])->float:
    mt=[str(x) for x in (model.get("model_tiers") or [])]
    matches=[i for i,t in enumerate(tiers) if t in mt]
    if not matches:return 0.0
    fallback_penalty=min(matches)*12.5
    specialization_penalty=12.5 if mt and tiers and mt[0]!=tiers[0] else 0.0
    return max(50.0,100.0-fallback_penalty-specialization_penalty)

def evaluate_model(model:dict[str,Any],task_class:str,tiers:list[str],request:dict[str,Any],
                   policy:dict[str,Any],economics:dict[str,Any],gateways:dict[str,Any])->dict[str,Any]:
    blockers=[]
    status=str(model.get("status") or "DISCOVER")
    health=str(model.get("health_state") or "UNKNOWN")
    cost_class=str(model.get("cost_class") or "paid")
    locality=str(model.get("locality") or "external")
    quota=str(model.get("quota_state") or "UNKNOWN")
    fit=task_fit(model,tiers)
    gateway_id=str(model.get("gateway") or "")
    gateway=((gateways.get("gateways") or {}).get(gateway_id) or {}) if gateway_id else {}
    gateway_status=str(gateway.get("status") or "UNAVAILABLE")
    if status=="RETIRE": blockers.append("MODEL_RETIRED")
    allowed=set((gateways.get("eligibility") or {}).get("allowed_statuses") or [])
    if not gateway_id or gateway_status not in allowed: blockers.append("GATEWAY_NOT_ELIGIBLE")
    if gateway.get("decision_authority") is not False: blockers.append("GATEWAY_DECISION_AUTHORITY_FORBIDDEN")
    if health not in {"HEALTHY","DEGRADED"}: blockers.append("MODEL_NOT_HEALTHY")
    if fit<=0: blockers.append("TASK_CLASS_NOT_SUPPORTED")
    if task_class=="private-local" and locality not in {"local","owned"}:
        blockers.append("STRICT_LOCAL_EXTERNAL_MODEL_FORBIDDEN")
    if task_class=="private-local" and str(gateway.get("kind") or "")!="local-model-runtime":
        blockers.append("STRICT_LOCAL_EXTERNAL_GATEWAY_FORBIDDEN")
    if quota=="EXHAUSTED": blockers.append("QUOTA_EXHAUSTED")
    required_context=as_int(request.get("context_tokens"))
    if required_context and as_int(model.get("context_window"))<required_context:
        blockers.append("CONTEXT_WINDOW_INSUFFICIENT")
    cost=(economics.get("cost_classes") or {}).get(cost_class) or {"score":0,"automatic":False}
    if not bool(cost.get("automatic")) and not bool(request.get("paid_approved")):
        blockers.append("COST_APPROVAL_REQUIRED")
    weights=policy.get("selection_weights") or {}
    quality=float(model.get("quality_score") or 50)
    latency=float(model.get("latency_score") or 50)
    evidence=float(model.get("evidence_score") or 40)
    privacy_score=100.0 if locality in {"local","owned"} else 60.0
    health_score=float(HEALTH_SCORE.get(health,0))
    cost_score=float(cost.get("score") or 0)
    score=(fit*float(weights.get("task_fit",35))/100+
           quality*float(weights.get("quality",20))/100+
           cost_score*float(weights.get("cost",20))/100+
           health_score*float(weights.get("health",10))/100+
           privacy_score*float(weights.get("privacy",7))/100+
           latency*float(weights.get("latency",4))/100+
           evidence*float(weights.get("evidence",4))/100)
    score+=STATUS_SCORE.get(status,0)*0.02
    return {
      "model_id":model.get("id"),"gateway":gateway_id,"gateway_status":gateway_status,"provider":model.get("provider"),
      "model":model.get("model"),"status":status,"health_state":health,"cost_class":cost_class,
      "locality":locality,"eligible":not blockers,"blockers":blockers,"score":round(score,2),
      "task_fit":fit,"context_window":as_int(model.get("context_window")),"quota_state":quota
    }

def route(request:dict[str,Any],policy:dict[str,Any],catalog:dict[str,Any],economics:dict[str,Any],gateways:dict[str,Any])->dict[str,Any]:
    task_class=classify(request,policy)
    cls=(policy.get("task_classes") or {}).get(task_class) or {}
    tiers=[str(x) for x in (cls.get("model_tiers") or [])]
    candidates=[evaluate_model(m,task_class,tiers,request,policy,economics,gateways)
                for m in (catalog.get("models") or []) if isinstance(m,dict)]
    eligible=[x for x in candidates if x["eligible"]]
    eligible.sort(key=lambda x:(x["score"],str(x.get("model_id") or "")),reverse=True)
    candidates.sort(key=lambda x:(x["eligible"],x["score"],str(x.get("model_id") or "")),reverse=True)
    if not eligible:
        return {"schema":"chacha.dev/adaptive-cognitive-route/v1","status":"BLOCK","task_class":task_class,
                "selected":None,"alternatives":[],"candidates":candidates,
                "reason":"NO_ELIGIBLE_MODEL","production_activation_authorized":False,
                "automatic_external_spend_eur":0}
    selected=eligible[0]
    return {"schema":"chacha.dev/adaptive-cognitive-route/v1","status":"PASS","task_class":task_class,
            "selected":selected,"alternatives":eligible[1:4],"candidates":candidates,
            "reason":"CAPABILITY_HEALTH_COST_PRIVACY_QUALITY_SELECTION",
            "production_activation_authorized":False,"automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--catalog",type=Path,required=True)
    ap.add_argument("--economics",type=Path,required=True)
    ap.add_argument("--gateways",type=Path,required=True)
    ap.add_argument("--request",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    policy=load(a.policy);catalog=load(a.catalog);economics=load(a.economics);gateways=load(a.gateways);request=load(a.request)
    require_schema(policy,POLICY_SCHEMA,"policy");require_schema(catalog,CATALOG_SCHEMA,"catalog")
    require_schema(economics,ECON_SCHEMA,"economics");require_schema(gateways,GATEWAY_SCHEMA,"gateways");require_schema(request,REQUEST_SCHEMA,"request")
    out=route(request,policy,catalog,economics,gateways)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("ADAPTIVE_COGNITIVE_ROUTER="+out["status"])
    print("TASK_CLASS="+out["task_class"])
    chosen=out.get("selected") or {}
    print("SELECTED_MODEL="+str(chosen.get("model_id")))
    print("SELECTED_GATEWAY="+str(chosen.get("gateway")))
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if out["status"]=="PASS" else 20

if __name__=="__main__":
    raise SystemExit(main())
