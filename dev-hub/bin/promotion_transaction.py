#!/usr/bin/env python3
from __future__ import annotations
import fcntl,hashlib,json,os,secrets,tempfile,time,uuid
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Iterator

SCHEMA='chacha.dev/platform-promotion-transaction/v1'
LEASE_SCHEMA='chacha.dev/platform-promotion-lease/v1'
LEDGER_SCHEMA='chacha.dev/platform-promotion-ledger-event/v1'
DEFAULT_TTL_SECONDS=1800


def iso(epoch:float|None=None)->str:
    d=datetime.fromtimestamp(time.time() if epoch is None else epoch,timezone.utc)
    return d.isoformat().replace('+00:00','Z')

def load_json(path:Path,default=None):
    if not path.is_file():return {} if default is None else default
    x=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT:'+str(path))
    return x

def atomic_json(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(obj,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
        dfd=os.open(str(path.parent),os.O_DIRECTORY)
        try:os.fsync(dfd)
        finally:os.close(dfd)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def write_once_json(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    data=(json.dumps(obj,indent=2,ensure_ascii=False)+'\n').encode()
    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o640)
    except FileExistsError as exc:raise ValueError('IMMUTABLE_RECEIPT_ALREADY_EXISTS:'+str(path)) from exc
    try:
        with os.fdopen(fd,'wb',closefd=True) as f:f.write(data);f.flush();os.fsync(f.fileno())
        dfd=os.open(str(path.parent),os.O_DIRECTORY)
        try:os.fsync(dfd)
        finally:os.close(dfd)
    except Exception:
        try:path.unlink(missing_ok=True)
        except Exception:pass
        raise

def runtime_paths(runtime_root:Path)->dict[str,Path]:
    root=runtime_root.resolve()/'platform-promotion'
    return {'root':root,'guard':root/'transaction.lock','lease':root/'lease.json','ledger':root/'ledger.jsonl'}

@contextmanager
def locked(runtime_root:Path)->Iterator[dict[str,Path]]:
    paths=runtime_paths(runtime_root);paths['root'].mkdir(parents=True,exist_ok=True)
    fd=open(paths['guard'],'a+',encoding='utf-8')
    fcntl.flock(fd,fcntl.LOCK_EX)
    try:yield paths
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN);fd.close()

def _append(paths:dict[str,Path],event:dict[str,Any])->None:
    row={'schema':LEDGER_SCHEMA,'recorded_at':iso(),**event,'automatic_external_spend_eur':0}
    data=(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    fd=os.open(paths['ledger'],os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o640)
    try:os.write(fd,data);os.fsync(fd)
    finally:os.close(fd)

def _expired(x:dict[str,Any],now:float|None=None)->bool:
    now=time.time() if now is None else now
    try:return float(x.get('expires_epoch') or 0)<=now
    except Exception:return True

def public_status(runtime_root:Path)->dict[str,Any]:
    with locked(runtime_root) as paths:
        x=load_json(paths['lease'],{})
        if not x:return {'schema':LEASE_SCHEMA,'status':'NONE','automatic_external_spend_eur':0}
        out={k:v for k,v in x.items() if k!='token_sha256'}
        if out.get('status')=='ACTIVE' and _expired(out):out['status']='EXPIRED'
        out['automatic_external_spend_eur']=0
        return out

def acquire(runtime_root:Path,promotion_id:str,owner:str,candidate_revision:str,ttl_seconds:int=DEFAULT_TTL_SECONDS)->dict[str,Any]:
    if not promotion_id.strip() or not owner.strip():raise ValueError('PROMOTION_ID_AND_OWNER_REQUIRED')
    if len(candidate_revision)!=40:raise ValueError('EXACT_CANDIDATE_REVISION_REQUIRED')
    ttl=max(60,min(int(ttl_seconds),7200));now=time.time();token=secrets.token_urlsafe(32);token_hash=hashlib.sha256(token.encode()).hexdigest()
    with locked(runtime_root) as paths:
        old=load_json(paths['lease'],{})
        if old.get('status')=='ACTIVE' and not _expired(old,now):
            raise ValueError('PROMOTION_LEASE_HELD:'+str(old.get('promotion_id'))+':'+str(old.get('owner')))
        lease_id='promotion-'+uuid.uuid4().hex
        x={'schema':LEASE_SCHEMA,'status':'ACTIVE','lease_id':lease_id,'promotion_id':promotion_id,'owner':owner,
           'candidate_revision':candidate_revision,'acquired_at':iso(now),'renewed_at':iso(now),'expires_at':iso(now+ttl),
           'expires_epoch':now+ttl,'ttl_seconds':ttl,'token_sha256':token_hash,'recovered_from_lease_id':None,
           'root_lease_id':lease_id,'recovery_generation':0,'automatic_external_spend_eur':0}
        atomic_json(paths['lease'],x);_append(paths,{'event':'LEASE_ACQUIRED','lease_id':lease_id,'promotion_id':promotion_id,'owner':owner,'candidate_revision':candidate_revision})
    return {'schema':SCHEMA,'status':'PASS','phase':'LEASE_ACQUIRE','lease_id':lease_id,'promotion_id':promotion_id,'owner':owner,
            'candidate_revision':candidate_revision,'lease_token':token,'expires_at':x['expires_at'],'automatic_external_spend_eur':0}

def recover(runtime_root:Path,promotion_id:str,owner:str,candidate_revision:str,previous_lease_id:str,ttl_seconds:int=DEFAULT_TTL_SECONDS)->dict[str,Any]:
    ttl=max(60,min(int(ttl_seconds),7200));now=time.time();token=secrets.token_urlsafe(32);token_hash=hashlib.sha256(token.encode()).hexdigest()
    with locked(runtime_root) as paths:
        old=load_json(paths['lease'],{})
        if old.get('lease_id')!=previous_lease_id:raise ValueError('RECOVERY_PREVIOUS_LEASE_MISMATCH')
        if old.get('status')!='ACTIVE' or not _expired(old,now):raise ValueError('RECOVERY_REQUIRES_EXPIRED_ACTIVE_LEASE')
        if old.get('promotion_id')!=promotion_id or old.get('candidate_revision')!=candidate_revision:raise ValueError('RECOVERY_SCOPE_MISMATCH')
        if old.get('owner')!=owner:raise ValueError('RECOVERY_OWNER_MISMATCH')
        lease_id='promotion-'+uuid.uuid4().hex
        root_lease_id=str(old.get('root_lease_id') or old.get('lease_id') or previous_lease_id)
        recovery_generation=int(old.get('recovery_generation') or 0)+1
        x={'schema':LEASE_SCHEMA,'status':'ACTIVE','lease_id':lease_id,'promotion_id':promotion_id,'owner':owner,
           'candidate_revision':candidate_revision,'acquired_at':iso(now),'renewed_at':iso(now),'expires_at':iso(now+ttl),
           'expires_epoch':now+ttl,'ttl_seconds':ttl,'token_sha256':token_hash,'recovered_from_lease_id':previous_lease_id,
           'root_lease_id':root_lease_id,'recovery_generation':recovery_generation,'automatic_external_spend_eur':0}
        atomic_json(paths['lease'],x);_append(paths,{'event':'LEASE_RECOVERED','lease_id':lease_id,'previous_lease_id':previous_lease_id,
          'root_lease_id':root_lease_id,'recovery_generation':recovery_generation,'promotion_id':promotion_id,'owner':owner,'candidate_revision':candidate_revision})
    return {'schema':SCHEMA,'status':'PASS','phase':'LEASE_RECOVER','lease_id':lease_id,'promotion_id':promotion_id,'owner':owner,
            'candidate_revision':candidate_revision,'lease_token':token,'expires_at':x['expires_at'],'automatic_external_spend_eur':0}

def assert_owner(runtime_root:Path,lease_token:str,promotion_id:str,candidate_revision:str,phase:str,renew:bool=True)->dict[str,Any]:
    now=time.time();present=hashlib.sha256(lease_token.encode()).hexdigest()
    with locked(runtime_root) as paths:
        x=load_json(paths['lease'],{})
        if x.get('status')!='ACTIVE':raise ValueError('PROMOTION_LEASE_NOT_ACTIVE')
        if _expired(x,now):raise ValueError('PROMOTION_LEASE_EXPIRED')
        if x.get('promotion_id')!=promotion_id:raise ValueError('PROMOTION_LEASE_SCOPE_MISMATCH')
        if x.get('candidate_revision')!=candidate_revision:raise ValueError('PROMOTION_LEASE_REVISION_MISMATCH')
        if not secrets.compare_digest(str(x.get('token_sha256') or ''),present):raise ValueError('PROMOTION_LEASE_OWNER_MISMATCH')
        if renew:
            ttl=int(x.get('ttl_seconds') or DEFAULT_TTL_SECONDS);x['renewed_at']=iso(now);x['expires_at']=iso(now+ttl);x['expires_epoch']=now+ttl
            atomic_json(paths['lease'],x);_append(paths,{'event':'LEASE_ASSERTED','phase':phase,'lease_id':x.get('lease_id'),'promotion_id':promotion_id,
              'owner':x.get('owner'),'candidate_revision':candidate_revision})
        return {k:v for k,v in x.items() if k!='token_sha256'}

def release(runtime_root:Path,lease_token:str,promotion_id:str,candidate_revision:str,terminal_status:str)->dict[str,Any]:
    x=assert_owner(runtime_root,lease_token,promotion_id,candidate_revision,'LEASE_RELEASE',renew=False);now=time.time()
    with locked(runtime_root) as paths:
        cur=load_json(paths['lease'],{})
        if cur.get('lease_id')!=x.get('lease_id'):raise ValueError('PROMOTION_LEASE_CHANGED_DURING_RELEASE')
        cur.update({'status':terminal_status,'released_at':iso(now),'expires_at':iso(now),'expires_epoch':now})
        atomic_json(paths['lease'],cur);_append(paths,{'event':'LEASE_RELEASED','terminal_status':terminal_status,'lease_id':cur.get('lease_id'),
          'promotion_id':promotion_id,'owner':cur.get('owner'),'candidate_revision':candidate_revision})
    return {'schema':SCHEMA,'status':'PASS','phase':'LEASE_RELEASE','lease_id':cur.get('lease_id'),'terminal_status':terminal_status,
            'automatic_external_spend_eur':0}


def lease_lineage(runtime_root:Path,current_lease_id:str)->list[str]:
    """Return current lease followed by its recovered ancestors, newest to oldest."""
    with locked(runtime_root) as paths:
        parent:dict[str,str]={}
        if paths['ledger'].is_file():
            for raw in paths['ledger'].read_text(encoding='utf-8').splitlines():
                if not raw.strip():continue
                try:row=json.loads(raw)
                except Exception:continue
                if row.get('event')=='LEASE_RECOVERED' and row.get('lease_id') and row.get('previous_lease_id'):
                    parent[str(row['lease_id'])]=str(row['previous_lease_id'])
        chain=[];seen=set();cur=str(current_lease_id or '')
        while cur and cur not in seen:
            chain.append(cur);seen.add(cur);cur=parent.get(cur,'')
        return chain

def require_receipt_binding(runtime_root:Path,receipt:dict[str,Any],lease:dict[str,Any],candidate_revision:str,label:str)->None:
    bound_revision=receipt.get('candidate_revision')
    if bound_revision not in (None,'') and bound_revision!=candidate_revision:raise ValueError(label+'_REVISION_MISMATCH')
    if receipt.get('promotion_id')!=lease.get('promotion_id'):raise ValueError(label+'_PROMOTION_ID_MISMATCH')
    bound=str(receipt.get('promotion_lease_id') or '')
    if not bound:raise ValueError(label+'_LEASE_BINDING_MISSING')
    if bound not in lease_lineage(runtime_root,str(lease.get('lease_id') or '')):
        raise ValueError(label+'_LEASE_LINEAGE_MISMATCH')

def bind_receipt(lease:dict[str,Any],payload:dict[str,Any])->dict[str,Any]:
    return {**payload,'promotion_lease_id':lease.get('lease_id'),'promotion_lease_root_id':lease.get('root_lease_id') or lease.get('lease_id'),
            'promotion_lease_recovery_generation':int(lease.get('recovery_generation') or 0),'promotion_id':lease.get('promotion_id'),
            'promotion_owner':lease.get('owner'),'automatic_external_spend_eur':0}
