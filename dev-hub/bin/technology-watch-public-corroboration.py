#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,ipaddress,json,re,ssl,time
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
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def sha(v:str)->str:return hashlib.sha256(v.encode("utf-8","replace")).hexdigest()

def sse_json(raw:str,expected_id:int|None=None)->dict[str,Any]:
    rows=[]
    for line in raw.splitlines():
        if not line.startswith("data:"):continue
        try:x=json.loads(line[5:].strip())
        except Exception:continue
        if isinstance(x,dict):rows.append(x)
    if expected_id is not None:
        for x in rows:
            if x.get("id")==expected_id:return x
    if rows:return rows[-1]
    try:
        x=json.loads(raw)
        if isinstance(x,dict):return x
    except Exception:pass
    raise ValueError("MCP_RESPONSE_INVALID")

class MCP:
    def __init__(self,endpoint:str,protocol:str,timeout:int):
        self.endpoint=endpoint;self.protocol=protocol;self.timeout=timeout;self.session=None;self.seq=0
    def _post(self,payload:dict[str,Any],expect:bool=True)->dict[str,Any]:
        data=json.dumps(payload,separators=(",",":")).encode()
        headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream","MCP-Protocol-Version":self.protocol}
        if self.session:headers["Mcp-Session-Id"]=self.session
        req=Request(self.endpoint,data=data,headers=headers,method="POST")
        with urlopen(req,timeout=self.timeout,context=ssl.create_default_context()) as r:
            if not self.session:self.session=r.headers.get("Mcp-Session-Id")
            raw=r.read(4*1024*1024).decode("utf-8","replace")
        return sse_json(raw,payload.get("id")) if expect else {}
    def initialize(self)->None:
        self.seq+=1
        x=self._post({"jsonrpc":"2.0","id":self.seq,"method":"initialize","params":{
          "protocolVersion":self.protocol,"capabilities":{},"clientInfo":{"name":"chacha-v801-public-corroboration","version":"8.0.1"}}})
        result=x.get("result") if isinstance(x.get("result"),dict) else {}
        if not self.session or not result.get("serverInfo"):raise RuntimeError("EXA_MCP_INITIALIZE_FAILED")
        self._post({"jsonrpc":"2.0","method":"notifications/initialized"},False)
    def tools(self)->set[str]:
        self.seq+=1;x=self._post({"jsonrpc":"2.0","id":self.seq,"method":"tools/list","params":{}})
        return {str(t.get("name")) for t in (x.get("result") or {}).get("tools") or [] if isinstance(t,dict)}
    def call(self,name:str,args:dict[str,Any])->str:
        self.seq+=1;x=self._post({"jsonrpc":"2.0","id":self.seq,"method":"tools/call","params":{"name":name,"arguments":args}})
        result=x.get("result") if isinstance(x.get("result"),dict) else {}
        if result.get("isError") is True:raise RuntimeError("EXA_MCP_TOOL_ERROR")
        parts=[]
        for c in result.get("content") or []:
            if isinstance(c,dict) and c.get("type")=="text":parts.append(str(c.get("text") or ""))
        return "\n".join(parts)

def public_url(value:str)->bool:
    try:
        p=urlparse(value);host=(p.hostname or "").lower().rstrip(".")
        if p.scheme not in {"http","https"} or not host or host.endswith(".onion") or p.username or p.password:return False
        try:
            ip=ipaddress.ip_address(host)
            return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)
        except ValueError:return True
    except Exception:return False

COMMON_SECOND_LEVEL={"co.uk","org.uk","ac.uk","com.au","net.au","org.au","co.nz","com.br","com.mx","co.jp","co.kr","com.sg","com.tr"}
def owner_for(url:str,author:str="")->str:
    if author and author.strip() and author.strip().casefold() not in {"n/a","unknown"}:return author.strip().casefold()
    host=(urlparse(url).hostname or "").lower().rstrip(".")
    parts=host.split(".")
    if len(parts)>=3 and ".".join(parts[-2:]) in COMMON_SECOND_LEVEL:return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts)>=2 else host

def parse_search(text:str)->list[dict[str,str]]:
    out=[]
    for block in re.split(r"\n\s*---\s*\n",text):
        tm=re.search(r"(?m)^Title:\s*(.+)$",block);um=re.search(r"(?m)^URL:\s*(\S+)",block)
        if not um:continue
        pm=re.search(r"(?m)^Published:\s*(.*)$",block);am=re.search(r"(?m)^Author:\s*(.*)$",block)
        hm=re.search(r"(?s)(?:^|\n)Highlights:\s*\n?(.*)$",block)
        out.append({"title":(tm.group(1).strip() if tm else ""),"url":um.group(1).strip(),
                    "published":(pm.group(1).strip() if pm else ""),"author":(am.group(1).strip() if am else ""),
                    "highlights":(hm.group(1).strip() if hm else "")})
    return out

def parse_fetch(text:str)->tuple[str,str]:
    um=re.search(r"(?m)^URL:\s*(\S+)",text);url=um.group(1).strip() if um else ""
    body=re.sub(r"^# .*?\nURL:\s*\S+\s*\n","",text,count=1,flags=re.S).strip()
    return url,body

def collect(request_doc:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    if request_doc.get("schema")!="chacha.dev/dark-intelligence-corroboration-request/v1":
        raise ValueError("CORROBORATION_REQUEST_SCHEMA_INVALID")
    cfg=policy["provider"];search=policy["search"]
    client=MCP(str(cfg["endpoint"]),str(cfg["protocol_version"]),int(search["request_timeout_seconds"]))
    started=time.time()
    try:
        client.initialize();tools=client.tools()
        required={"web_search_exa","web_fetch_exa"}
        if not required.issubset(tools):raise RuntimeError("EXA_REQUIRED_TOOLS_MISSING")
    except Exception as exc:
        return {"schema":OUT_SCHEMA,"status":"PROVIDER_UNAVAILABLE","provider":"exa-mcp","claims":[],
                "failure_class":"MCP_INITIALIZATION","detail":str(exc)[:500],
                "search_results_have_no_fact_authority":True,"automatic_external_spend_eur":0}
    primary=str(request_doc.get("source_ref") or "");primary_owner=owner_for(primary)
    rows=[]
    for claim in (request_doc.get("claims") or [])[:int(search["max_claims_per_run"])]:
        cid=str(claim.get("claim_id") or "");ctext=str(claim.get("claim_text") or "").strip()
        if not ctext:continue
        objective=("Find independent public-web sources that can corroborate or contradict this allegation. "
                   "Prefer official technical, security advisory, maintainer, postmortem, academic, or reputable independent technical sources. "
                   "Do not use .onion pages. Do not treat pages merely linked by the primary source as independent proof. "
                   "Return sources with enough text to assess whether they support or contradict the allegation.")
        try:
            raw=client.call("web_search_exa",{"query":ctext,"objective":objective,
                            "numResults":int(search["max_results_per_claim"])})
            found=parse_search(raw)
        except Exception as exc:
            rows.append({"claim_id":cid,"claim_text":ctext,"status":"SEARCH_FAILED","candidates":[],"detail":str(exc)[:500]});continue
        candidates=[];seen_urls=set();seen_owners=set()
        for item in found:
            url=item["url"]
            if not public_url(url) or url in seen_urls:continue
            owner=owner_for(url,item.get("author") or "")
            if search.get("exclude_primary_source",True) and primary_owner and owner==primary_owner:continue
            if owner in seen_owners:continue
            seen_urls.add(url);seen_owners.add(owner)
            try:
                fetched=client.call("web_fetch_exa",{"urls":[url],"maxCharacters":int(search["max_fetch_characters"])})
                f_url,body=parse_fetch(fetched)
                if f_url and public_url(f_url):url=f_url
                retrieval=bool(body.strip())
            except Exception:
                body="";retrieval=False
            candidates.append({
              "candidate_id":"cor-"+sha(cid+"\n"+url)[:20],"title":item.get("title"),"url":url,
              "source_owner":owner,"published":item.get("published"),"author":item.get("author"),
              "search_highlights":str(item.get("highlights") or "")[:3000],
              "retrieved_text":body[:int(search["max_fetch_characters"])],
              "content_sha256":sha(body) if body else None,"retrieval_verified":retrieval,
              "derived_from_primary_source":False,"source_class":"public_web",
              "fact_authority":"NONE"
            })
        rows.append({"claim_id":cid,"claim_text":ctext,"status":"PASS" if candidates else "NO_RESULTS","candidates":candidates})
        if time.time()-started>int(search["total_timeout_seconds"]):break
    all_candidates=sum(len(x.get("candidates") or []) for x in rows)
    return {"schema":OUT_SCHEMA,"status":"PASS" if all_candidates else "NO_RESULTS","provider":"exa-mcp",
            "claims":rows,"candidate_count":all_candidates,"read_only":True,
            "search_results_have_no_fact_authority":True,"retrieval_success_does_not_equal_claim_verification":True,
            "automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--request",type=Path,required=True);ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args();out=collect(load(a.request),load(a.policy));save(a.output,out);print(json.dumps(out,ensure_ascii=False))
    print("CHACHA_DEV_V801_PUBLIC_CORROBORATION_SEARCH="+str(out.get("status")))
    print("CHACHA_DEV_V801_EXA_FACT_AUTHORITY=NO")
    return 0 if out.get("status") in {"PASS","NO_RESULTS","PROVIDER_UNAVAILABLE"} else 2
if __name__=="__main__":raise SystemExit(main())
