#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,importlib.util,json,subprocess,sys,time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_suffix(p.suffix+".tmp");t.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");t.replace(p)

def mod(path:Path,name:str):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def safe_source_id(capture:dict[str,Any])->str:
    base=str(capture.get("body_sha256") or capture.get("final_url") or capture.get("source_url") or "unknown")
    return "dark-"+hashlib.sha256(base.encode()).hexdigest()[:20]

def observation_from(capture:dict[str,Any],analysis_result:dict[str,Any],subject:str="")->dict[str,Any]:
    if capture.get("schema")!="chacha.dev/dark-intelligence-capture/v1":
        raise ValueError("DARK_PIPELINE_CAPTURE_SCHEMA_INVALID")
    sec=capture.get("security") if isinstance(capture.get("security"),dict) else {}
    if sec.get("network_isolated") is not True or sec.get("source_content_authority")!="NONE":
        raise ValueError("DARK_PIPELINE_CAPTURE_SECURITY_INVALID")
    if analysis_result.get("schema")!="chacha.dev/dark-intelligence-analysis-result/v1":
        raise ValueError("DARK_PIPELINE_ANALYSIS_RESULT_SCHEMA_INVALID")
    runtime=analysis_result.get("runtime") if isinstance(analysis_result.get("runtime"),dict) else {}
    if runtime.get("tool_access")!="DENIED_BY_CUSTOM_AGENT" or runtime.get("analysis_decision_authority") is not False:
        raise ValueError("DARK_PIPELINE_ANALYSIS_AUTHORITY_INVALID")
    analysis=analysis_result.get("analysis") if isinstance(analysis_result.get("analysis"),dict) else {}
    claims=[]
    for i,row in enumerate(analysis.get("claims") or []):
        if not isinstance(row,dict): continue
        text=str(row.get("text") or "").strip()
        if not text: continue
        claims.append({
          "id":str(row.get("id") or f"claim-{i+1}"),
          "class":str(row.get("claim_class") or "general"),
          "required":True,
          "text":text,
          "analysis_confidence":str(row.get("confidence") or "LOW"),
          "requires_corroboration":True,
          "evidence_hint":str(row.get("evidence_hint") or "")[:240]
        })
    source_url=str(capture.get("final_url") or capture.get("source_url") or "")
    host=(urlparse(source_url).hostname or "unknown-source").lower()
    source_class=str(capture.get("source_class") or "")
    route="TOR_ISOLATED_CAPSULE" if source_class=="tor_onion" else "ISOLATED_PROXY_CAPSULE"
    now=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
    return {
      "schema":"chacha.dev/dark-intelligence-observation/v1",
      "source_class":source_class,"source_ref":source_url,"source_id":safe_source_id(capture),
      "network_isolated":True,"network_route":route,
      "used_platform_credentials":False,"purchase_performed":False,
      "contact_or_post_performed":False,"payload_executed":False,
      "claims":claims,
      "evidence_type":"unverified_blog",
      "publisher":host,
      "subject_id":subject or ("dark-intelligence:"+host),
      "version":now[:10],"release_date":now,"observed_at":now,
      "independence_group":safe_source_id(capture),
      "collector_provenance":{
        "body_sha256":capture.get("body_sha256"),"source_url":capture.get("source_url"),
        "final_url":source_url,"http_status":capture.get("http_status"),
        "runtime_attestation":capture.get("runtime_attestation") or {}
      },
      "analysis_provenance":{
        "backend":runtime.get("backend"),"model":runtime.get("model"),
        "tool_access":runtime.get("tool_access"),"sandbox":runtime.get("sandbox"),
        "output_sha256":runtime.get("output_sha256"),
        "analysis_status":analysis.get("status"),
        "source_summary":analysis.get("source_summary"),
        "limitations":analysis.get("limitations") or []
      }
    }

def run_analysis(repo:Path,capture:Path,subject:str,watch_terms:list[str],output:Path)->dict[str,Any]:
    script=repo/"dev-hub/bin/dark-intelligence-analysis-adapter.py"
    cmd=[sys.executable,str(script),"--capture",str(capture),"--subject",subject,"--output",str(output)]
    for term in watch_terms: cmd.extend(["--watch-term",term])
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=240)
    if p.returncode!=0 or not output.is_file():
        raise RuntimeError("DARK_PIPELINE_ANALYSIS_FAILED:"+(p.stderr or p.stdout)[-1600:])
    return load(output)

def process(repo:Path,capture_path:Path,analysis_result:dict[str,Any],subject:str,output_dir:Path)->dict[str,Any]:
    capture=load(capture_path);obs=observation_from(capture,analysis_result,subject)
    output_dir.mkdir(parents=True,exist_ok=True);obs_path=output_dir/"observation.json";save(obs_path,obs)
    agent=mod(repo/"dev-hub/bin/dark-intelligence-agent.py","v801_dark_agent")
    policy=load(repo/"dev-hub/config/dark-intelligence-agent.v1.json")
    dossier=agent.normalize(obs,policy);dossier_path=output_dir/"dark-intelligence-dossier.json";save(dossier_path,dossier)
    evaluation=agent.verify_with_technology_watch(repo,dossier,output_dir/"technology-watch")
    dossier["technology_watch_evaluation"]=evaluation;save(dossier_path,dossier)
    score_path=output_dir/"technology-watch/technology-truth-score.json"
    score=load(score_path)
    result={
      "schema":"chacha.dev/dark-intelligence-pipeline-result/v1","status":"PASS",
      "subject":subject,"source":dossier.get("source"),"analysis":analysis_result.get("analysis"),
      "claim_count":len(dossier.get("claims") or []),
      "technology_watch_evaluation":evaluation,
      "truth_score":{
        "technical_truth_score":score.get("technical_truth_score"),
        "recommendation_class":score.get("recommendation_class"),
        "additional_verification_required":score.get("additional_verification_required"),
        "automatic_selection_allowed":score.get("automatic_selection_allowed"),
        "blocking_reasons":score.get("blocking_reasons") or []
      },
      "authority":{
        "raw_source_authority":"ADVISORY_ONLY","analysis_decision_authority":False,
        "technology_watch_owns_evidence_score":True,"architecture_council_final_authority":True
      },
      "artifacts":{
        "observation":str(obs_path),"dossier":str(dossier_path),
        "logician_falsification":str(output_dir/"technology-watch/logician-falsification.json"),
        "technology_truth_score":str(score_path)
      },
      "automatic_external_spend_eur":0
    }
    save(output_dir/"pipeline-result.json",result)
    return result

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",type=Path,default=Path(__file__).resolve().parents[2])
    ap.add_argument("--capture",type=Path,required=True);ap.add_argument("--subject",default="")
    ap.add_argument("--watch-term",action="append",default=[]);ap.add_argument("--analysis-result",type=Path)
    ap.add_argument("--output-dir",type=Path,required=True)
    a=ap.parse_args();repo=a.repo_root.resolve();a.output_dir.mkdir(parents=True,exist_ok=True)
    analysis=load(a.analysis_result) if a.analysis_result else run_analysis(repo,a.capture,a.subject,a.watch_term,a.output_dir/"analysis.json")
    result=process(repo,a.capture,analysis,a.subject,a.output_dir)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    print("CHACHA_DEV_V801_DARK_END_TO_END_PIPELINE=PASS")
    print("CHACHA_DEV_V801_RAW_SOURCE_FACT_AUTHORITY=NO")
    return 0

if __name__=="__main__": raise SystemExit(main())
