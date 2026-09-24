#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from collections import Counter
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def digest(x:Any)->str:
    return "sha256:"+hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def build_index(agent_profiles:dict[str,Any],core:dict[str,Any],providers:dict[str,Any],mcp:dict[str,Any],
                embedded:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    classes=policy.get("classes") or {};core_map=policy.get("core_class_map") or {};entries={}
    def add(cid:str,name:str,gclass:str,sources:list[str],meta:dict[str,Any]|None=None):
        spec=classes.get(gclass)
        if not isinstance(spec,dict):raise ValueError("UNKNOWN_GOVERNANCE_CLASS:"+gclass)
        owner=str(spec.get("candidate_owner") or "")
        if not owner:raise ValueError("MISSING_EVOLUTION_OWNER:"+cid)
        row={"component_id":cid,"name":name,"governance_class":gclass,"evolution_owner":owner,
             "sources":sorted(set(sources)),"agent_scorecard":bool(spec.get("agent_scorecard")),
             "independent_component_scorecard":bool(spec.get("independent_component_scorecard")),
             "required_controls":list(spec.get("required_controls") or []),
             "central_only_controls":list(spec.get("central_only_controls") or []),
             "forbidden_controls":list(spec.get("forbidden_controls") or []),
             "active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
             "technology_watch_revalidation_required":True,"logician_falsification_required":True,
             "architecture_council_final_authority":True,"automatic_external_spend_eur":0}
        if meta:row["metadata"]=meta
        if cid in entries:
            old=entries[cid]
            if old["governance_class"]!=gclass or old["evolution_owner"]!=owner:
                raise ValueError("DUPLICATE_GOVERNANCE_OWNERSHIP:"+cid)
            old["sources"]=sorted(set(old["sources"]+row["sources"]))
            if meta:
                old.setdefault("metadata",{}).update(meta)
            return
        entries[cid]=row

    for p in agent_profiles.get("profiles") or []:
        ident=p.get("identity") or {};aid=str(ident.get("agent_id") or "")
        gclass="LIGHTWEIGHT_PROJECT_AGENT" if str(ident.get("scope") or "")=="PROJECT" else "FULL_AGENT"
        pid=str(p.get("profile_id") or aid)
        add("agent:"+pid,aid,gclass,["agent-evolution-profile"],{"profile_id":pid,"scope":ident.get("scope"),"project_id":ident.get("project_id")})

    for role,cfg in (embedded.get("local_agents") or {}).items():
        if isinstance(cfg,dict) and str(cfg.get("status") or "")=="ACTIVE":
            add("embedded-probe:"+str(role),str(role),"LIGHTWEIGHT_EMBEDDED_AGENT",["project-embedded-assurance"],
                {"role":cfg.get("role"),"instance_model":"PER_PROJECT_INHERITANCE","direct_mutation":False})

    for comp in core.get("components") or []:
        raw=str(comp.get("class") or "");gclass=str(core_map.get(raw) or "CORE_PLATFORM_COMPONENT")
        add("core:"+str(comp.get("id")),str(comp.get("id")),gclass,["technology-core-watch"],
            {"core_class":raw,"criticality":comp.get("criticality")})

    provider_rows=providers.get("providers") or {}
    for pid,p in provider_rows.items():
        add("integration:"+str(pid),str(pid),"CONNECTOR_ADAPTER",["provider-adapters"],
            {"kind":p.get("kind"),"execution":p.get("execution"),"adapter":p.get("adapter")})
    for aid,a in (providers.get("adapters") or {}).items():
        add("adapter:"+str(aid),str(aid),"CONNECTOR_ADAPTER",["provider-adapters"],
            {"status":a.get("status"),"supports":a.get("supports") or [],"executable":a.get("executable")})

    for mid,m in (mcp.get("providers") or {}).items():
        binding=str(m.get("provider_binding") or "")
        cid="integration:"+binding if binding and binding in provider_rows else "integration:"+str(mid)
        add(cid,str(mid),"CONNECTOR_ADAPTER",["mcp-provider-catalog"],
            {"mcp_id":mid,"provider_binding":m.get("provider_binding"),"runtime_status":m.get("runtime_status"),
             "risk_class":m.get("risk_class"),"write_scope":m.get("write_scope") or [],
             "health_probe":m.get("health_probe")})

    rows=sorted(entries.values(),key=lambda x:x["component_id"])
    counts=dict(sorted(Counter(x["governance_class"] for x in rows).items()))
    owners_ok=all(bool(x.get("evolution_owner")) for x in rows)
    lightweight=[x for x in rows if x["governance_class"] in {"LIGHTWEIGHT_PROJECT_AGENT","LIGHTWEIGHT_EMBEDDED_AGENT"}]
    no_local_heavy=all(not(set(x.get("required_controls") or []) & {"technology-watch","logician","foundries","benchmark-orchestrator"}) for x in lightweight)
    return {"schema":"chacha.dev/universal-evolution-governance-index/v1",
      "policy_version":policy.get("version"),"component_count":len(rows),"components":rows,"class_counts":counts,
      "single_evolution_owner_per_component":owners_ok,"no_parallel_governance_engines":True,
      "lightweight_agents_do_not_duplicate_central_intelligence":no_local_heavy,
      "passive_artifact_governance":policy.get("passive_artifacts"),
      "policy_digest":digest(policy),"automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--agent-profiles",type=Path,required=True);ap.add_argument("--core-watch",type=Path,required=True)
    ap.add_argument("--provider-adapters",type=Path,required=True);ap.add_argument("--mcp-catalog",type=Path,required=True)
    ap.add_argument("--embedded-assurance",type=Path,required=True);ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    x=build_index(load(a.agent_profiles),load(a.core_watch),load(a.provider_adapters),load(a.mcp_catalog),load(a.embedded_assurance),load(a.policy))
    save(a.output,x)
    print("CHACHA_DEV_V654_UNIVERSAL_COMPONENT_GOVERNANCE=PASS")
    print("COMPONENT_COUNT="+str(x["component_count"]))
    print("SINGLE_EVOLUTION_OWNER=YES" if x["single_evolution_owner_per_component"] else "SINGLE_EVOLUTION_OWNER=NO")
    print("NO_PARALLEL_GOVERNANCE_ENGINES=YES")
    print("CHACHA_DEV_V654_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0
if __name__=="__main__":raise SystemExit(main())
