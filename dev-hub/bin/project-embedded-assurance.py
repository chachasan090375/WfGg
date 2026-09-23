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
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--project-id",required=True);ap.add_argument("--application-version",default="0")
    ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--runtime-script",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True);a=ap.parse_args()
    policy=load(a.policy)
    if policy.get("schema")!=POLICY_SCHEMA or policy.get("mandatory_for_all_projects") is not True:
        raise SystemExit("EMBEDDED_ASSURANCE_POLICY_INVALID")
    root=a.output_dir.resolve();root.mkdir(parents=True,exist_ok=True)
    runtime=root/"project-assurance-event.py";shutil.copy2(a.runtime_script,runtime);runtime.chmod(0o755)
    for role in ("guardian","sentinel"):
        (root/"outbox"/role).mkdir(parents=True,exist_ok=True)
        (root/"delivered"/role).mkdir(parents=True,exist_ok=True)
    manifest={
      "schema":MANIFEST_SCHEMA,"project_id":a.project_id,"application_version":a.application_version,
      "created_at":now(),"mandatory":True,
      "guardian_local":{"enabled":True,"mode":"LOCAL_EVENT_PROBE","direct_mutation":False},
      "sentinel_local":{"enabled":True,"mode":"LOCAL_EVENT_PROBE","direct_mutation":False},
      "relay":{"mode":"SERVER_SIDE_ONLY","client_direct_to_central":False,
               "private_key_embedded_in_client":False,"incremental":True},
      "privacy":{"raw_user_content":False,"raw_prompt":False,"raw_message":False,
                 "credentials":False,"secrets":False},
      "paths":{"runtime":str(runtime),"guardian_outbox":str(root/"outbox/guardian"),
               "sentinel_outbox":str(root/"outbox/sentinel")},
      "central_orchestrator_owns_remediation":True,"automatic_external_spend_eur":0
    }
    manifest["bundle_digest"]="sha256:"+hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    save(root/"embedded-assurance.json",manifest)
    print("CHACHA_DEV_PROJECT_EMBEDDED_ASSURANCE=PASS")
    print("PROJECT_ID="+a.project_id);print("GUARDIAN_LOCAL=ENABLED");print("SENTINEL_LOCAL=ENABLED")
    print("RAW_USER_CONTENT=NO");print("CLIENT_CENTRAL_SECRET=NO");print("DIRECT_MUTATION=NO");return 0
if __name__=="__main__":raise SystemExit(main())
