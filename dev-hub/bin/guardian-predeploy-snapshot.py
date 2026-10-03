#!/usr/bin/env python3
import argparse,hashlib,json,os,subprocess
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--database-id',required=True); p.add_argument('--output-dir',required=True); a=p.parse_args()
out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
tables=['role_contracts','expected_components','action_leases','remediation_directives','guardian_alerts']
def run(sql):
 r=subprocess.run(['npx','--yes','wrangler@4.45.0','d1','execute',a.database_id,'--remote','--json','--command',sql],capture_output=True,text=True,check=True)
 return json.loads(r.stdout)
art={}
for t in tables:
 data=run(f'SELECT * FROM {t};'); f=out/(t+'.json'); f.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n'); art[f.name]=hashlib.sha256(f.read_bytes()).hexdigest()
# Full D1 export is the authoritative rollback payload; snapshots above provide reviewable scoped evidence.
rb=out/'rollback.sql'
subprocess.run(['npx','--yes','wrangler@4.45.0','d1','export',a.database_id,'--remote','--output',str(rb)],check=True)
art[rb.name]=hashlib.sha256(rb.read_bytes()).hexdigest()
dep=out/'worker-deployments.json'; art[dep.name]=hashlib.sha256(dep.read_bytes()).hexdigest()
manifest={'schema':'chacha.dev/guardian-predeploy-snapshot/v1','database_id':a.database_id,'artifacts':art,'automatic_external_spend_eur':0}
(out/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
print('CHACHA_DEV_GUARDIAN_D1_SNAPSHOT_DIGESTS=PASS')
