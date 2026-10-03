#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,time
from pathlib import Path
SERVICES={'chacha-dev-guardian','chacha-dev-sentinel','chacha-dev-assurance-exchange','chacha-dev-learning-relay'}
def load(p):return json.loads(Path(p).read_text())
def mapfiles(x):return {str(r['database']):str(r['sha256']) for r in x.get('files') or []}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--first',type=Path,required=True);ap.add_argument('--second',type=Path,required=True);ap.add_argument('--max-age-seconds',type=int,default=300);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();x,y=load(a.first),load(a.second);m1,m2=mapfiles(x),mapfiles(y);missing=sorted((SERVICES-set(m1)) | (SERVICES-set(m2)));same={s:(m1.get(s)==m2.get(s) and m1.get(s) is not None) for s in sorted(SERVICES)};age=max(0,int(time.time()-a.second.stat().st_mtime));block=[]
 if missing:block.append('EXPORT_SERVICE_MISSING')
 if not all(same.values()):block.append('DOUBLE_EXPORT_DIGEST_NOT_CONVERGED')
 if age>a.max_age_seconds:block.append('SECOND_EXPORT_TOO_OLD')
 out={'schema':'chacha.dev/sovereign-state-export-convergence/v1','status':'PASS' if not block else 'HOLD','same_digests':same,'second_export_age_seconds':age,'max_age_seconds':a.max_age_seconds,'blockers':block,'production_mutation':False,'automatic_external_spend_eur':0};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_SOVEREIGN_EXPORT_CONVERGENCE='+out['status']);return 0 if not block else 20
if __name__=='__main__':raise SystemExit(main())
