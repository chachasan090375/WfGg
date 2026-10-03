from __future__ import annotations
import hashlib,json,os,re,tempfile,time,uuid
from pathlib import Path
from typing import Any,BinaryIO

class ArtifactError(RuntimeError):pass

def now_iso()->str:return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def safe_name(v:str)->str:
    name=Path(str(v or 'artifact.bin')).name
    name=re.sub(r'[^A-Za-z0-9._() -]+','_',name).strip(' .')[:180]
    return name or 'artifact.bin'
def atomic_json(p:Path,x:dict[str,Any]):
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');os.replace(tmp,p)

class ArtifactStore:
    def __init__(self,root:Path,max_upload_bytes:int=64*1024*1024):
        self.root=root.resolve();self.max_upload_bytes=int(max_upload_bytes);self.objects=self.root/'objects';self.meta=self.root/'metadata';self.objects.mkdir(parents=True,exist_ok=True);self.meta.mkdir(parents=True,exist_ok=True)
    def metadata_path(self,artifact_id:str)->Path:
        if not re.fullmatch(r'art-[0-9a-f]{32}',str(artifact_id or '')):raise ArtifactError('ARTIFACT_ID_INVALID')
        return self.meta/(artifact_id+'.json')
    def _load(self,artifact_id:str)->dict[str,Any]:
        p=self.metadata_path(artifact_id)
        if not p.is_file():raise ArtifactError('ARTIFACT_NOT_FOUND')
        x=json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(x,dict):raise ArtifactError('ARTIFACT_METADATA_INVALID')
        return x
    def authorize(self,artifact_id:str,owner_key:str,project_id:str|None=None)->dict[str,Any]:
        x=self._load(artifact_id)
        if str(x.get('owner_key') or '')!=str(owner_key):raise ArtifactError('ARTIFACT_OWNER_MISMATCH')
        if project_id is not None and str(x.get('project_id') or '')!=str(project_id):raise ArtifactError('ARTIFACT_PROJECT_MISMATCH')
        return x
    def ingest_stream(self,stream:BinaryIO,length:int,filename:str,mime_type:str,owner_key:str,project_id:str,origin:str='user-upload',parent_artifact:str|None=None)->dict[str,Any]:
        length=int(length)
        if length<=0:raise ArtifactError('ARTIFACT_EMPTY')
        if length>self.max_upload_bytes:raise ArtifactError('ARTIFACT_TOO_LARGE')
        h=hashlib.sha256();written=0
        self.root.mkdir(parents=True,exist_ok=True)
        fd,tmpname=tempfile.mkstemp(prefix='.artifact-',dir=str(self.root));os.close(fd);tmp=Path(tmpname)
        try:
            with tmp.open('wb') as out:
                while written<length:
                    chunk=stream.read(min(1024*1024,length-written))
                    if not chunk:break
                    written+=len(chunk)
                    if written>self.max_upload_bytes:raise ArtifactError('ARTIFACT_TOO_LARGE')
                    h.update(chunk);out.write(chunk)
            if written!=length:raise ArtifactError('ARTIFACT_LENGTH_MISMATCH')
            hexsha=h.hexdigest();obj=self.objects/hexsha[:2]/hexsha;obj.parent.mkdir(parents=True,exist_ok=True)
            if not obj.exists():os.replace(tmp,obj)
            else:tmp.unlink(missing_ok=True)
            aid='art-'+uuid.uuid4().hex
            meta={"schema":"chacha.dev/artifact/v1","artifact_id":aid,"filename":safe_name(filename),"mime_type":str(mime_type or 'application/octet-stream')[:160],"size":written,"sha256":'sha256:'+hexsha,"origin":origin,"owner_key":owner_key,"project_id":project_id,"created_at":now_iso(),"classification":"UNCLASSIFIED","security_state":"STORED_UNTRUSTED_NONEXECUTABLE" if origin=='user-upload' else "GENERATED_NONEXECUTABLE_UNLESS_SEPARATELY_AUTHORIZED","execution_allowed":False,"version":1,"parent_artifact":parent_artifact,"object_relpath":str(obj.relative_to(self.root)),"automatic_external_spend_eur":0}
            atomic_json(self.metadata_path(aid),meta);return meta
        finally:tmp.unlink(missing_ok=True)
    def ingest_bytes(self,data:bytes,**kw)->dict[str,Any]:
        import io
        return self.ingest_stream(io.BytesIO(data),len(data),**kw)
    def ingest_path(self,path:Path,filename:str|None,owner_key:str,project_id:str,origin:str='generated',mime_type:str='application/octet-stream',parent_artifact:str|None=None)->dict[str,Any]:
        path=path.resolve()
        with path.open('rb') as fh:return self.ingest_stream(fh,path.stat().st_size,filename or path.name,mime_type,owner_key,project_id,origin,parent_artifact)
    def content_path(self,artifact_id:str,owner_key:str,project_id:str|None=None)->Path:
        x=self.authorize(artifact_id,owner_key,project_id);p=(self.root/str(x['object_relpath'])).resolve()
        try:p.relative_to(self.objects.resolve())
        except ValueError:raise ArtifactError('ARTIFACT_OBJECT_PATH_INVALID')
        if not p.is_file():raise ArtifactError('ARTIFACT_OBJECT_MISSING')
        return p
    def list(self,owner_key:str,project_id:str|None=None,limit:int=100)->list[dict[str,Any]]:
        rows=[]
        for p in sorted(self.meta.glob('art-*.json'),key=lambda x:x.stat().st_mtime,reverse=True):
            try:x=json.loads(p.read_text())
            except Exception:continue
            if x.get('owner_key')!=owner_key:continue
            if project_id is not None and x.get('project_id')!=project_id:continue
            rows.append(x)
            if len(rows)>=max(1,min(500,int(limit))):break
        return rows
    def validate_refs(self,artifact_ids:list[str],owner_key:str,project_id:str)->list[dict[str,Any]]:
        seen=set();out=[]
        for aid in artifact_ids:
            aid=str(aid)
            if aid in seen:continue
            out.append(self.authorize(aid,owner_key,project_id));seen.add(aid)
        return out
