#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, tempfile
from pathlib import Path

def load(p): return json.loads(Path(p).read_text())
def digest_bytes(b): return 'sha256:'+hashlib.sha256(b).hexdigest()
def canonical_bytes(x): return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--reconciliation',required=True); ap.add_argument('--current',required=True); ap.add_argument('--desired',required=True); ap.add_argument('--stop',required=True); ap.add_argument('--receipt',required=True); a=ap.parse_args()
 r=load(a.reconciliation); stop=load(a.stop); cur=Path(a.current); desired=load(a.desired)
 if stop.get('active') is not False: raise SystemExit('BLOCK:STOP_ACTIVE')
 if r.get('status')!='READY' or r.get('apply') is not False or r.get('single_writer_required') is not True: raise SystemExit('BLOCK:RECONCILIATION_NOT_READY')
 old=cur.read_bytes(); old_digest=digest_bytes(old)
 if old_digest!=r.get('old_digest'): raise SystemExit('BLOCK:OLD_DIGEST_MISMATCH')
 new=canonical_bytes(desired); new_digest=digest_bytes(new)
 if new_digest!=r.get('new_digest'): raise SystemExit('BLOCK:NEW_DIGEST_MISMATCH')
 backup=cur.with_suffix(cur.suffix+'.rollback'); backup.write_bytes(old)
 fd,tmp=tempfile.mkstemp(prefix=cur.name+'.',dir=str(cur.parent)); os.close(fd)
 try:
  Path(tmp).write_bytes(new); os.replace(tmp,cur)
  actual=digest_bytes(cur.read_bytes())
  if actual!=new_digest:
   cur.write_bytes(old); raise SystemExit('ROLLBACK:POST_WRITE_DIGEST_MISMATCH')
 except BaseException:
  if Path(tmp).exists(): Path(tmp).unlink()
  raise
 receipt={'schema':'chacha.dev/guardian-contract-registry-writer-receipt/v1','status':'APPLIED_VERIFIED','old_digest':old_digest,'new_digest':new_digest,'rollback':str(backup),'automatic_external_spend_eur':0}
 Path(a.receipt).write_text(json.dumps(receipt,indent=2)+'\n'); print('GUARDIAN_CONTRACT_REGISTRY_WRITER=APPLIED_VERIFIED'); return 0
if __name__=='__main__': raise SystemExit(main())
