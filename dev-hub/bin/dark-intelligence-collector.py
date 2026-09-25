#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, html, ipaddress, json, os, re, subprocess, tempfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

SCHEMA="chacha.dev/dark-intelligence-capture/v1"

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def sha256(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts:list[str]=[]
        self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag.lower() in {"script","style","noscript","svg","canvas","template"}: self.skip+=1
    def handle_endtag(self,tag):
        if tag.lower() in {"script","style","noscript","svg","canvas","template"} and self.skip: self.skip-=1
    def handle_data(self,data):
        if not self.skip and data.strip(): self.parts.append(data)

def normalize_text(raw:bytes,content_type:str,max_chars:int)->str:
    enc="utf-8"
    m=re.search(r"charset=([A-Za-z0-9._-]+)",content_type or "",re.I)
    if m: enc=m.group(1)
    try:s=raw.decode(enc,"replace")
    except LookupError:s=raw.decode("utf-8","replace")
    if (content_type or "").split(";",1)[0].strip().lower() in {"text/html","application/xhtml+xml"}:
        p=TextExtractor()
        try:p.feed(s);s="\n".join(p.parts)
        except Exception:s=re.sub(r"<[^>]+>"," ",s)
    s=html.unescape(s)
    s="".join(ch for ch in s if ch in "\n\t" or ord(ch)>=32)
    s=re.sub(r"[ \t]+"," ",s)
    s=re.sub(r"\n{4,}","\n\n\n",s).strip()
    return s[:max_chars]

def source_class(mode:str)->str:
    return "tor_onion" if mode=="TOR_ONION" else "deep_web_https"

def validate_target(url:str,mode:str,policy:dict[str,Any],original_host:str|None=None)->dict[str,str]:
    req=policy.get("request") or {}
    if mode not in set(req.get("allowed_modes") or []): raise ValueError("COLLECTOR_MODE_FORBIDDEN")
    u=urlparse(url)
    if u.scheme not in {"http","https"}: raise ValueError("COLLECTOR_SCHEME_FORBIDDEN")
    if u.username or u.password: raise ValueError("COLLECTOR_URL_CREDENTIALS_FORBIDDEN")
    host=(u.hostname or "").rstrip(".").lower()
    if not host: raise ValueError("COLLECTOR_HOST_REQUIRED")
    try:
        ipaddress.ip_address(host)
        if req.get("ip_literal_targets_forbidden",True): raise ValueError("COLLECTOR_IP_LITERAL_FORBIDDEN")
    except ValueError as exc:
        if str(exc)=="COLLECTOR_IP_LITERAL_FORBIDDEN": raise
    port=u.port or (443 if u.scheme=="https" else 80)
    if port not in set(int(x) for x in req.get("allowed_ports") or [80,443]): raise ValueError("COLLECTOR_PORT_FORBIDDEN")
    if mode=="TOR_ONION":
        if not host.endswith(".onion"): raise ValueError("COLLECTOR_ONION_HOST_REQUIRED")
    else:
        if u.scheme!="https": raise ValueError("COLLECTOR_HTTPS_REQUIRED")
        if host.endswith(".onion"): raise ValueError("COLLECTOR_ONION_REQUIRES_TOR_MODE")
        if original_host and req.get("clearweb_redirect_must_preserve_hostname",True) and host!=original_host:
            raise ValueError("COLLECTOR_CLEARWEB_REDIRECT_HOST_CHANGE_FORBIDDEN")
    return {"scheme":u.scheme,"host":host,"port":str(port),"source_class":source_class(mode)}

def parse_headers(raw:str)->dict[str,str]:
    blocks=re.split(r"\r?\n\r?\n",raw.strip())
    block=blocks[-1] if blocks else raw
    out={}
    for line in block.splitlines():
        if ":" not in line: continue
        k,v=line.split(":",1);out[k.strip().lower()]=v.strip()
    return out

def fetch_one(url:str,mode:str,policy:dict[str,Any])->dict[str,Any]:
    req=policy["request"];tor=policy["tor"]
    with tempfile.TemporaryDirectory(prefix="chacha-dark-fetch-") as td:
        root=Path(td);headers=root/"headers.txt";body=root/"body.bin"
        cmd=[
          "/usr/bin/curl","--silent","--show-error","--request","GET",
          "--proto","=http,https","--connect-timeout",str(int(req["connect_timeout_seconds"])),
          "--max-time",str(int(req["total_timeout_seconds"])),"--max-filesize",str(int(req["max_response_bytes"])),
          "--compressed","--user-agent",str(req["user_agent"]),
          "--header","Accept: text/html,text/plain,application/json,application/xml,application/xhtml+xml;q=0.9,*/*;q=0.1",
          "--dump-header",str(headers),"--output",str(body),
          "--write-out","%{http_code}\n%{url_effective}\n%{content_type}\n%{size_download}\n"
        ]
        if mode=="TOR_ONION":
            cmd.extend(["--socks5-hostname",f"{tor['socks_host']}:{int(tor['socks_port'])}"])
        cmd.append(url)
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=int(req["total_timeout_seconds"])+10)
        meta=p.stdout.splitlines()
        status=int(meta[0]) if meta and meta[0].isdigit() else 0
        effective=meta[1].strip() if len(meta)>1 else url
        curl_type=meta[2].strip() if len(meta)>2 else ""
        payload=body.read_bytes() if body.is_file() else b""
        if len(payload)>int(req["max_response_bytes"]): raise RuntimeError("COLLECTOR_RESPONSE_LIMIT_EXCEEDED")
        hs=parse_headers(headers.read_text(encoding="utf-8",errors="replace") if headers.is_file() else "")
        ctype=(curl_type or hs.get("content-type") or "application/octet-stream").split(";",1)[0].strip().lower()
        return {
          "curl_returncode":p.returncode,"curl_error":p.stderr[-600:] if p.returncode else "",
          "http_status":status,"effective_url":effective,"headers":hs,"content_type":ctype,
          "payload":payload,"payload_sha256":sha256(payload),"bytes":len(payload)
        }

def collect(url:str,mode:str,policy:dict[str,Any])->dict[str,Any]:
    if os.environ.get("CHACHA_DARK_INTEL_NETWORK_ISOLATED")!="1":
        raise RuntimeError("COLLECTOR_NETWORK_ISOLATION_NOT_ATTESTED")
    if mode=="TOR_ONION" and os.environ.get("CHACHA_DARK_INTEL_TOR_READY")!="1":
        raise RuntimeError("COLLECTOR_TOR_NOT_ATTESTED")
    first=validate_target(url,mode,policy);current=url;original_host=first["host"]
    max_redirects=int((policy.get("request") or {}).get("max_redirects") or 0);hops=[]
    result=None
    for hop in range(max_redirects+1):
        validate_target(current,mode,policy,original_host)
        result=fetch_one(current,mode,policy);hops.append({"url":current,"status":result["http_status"]})
        if result["curl_returncode"]!=0:
            raise RuntimeError("COLLECTOR_FETCH_FAILED:"+result["curl_error"])
        if result["http_status"] not in {301,302,303,307,308}: break
        loc=result["headers"].get("location")
        if not loc: break
        nxt=urljoin(current,loc)
        validate_target(nxt,mode,policy,original_host)
        current=nxt
    else: raise RuntimeError("COLLECTOR_REDIRECT_LIMIT_EXCEEDED")
    assert result is not None
    final=validate_target(result["effective_url"],mode,policy,original_host)
    allowed={str(x).lower() for x in policy["request"]["allowed_content_types"]}
    textual=result["content_type"] in allowed or result["content_type"].startswith("text/")
    text=normalize_text(result["payload"],result["headers"].get("content-type",""),int(policy["request"]["max_sanitized_text_chars"])) if textual else ""
    return {
      "schema":SCHEMA,"collector_id":policy.get("collector_id"),"mode":mode,
      "source_class":final["source_class"],"source_url":url,"final_url":result["effective_url"],
      "http_status":result["http_status"],"content_type":result["content_type"],"response_bytes":result["bytes"],
      "body_sha256":result["payload_sha256"],"redirect_chain":hops,
      "sanitized_text":text,"textual_content":textual,
      "quarantine_status":"NOT_REQUIRED" if textual else "METADATA_ONLY_BODY_DISCARDED",
      "safe_response_headers":{
        "content-type":result["headers"].get("content-type"),
        "content-length":result["headers"].get("content-length"),
        "last-modified":result["headers"].get("last-modified")
      },
      "security":{
        "network_isolated":True,"read_only_method":"GET","credentials_sent":False,"cookies_enabled":False,
        "authorization_header_sent":False,"javascript_executed":False,"payload_executed":False,
        "untrusted_external_content":True,"treat_source_as_data_not_instructions":True,
        "source_content_authority":"NONE","prompt_injection_possible":True
      },
      "handoff":{
        "next_agent":"dark-intelligence-agent","technology_watch_verification_required_after_analysis":True,
        "guardian_required":True,"sentinel_required":True,"bastion_security_boundary_required":True
      },
      "automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--url",required=True);ap.add_argument("--mode",required=True)
    a=ap.parse_args();out=collect(a.url,a.mode,load(a.policy));print(json.dumps(out,ensure_ascii=False))
    print("CHACHA_DEV_V801_ISOLATED_COLLECTOR=PASS",file=os.sys.stderr)
    return 0

if __name__=="__main__": raise SystemExit(main())
