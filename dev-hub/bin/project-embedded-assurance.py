#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,shutil,time
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/project-embedded-assurance-policy/v1"
MANIFEST_SCHEMA="chacha.dev/project-embedded-assurance-manifest/v1"

def now()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");os.replace(tmp,p)
def digest_file(p:Path)->str:
    return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--project-id",required=True);ap.add_argument("--application-version",default="UNRELEASED")
    ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--runtime-script",type=Path,required=True)
    ap.add_argument("--relay-script",type=Path,required=True);ap.add_argument("--client-runtime",type=Path,required=True)
    ap.add_argument("--functional-contract",type=Path)
    ap.add_argument("--output-dir",type=Path,required=True);a=ap.parse_args()
    policy=load(a.policy)
    if policy.get("schema")!=POLICY_SCHEMA or policy.get("mandatory_for_all_projects") is not True:
        raise SystemExit("EMBEDDED_ASSURANCE_POLICY_INVALID")
    root=a.output_dir.resolve();root.mkdir(parents=True,exist_ok=True)
    runtime=root/"project-assurance-event.py";shutil.copy2(a.runtime_script,runtime);runtime.chmod(0o755)
    relay=root/"project-assurance-relay.py";shutil.copy2(a.relay_script,relay);relay.chmod(0o755)
    client=root/"project-assurance-client.mjs";shutil.copy2(a.client_runtime,client)
    policy_copy=root/"project-embedded-assurance.policy.json";shutil.copy2(a.policy,policy_copy)
    functional_contract_digest=None
    if a.functional_contract and a.functional_contract.is_file():
        functional_contract_digest=digest_file(a.functional_contract)
    identity_request={
      "schema":"chacha.dev/project-assurance-identity-request/v1",
      "project_id":a.project_id,
      "status":"PENDING_APPROVAL",
      "server_side_only":True,
      "client_secret_allowed":False,
      "private_key_must_not_be_committed":True,
      "required_before_production":True,
      "requested_at":now()
    }
    save(root/"project-assurance-identity-request.json",identity_request)
    active_roles=[
      str(role) for role,cfg in (policy.get("local_agents") or {}).items()
      if isinstance(cfg,dict) and str(cfg.get("status") or "")=="ACTIVE"
    ]
    if set(active_roles)!={"guardian","sentinel","curator","bastion","intendant"}:
        raise SystemExit("EMBEDDED_ASSURANCE_FIVE_ACTIVE_PROBES_REQUIRED")
    for role in active_roles:
        (root/"outbox"/role).mkdir(parents=True,exist_ok=True)
        (root/"delivered"/role).mkdir(parents=True,exist_ok=True)
    manifest={
      "schema":MANIFEST_SCHEMA,"project_id":a.project_id,"application_version":a.application_version,
      "created_at":now(),"mandatory":True,
      "guardian_local":{"enabled":True,"mode":"LOCAL_EVENT_PROBE","direct_mutation":False},
      "sentinel_local":{"enabled":True,"mode":"LOCAL_EVENT_PROBE","direct_mutation":False},
      "curator_local":{"enabled":True,"mode":"LOCAL_EVENT_PROBE","direct_mutation":False},
      "bastion_local":{"enabled":True,"mode":"LOCAL_EVENT_PROBE","direct_mutation":False},
      "intendant_local":{"enabled":True,"mode":"LOCAL_EVENT_PROBE","direct_mutation":False},
      "local_probes":{role:{"enabled":True,"mode":"LOCAL_EVENT_PROBE","direct_mutation":False} for role in active_roles},
      "relay":{"mode":"SERVER_SIDE_ONLY","client_direct_to_central":False,
               "private_key_embedded_in_client":False,"incremental":True,
               "same_origin_client_endpoint":"/__chacha/assurance/v1/events",
               "project_specific_identity_required_for_production":True,
               "identity_status":"PENDING_APPROVAL"},
      "functional_contract":{"bound":functional_contract_digest is not None,
                             "digest":functional_contract_digest,
                             "required_for_guardian_local_production":True},
      "privacy":{"raw_user_content":False,"raw_prompt":False,"raw_message":False,
                 "credentials":False,"secrets":False,"client_side_secret":False},
      "paths":{"runtime":str(runtime),"relay":str(relay),"client_runtime":str(client),
               "policy":str(policy_copy),
               "identity_request":str(root/"project-assurance-identity-request.json"),
               "guardian_outbox":str(root/"outbox/guardian"),
               "sentinel_outbox":str(root/"outbox/sentinel"),
               "curator_outbox":str(root/"outbox/curator"),
               "bastion_outbox":str(root/"outbox/bastion"),
               "intendant_outbox":str(root/"outbox/intendant")},
      "production_readiness":{"guardian_local":True,"sentinel_local":True,
                              "curator_local":True,"bastion_local":True,"intendant_local":True,
                              "five_local_probes":True,
                              "privacy_contract":True,
                              "functional_contract_bound":functional_contract_digest is not None,
                              "relay_identity_active":False,
                              "ready":False},
      "central_orchestrator_owns_remediation":True,"automatic_external_spend_eur":0
    }
    manifest["bundle_digest"]="sha256:"+hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    save(root/"embedded-assurance.json",manifest)
    print("CHACHA_DEV_PROJECT_EMBEDDED_ASSURANCE=PASS")
    print("PROJECT_ID="+a.project_id);print("GUARDIAN_LOCAL=ENABLED");print("SENTINEL_LOCAL=ENABLED")
    print("CURATOR_LOCAL=ENABLED");print("BASTION_LOCAL=ENABLED");print("INTENDANT_LOCAL=ENABLED")
    print("ASSURANCE_RELAY=SERVER_SIDE_ONLY");print("PROJECT_ASSURANCE_IDENTITY=PENDING_APPROVAL")
    print("RAW_USER_CONTENT=NO");print("CLIENT_CENTRAL_SECRET=NO");print("DIRECT_MUTATION=NO");return 0
if __name__=="__main__":raise SystemExit(main())
