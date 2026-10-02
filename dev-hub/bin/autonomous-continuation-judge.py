#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def load(p): return json.loads(Path(p).read_text())
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--mission',required=True); ap.add_argument('--authorization',required=True); ap.add_argument('--stop',required=True); ap.add_argument('--output',required=True); a=ap.parse_args()
 m,z,s=load(a.mission),load(a.authorization),load(a.stop); verdict='CONTINUE'; reason='WITHIN_AUTHORIZED_ENVELOPE'
 if s.get('active') is not False: verdict,reason='BLOCK','EMERGENCY_STOP_ACTIVE'
 elif m.get('human_boundary') is True: verdict,reason='HUMAN_BOUNDARY','MISSION_HUMAN_BOUNDARY'
 elif m.get('status') not in ('ACTIVE',): verdict,reason='BLOCK','MISSION_NOT_ACTIVE'
 elif m.get('automatic_external_spend_eur',0)>z.get('max_external_spend_eur',0): verdict,reason='HUMAN_BOUNDARY','BUDGET_ENVELOPE_EXCEEDED'
 out={'schema':'chacha.dev/autonomous-continuation-verdict/v1','mission_id':m.get('mission_id'),'verdict':verdict,'reason':reason,'judge_executes_tasks':False,'judge_can_expand_authority':False}
 Path(a.output).write_text(json.dumps(out,indent=2)+'\n'); print('CONTINUATION_JUDGE='+verdict); return 0 if verdict=='CONTINUE' else 20
if __name__=='__main__': raise SystemExit(main())
