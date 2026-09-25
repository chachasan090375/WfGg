#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,ipaddress,json,subprocess,sys,tempfile,time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request,urlopen

OUT_SCHEMA="chacha.dev/dark-intelligence-corroboration-candidates/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise ValueError("JSON_ROOT_NOT_OBJECT")
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def sha(v:str)->str:
    return hashlib.sha256(v.encode("utf-8","replace")).hexdigest()

def public_https(value:str)->bool:
    try:
        p=urlparse(value);host=(p.hostname or "").lower().rstrip(".")
        if p.scheme!="https" or not host or host.endswith(".onion") or p.username or p.password:return False
        try:
            ip=ipaddress.ip_address(host)
            return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)
        except ValueError:return True
    except Exception:return False

COMMON_SECOND_LEVEL={"co.uk","org.uk","ac.uk","com.au","net.au","org.au","co.nz","com.br","com.mx","co.jp","co.kr","com.sg","com.tr"}
def publisher_domain(url:str)->str:
    host=(urlparse(url).hostname or "").lower().rstrip(".")
    parts=host.split(".")
    if len(parts)>=3 and ".".join(parts[-2:]) in COMMON_SECOND_LEVEL:return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts)>=2 else host

def search_firecrawl(query:str,policy:dict[str,Any])->tuple[list[dict[str,Any]],dict[str,Any]]:
    cfg=policy["provider"];s=policy["search"]
    body=json.dumps({"query":query,"limit":int(s["max_results_per_claim"]),"sources":["web"]},
                    separators=(",",":")).encode()
    req=Request(str(cfg["endpoint"]),data=body,method="POST",
                headers={"Content-Type":"application/json","Accept":"application/json",
                         "User-Agent":"ChaCha-TechnologyWatch/8.0.1 read-only"})
    with urlopen(req,timeout=int(s["request_timeout_seconds"])) as r:
        raw=r.read(4*1024*1024)
    x=json.loads(raw.decode("utf-8","strict"))
    if not isinstance(x,dict) or x.get("success") is not True:
        raise RuntimeError("FIRECRAWL_KEYLESS_SEARCH_NOT_SUCCESS")
    data=x.get("data") if isinstance(x.get("data"),dict) else {}
    rows=data.get("web") if isinstance(data.get("web"),list) else []
    return [r for r in rows if isinstance(r,dict)],{
      "request_id":x.get("id"),"credits_used":x.get("creditsUsed"),"authentication":"NONE",
      "automatic_external_spend_eur":0
    }

def isolated_refetch(repo:Path,url:str,policy:dict[str,Any])->dict[str,Any]|None:
    rpol=policy["retrieval"]
    with tempfile.TemporaryDirectory(prefix="chacha-public-corroboration-fetch-") as td:
        out=Path(td)/"capture.json"
        p=subprocess.run([
          sys.executable,str(repo/str(rpol["collector_runner"])),
          "--repo-root",str(repo),"--policy",str(repo/str(rpol["collector_policy"])),
          "--url",url,"--mode",str(rpol["mode"]),"--output",str(out)
        ],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
          check=False,timeout=220)
        if p.returncode!=0 or not out.is_file():return None
        x=load(out)
        if x.get("schema")!="chacha.dev/dark-intelligence-capture/v1":return None
        sec=x.get("security") if isinstance(x.get("security"),dict) else {}
        if sec.get("network_isolated") is not True or sec.get("source_content_authority")!="NONE":return None
        if x.get("textual_content") is not True:return None
        return x

def collect(request_doc:dict[str,Any],policy:dict[str,Any],repo:Path)->dict[str,Any]:
    if request_doc.get("schema")!="chacha.dev/dark-intelligence-corroboration-request/v1":
        raise ValueError("CORROBORATION_REQUEST_SCHEMA_INVALID")
    search=policy["search"];started=time.time()
    primary=str(request_doc.get("source_ref") or "");primary_owner=publisher_domain(primary)
    claims=[];provider_runs=[]
    for claim in (request_doc.get("claims") or [])[:int(search["max_claims_per_run"])]:
        cid=str(claim.get("claim_id") or "");ctext=str(claim.get("claim_text") or "").strip()
        if not ctext:continue
        try:
            found,meta=search_firecrawl(ctext,policy);provider_runs.append({"claim_id":cid,"status":"PASS",**meta})
        except Exception as exc:
            claims.append({"claim_id":cid,"claim_text":ctext,"status":"SEARCH_FAILED","candidates":[],"detail":str(exc)[:500]})
            provider_runs.append({"claim_id":cid,"status":"FAILED","detail":str(exc)[:500]});continue
        candidates=[];seen_urls=set();seen_owners=set()
        for item in found:
            url=str(item.get("url") or "").strip()
            if not public_https(url) or url in seen_urls:continue
            owner=publisher_domain(url)
            if search.get("exclude_primary_source",True) and primary_owner and owner==primary_owner:continue
            if search.get("deduplicate_by_publisher_domain",True) and owner in seen_owners:continue
            seen_urls.add(url);seen_owners.add(owner)
            capture=isolated_refetch(repo,url,policy)
            if capture is None:continue
            text=str(capture.get("sanitized_text") or "")[:int(search["max_fetch_characters"])]
            if not text.strip():continue
            candidates.append({
              "candidate_id":"cor-"+sha(cid+"\n"+url)[:20],
              "title":item.get("title"),"url":url,"source_owner":owner,
              "published":None,"author":None,
              "search_highlights":str(item.get("description") or "")[:3000],
              "retrieved_text":text,"content_sha256":capture.get("body_sha256"),
              "retrieval_verified":True,"retrieval_method":"CHACHA_ISOLATED_HTTPS_COLLECTOR",
              "retrieval_attestation":capture.get("runtime_attestation") or {},
              "derived_from_primary_source":False,"source_class":"public_web","fact_authority":"NONE"
            })
        claims.append({"claim_id":cid,"claim_text":ctext,"status":"PASS" if candidates else "NO_RESULTS","candidates":candidates})
        if time.time()-started>int(search["total_timeout_seconds"]):break
    count=sum(len(x.get("candidates") or []) for x in claims)
    any_search=any(x.get("status")=="PASS" for x in provider_runs)
    status="PASS" if count else ("NO_RESULTS" if any_search else "PROVIDER_UNAVAILABLE")
    return {
      "schema":OUT_SCHEMA,"status":status,"provider":"firecrawl-keyless",
      "provider_role":"DISCOVERY_ONLY","claims":claims,"candidate_count":count,
      "provider_runs":provider_runs,"read_only":True,
      "search_results_have_no_fact_authority":True,
      "provider_snippet_counts_as_retrieved_evidence":False,
      "isolated_refetch_required":True,
      "retrieval_success_does_not_equal_claim_verification":True,
      "automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path(__file__).resolve().parents[2])
    ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--request",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args();out=collect(load(a.request),load(a.policy),a.repo_root.resolve());save(a.output,out)
    print(json.dumps(out,ensure_ascii=False))
    print("CHACHA_DEV_V801_FIRECRAWL_FALLBACK="+str(out.get("status")))
    print("CHACHA_DEV_V801_FIRECRAWL_FACT_AUTHORITY=NO")
    return 0 if out.get("status") in {"PASS","NO_RESULTS","PROVIDER_UNAVAILABLE"} else 2

if __name__=="__main__":raise SystemExit(main())
