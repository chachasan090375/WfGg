#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,importlib.util,json,subprocess,sys,time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_ANALYSIS_QUEUE=Path("/opt/chacha-dev/runtime/dark-intelligence/analysis-queue")

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

def enqueue_deferred(repo:Path,capture:Path,subject:str,watch_terms:list[str],queue_root:Path)->dict[str,Any]:
    queue=mod(repo/"dev-hub/bin/dark-intelligence-analysis-queue.py","v801_dark_analysis_queue")
    job=queue.enqueue(queue_root,capture,subject,watch_terms)
    return {
      "job_id":job.get("job_id"),"status":job.get("status"),
      "attempt_count":job.get("attempt_count"),"next_attempt_epoch":job.get("next_attempt_epoch"),
      "queue_root":str(queue_root),"automatic_external_spend_eur":0
    }

def run_auto_corroboration(repo:Path,request_path:Path,output_dir:Path)->tuple[Path|None,dict[str,Any]]:
    research_dir=output_dir/"public-corroboration";research_dir.mkdir(parents=True,exist_ok=True)
    attempts=[]

    # Primary discovery: Exa MCP. Search-provider results never become evidence
    # directly; they only identify candidate public URLs.
    candidates_path=research_dir/"candidates-exa.json"
    search_script=repo/"dev-hub/bin/technology-watch-public-corroboration.py"
    search_policy=repo/"dev-hub/config/dark-intelligence-public-corroboration.v1.json"
    p=subprocess.run([sys.executable,str(search_script),"--policy",str(search_policy),
      "--request",str(request_path),"--output",str(candidates_path)],
      stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=150)
    if p.returncode==0 and candidates_path.is_file():
        candidates=load(candidates_path)
    else:
        candidates={"status":"PROVIDER_UNAVAILABLE","provider":"exa-mcp",
                    "detail":(p.stderr or p.stdout)[-800:]}
    attempts.append({"provider":"exa-mcp","status":candidates.get("status"),
                     "detail":candidates.get("detail")})

    # Zero-spend fallback: Firecrawl keyless is discovery-only. Every URL it
    # returns is re-fetched by ChaCha's own isolated HTTPS collector before it
    # may be classified as candidate evidence.
    if candidates.get("status") in {"PROVIDER_UNAVAILABLE","NO_RESULTS"}:
        fallback_path=research_dir/"candidates-firecrawl.json"
        fallback_script=repo/"dev-hub/bin/technology-watch-firecrawl-fallback.py"
        fallback_policy=repo/"dev-hub/config/dark-intelligence-firecrawl-fallback.v1.json"
        fp=subprocess.run([sys.executable,str(fallback_script),"--repo-root",str(repo),
          "--policy",str(fallback_policy),"--request",str(request_path),"--output",str(fallback_path)],
          stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=300)
        if fp.returncode==0 and fallback_path.is_file():
            fallback=load(fallback_path)
        else:
            fallback={"status":"PROVIDER_UNAVAILABLE","provider":"firecrawl-keyless",
                      "detail":(fp.stderr or fp.stdout)[-800:]}
        attempts.append({"provider":"firecrawl-keyless","status":fallback.get("status"),
                         "detail":fallback.get("detail")})
        if fallback.get("status")=="PASS":
            candidates=fallback;candidates_path=fallback_path
        elif candidates.get("status")!="PASS":
            if candidates.get("status")=="NO_RESULTS" and fallback.get("status")=="NO_RESULTS":
                return None,{"status":"NO_RESULTS","stage":"PUBLIC_SEARCH","retry_required":False,
                  "candidate_count":0,"provider_attempts":attempts,
                  "candidates_path":str(fallback_path)}
            return None,{"status":"DEFERRED_PROVIDER_UNAVAILABLE","stage":"PUBLIC_SEARCH",
              "retry_required":True,"retry_after_seconds":900,"provider_attempts":attempts,
              "candidates_path":str(fallback_path) if fallback_path.is_file() else str(candidates_path)}

    if candidates.get("status")=="NO_RESULTS":
        return None,{"status":"NO_RESULTS","stage":"PUBLIC_SEARCH","retry_required":False,
                     "candidate_count":0,"provider_attempts":attempts,
                     "candidates_path":str(candidates_path)}
    if candidates.get("status")!="PASS":
        return None,{"status":"DEFERRED_PROVIDER_UNAVAILABLE","stage":"PUBLIC_SEARCH",
                     "retry_required":True,"retry_after_seconds":900,
                     "provider_attempts":attempts,"candidates_path":str(candidates_path)}

    evidence_path=research_dir/"evidence.json"
    classifier=repo/"dev-hub/bin/dark-intelligence-corroboration-analysis.py"
    p=subprocess.run([sys.executable,str(classifier),"--candidates",str(candidates_path),
      "--output",str(evidence_path),"--timeout","180"],
      stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=240)
    if p.returncode!=0 or not evidence_path.is_file():
        return None,{"status":"DEFERRED_PROVIDER_UNAVAILABLE","stage":"SEMANTIC_CLASSIFICATION",
                     "detail":(p.stderr or p.stdout)[-800:],"retry_required":True,"retry_after_seconds":900,
                     "provider_attempts":attempts,"candidates_path":str(candidates_path)}
    evidence=load(evidence_path)
    verified_count=sum(1 for x in evidence.get("evidence") or [] if isinstance(x,dict) and x.get("verified") is True)
    if evidence.get("status")=="DEFERRED_PROVIDER_UNAVAILABLE":
        return evidence_path,{"status":"DEFERRED_PROVIDER_UNAVAILABLE","stage":"SEMANTIC_CLASSIFICATION",
                     "retry_required":True,"retry_after_seconds":int(evidence.get("retry_after_seconds") or 900),
                     "provider_attempts":attempts,"candidate_provider":candidates.get("provider"),
                     "candidate_count":int(candidates.get("candidate_count") or 0),
                     "verified_evidence_count":verified_count,
                     "candidates_path":str(candidates_path),"evidence_path":str(evidence_path)}
    return evidence_path,{"status":"PASS","stage":"COMPLETE","retry_required":False,
                 "provider_attempts":attempts,"candidate_provider":candidates.get("provider"),
                 "candidate_count":int(candidates.get("candidate_count") or 0),
                 "verified_evidence_count":verified_count,
                 "candidates_path":str(candidates_path),"evidence_path":str(evidence_path)}

def process(repo:Path,capture_path:Path,analysis_result:dict[str,Any],subject:str,output_dir:Path,
            corroboration_evidence:Path|None=None,auto_corroboration:bool=False)->dict[str,Any]:
    capture=load(capture_path);obs=observation_from(capture,analysis_result,subject)
    output_dir.mkdir(parents=True,exist_ok=True);obs_path=output_dir/"observation.json";save(obs_path,obs)
    agent=mod(repo/"dev-hub/bin/dark-intelligence-agent.py","v801_dark_agent")
    policy=load(repo/"dev-hub/config/dark-intelligence-agent.v1.json")
    dossier=agent.normalize(obs,policy);dossier_path=output_dir/"dark-intelligence-dossier.json";save(dossier_path,dossier)
    evaluation=agent.verify_with_technology_watch(repo,dossier,output_dir/"technology-watch")
    dossier["technology_watch_evaluation"]=evaluation;save(dossier_path,dossier)

    # Every dark/deep-web claim must leave the single-source state through an
    # explicit independent-corroboration request. The gate itself never searches
    # or decides facts; Technology Watch owns research/evidence scoring.
    corroboration=mod(repo/"dev-hub/bin/dark-intelligence-corroboration.py","v801_corroboration")
    corroboration_policy=load(repo/"dev-hub/config/dark-intelligence-corroboration.v1.json")
    corroboration_request=corroboration.search_request(dossier,corroboration_policy)
    corroboration_request_path=output_dir/"corroboration-request.json";save(corroboration_request_path,corroboration_request)
    corroboration_result=corroboration.evaluate(dossier,[],corroboration_policy)
    corroboration_path=output_dir/"corroboration.json";save(corroboration_path,corroboration_result)

    research={"status":"NOT_RUN","retry_required":False}
    if corroboration_evidence is None and auto_corroboration and (dossier.get("claims") or []):
        corroboration_evidence,research=run_auto_corroboration(repo,corroboration_request_path,output_dir)

    score_path=output_dir/"technology-watch/technology-truth-score.json"
    score=load(score_path)
    final_watch_dir=output_dir/"technology-watch"
    if corroboration_evidence:
        evidence_doc=load(corroboration_evidence)
        if evidence_doc.get("schema")!="chacha.dev/dark-intelligence-corroboration-evidence/v1":
            raise ValueError("DARK_PIPELINE_CORROBORATION_EVIDENCE_SCHEMA_INVALID")
        evidence_rows=[x for x in evidence_doc.get("evidence") or [] if isinstance(x,dict)]
        corroboration_result=corroboration.evaluate(dossier,evidence_rows,corroboration_policy)
        save(corroboration_path,corroboration_result)

        # Re-score with independently gathered evidence. Only evidence explicitly
        # marked verified may influence the second Technology Watch pass.
        verified_rows=[x for x in evidence_rows if x.get("verified") is True]
        dossier["corroboration"]=corroboration_result
        if verified_rows:
            tech=dossier.get("technology_dossier") if isinstance(dossier.get("technology_dossier"),dict) else {}
            tech_evidence=tech.get("evidence") if isinstance(tech.get("evidence"),list) else []
            tech["evidence"]=tech_evidence+verified_rows
            dossier["technology_dossier"]=tech
            final_watch_dir=output_dir/"technology-watch-corroborated"
            evaluation=agent.verify_with_technology_watch(repo,dossier,final_watch_dir)
            dossier["technology_watch_evaluation"]=evaluation
            score_path=final_watch_dir/"technology-truth-score.json"
            score=load(score_path)
        save(dossier_path,dossier)

    result={
      "schema":"chacha.dev/dark-intelligence-pipeline-result/v1",
      "status":"CORROBORATION_DEFERRED" if research.get("status")=="DEFERRED_PROVIDER_UNAVAILABLE" else "PASS",
      "subject":subject,"source":dossier.get("source"),"analysis":analysis_result.get("analysis"),
      "claim_count":len(dossier.get("claims") or []),
      "technology_watch_evaluation":evaluation,
      "corroboration":{
        "verdict":corroboration_result.get("verdict"),
        "claim_reports":corroboration_result.get("claim_reports") or [],
        "request_route":corroboration_request.get("route"),
        "independent_sources_required":True,
        "request_path":str(corroboration_request_path),
        "evaluation_path":str(corroboration_path),
        "research":research
      },
      "truth_score":{
        "technical_truth_score":score.get("technical_truth_score"),
        "recommendation_class":score.get("recommendation_class"),
        "additional_verification_required":score.get("additional_verification_required"),
        "automatic_selection_allowed":score.get("automatic_selection_allowed"),
        "blocking_reasons":score.get("blocking_reasons") or []
      },
      "authority":{
        "raw_source_authority":"ADVISORY_ONLY","analysis_decision_authority":False,
        "technology_watch_owns_evidence_score":True,"corroboration_gate_has_execution_authority":False,
        "architecture_council_final_authority":True
      },
      "artifacts":{
        "observation":str(obs_path),"dossier":str(dossier_path),
        "corroboration_request":str(corroboration_request_path),
        "corroboration_evaluation":str(corroboration_path),
        "logician_falsification":str(final_watch_dir/"logician-falsification.json"),
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
    ap.add_argument("--corroboration-evidence",type=Path)
    ap.add_argument("--no-auto-corroboration",action="store_true")
    ap.add_argument("--queue-root",type=Path,default=DEFAULT_ANALYSIS_QUEUE)
    ap.add_argument("--output-dir",type=Path,required=True)
    a=ap.parse_args();repo=a.repo_root.resolve();a.output_dir.mkdir(parents=True,exist_ok=True)
    analysis=load(a.analysis_result) if a.analysis_result else run_analysis(repo,a.capture,a.subject,a.watch_term,a.output_dir/"analysis.json")
    analysis_body=analysis.get("analysis") if isinstance(analysis.get("analysis"),dict) else {}
    if analysis_body.get("status")=="DEFERRED_PROVIDER_UNAVAILABLE":
        queued=enqueue_deferred(repo,a.capture.resolve(),a.subject,a.watch_term,a.queue_root.resolve())
        result={
          "schema":"chacha.dev/dark-intelligence-pipeline-result/v1",
          "status":"DEFERRED_PROVIDER_UNAVAILABLE","subject":a.subject,
          "claim_count":0,"technology_watch_evaluation":None,
          "truth_score":None,
          "authority":{
            "raw_source_authority":"ADVISORY_ONLY","analysis_decision_authority":False,
            "fact_promotion_allowed":False
          },
          "retry":{
            "required":True,
            "after_seconds":int((analysis.get("runtime") or {}).get("retry_after_seconds") or 900),
            "persistent_queue":True,
            "queue_job":queued
          },
          "automatic_external_spend_eur":0
        }
        save(a.output_dir/"pipeline-result.json",result)
    else:
        result=process(repo,a.capture,analysis,a.subject,a.output_dir,a.corroboration_evidence,not a.no_auto_corroboration)
        if result.get("status")=="CORROBORATION_DEFERRED":
            queued=enqueue_deferred(repo,a.capture.resolve(),a.subject,a.watch_term,a.queue_root.resolve())
            result["retry"]={"required":True,
              "after_seconds":int((((result.get("corroboration") or {}).get("research") or {}).get("retry_after_seconds") or 900)),
              "persistent_queue":True,"queue_job":queued}
            save(a.output_dir/"pipeline-result.json",result)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    print("CHACHA_DEV_V801_DARK_END_TO_END_PIPELINE=PASS")
    print("CHACHA_DEV_V801_RAW_SOURCE_FACT_AUTHORITY=NO")
    return 0

if __name__=="__main__": raise SystemExit(main())
