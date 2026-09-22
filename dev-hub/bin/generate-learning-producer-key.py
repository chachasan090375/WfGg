#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,hashlib,json,os,subprocess
from pathlib import Path

def pub(private:Path)->str:
    p=subprocess.run(["/usr/bin/openssl","pkey","-in",str(private),"-pubout","-outform","DER"],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
    if p.returncode!=0:raise SystemExit("LEARNING_PRODUCER_PUBLIC_KEY_DERIVATION_FAILED")
    return base64.b64encode(p.stdout).decode()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--private-key",type=Path,required=True)
    ap.add_argument("--project-id",required=True);ap.add_argument("--deployment-id",required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    a.private_key.parent.mkdir(parents=True,exist_ok=True)
    if not a.private_key.exists():
        p=subprocess.run(["/usr/bin/openssl","genpkey","-algorithm","Ed25519","-out",str(a.private_key)],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=15)
        if p.returncode!=0:raise SystemExit("LEARNING_PRODUCER_KEYGEN_FAILED")
        os.chmod(a.private_key,0o600)
    public=pub(a.private_key)
    key_id="producer-"+hashlib.sha256(public.encode()).hexdigest()[:16]
    out={"schema":"chacha.dev/learning-producer-enrollment/v1","key_id":key_id,"role":"PRODUCER",
         "public_key_spki_b64":public,"project_id":a.project_id,"deployment_id":a.deployment_id,
         "private_key_exported":False}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out,indent=2))
    print("CHACHA_DEV_LEARNING_PRODUCER_KEYGEN=PASS")
if __name__=="__main__":main()
