#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,io,json,os,shutil,subprocess,tarfile,tempfile,time
from pathlib import Path,PurePosixPath
from typing import Any

SCHEMA='chacha.dev/exact-git-release-verification/v1'
MATERIALIZATION_SCHEMA='chacha.dev/exact-git-release-materialization/v1'
ENVELOPE_FILES={'.revision','.tree','.release-preparation.json'}

def atomic_json(path:Path,obj:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(obj,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def git(repo:Path,*args:str,binary:bool=False):
    p=subprocess.run(['/usr/bin/git','-C',str(repo),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    if p.returncode!=0:raise ValueError('GIT_COMMAND_FAILED:'+(' '.join(args))+':'+p.stderr.decode(errors='replace')[-300:])
    return p.stdout if binary else p.stdout.decode().strip()

def git_tree(repo:Path,revision:str)->str:
    return str(git(repo,'rev-parse',revision+'^{tree}'))

def tracked_entries(repo:Path,revision:str)->list[tuple[str,str,str,str]]:
    raw=git(repo,'ls-tree','-r','-z','--full-tree',revision,binary=True)
    out=[]
    for rec in raw.split(b'\0'):
        if not rec:continue
        head,path=rec.split(b'\t',1);mode,kind,oid=head.decode().split(' ',2)
        out.append((mode,kind,oid,path.decode('utf-8','surrogateescape')))
    return out

def blob_oid(data:bytes)->str:
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def file_payload(path:Path,mode:str)->bytes:
    if mode=='120000':
        if not path.is_symlink():raise ValueError('TRACKED_SYMLINK_TYPE_MISMATCH:'+str(path))
        return os.readlink(path).encode('utf-8','surrogateescape')
    if path.is_symlink() or not path.is_file():raise ValueError('TRACKED_FILE_TYPE_MISMATCH:'+str(path))
    return path.read_bytes()

def verify_release(release_root:Path,source_git_root:Path,candidate_revision:str,candidate_tree:str)->dict[str,Any]:
    release_root=release_root.resolve();source_git_root=source_git_root.resolve()
    reasons=[];missing=[];mismatched=[];unsupported=[];metadata_collisions=[]
    if not release_root.is_dir():reasons.append('RELEASE_ROOT_MISSING')
    if not source_git_root.is_dir():reasons.append('SOURCE_GIT_ROOT_MISSING')
    if reasons:return {'schema':SCHEMA,'status':'BLOCK','reason_codes':reasons,'automatic_external_spend_eur':0}
    actual_tree=git_tree(source_git_root,candidate_revision)
    if actual_tree!=candidate_tree:reasons.append('CANDIDATE_TREE_MISMATCH')
    entries=tracked_entries(source_git_root,candidate_revision);tracked=set();checked=0
    for mode,kind,oid,rel in entries:
        tracked.add(rel)
        if rel in ENVELOPE_FILES:metadata_collisions.append(rel);continue
        if kind!='blob':unsupported.append({'path':rel,'kind':kind,'mode':mode});continue
        target=release_root/rel
        if not target.exists() and not target.is_symlink():missing.append(rel);continue
        try:actual=blob_oid(file_payload(target,mode))
        except ValueError as e:mismatched.append({'path':rel,'expected':oid,'actual':'TYPE_MISMATCH','detail':str(e)});continue
        checked+=1
        if actual!=oid:mismatched.append({'path':rel,'expected':oid,'actual':actual})
    extras=[]
    for x in release_root.rglob('*'):
        if not (x.is_file() or x.is_symlink()):continue
        rel=x.relative_to(release_root).as_posix()
        if rel not in tracked and rel not in ENVELOPE_FILES:extras.append(rel)
    rev_marker=(release_root/'.revision').read_text().strip() if (release_root/'.revision').is_file() else ''
    tree_marker=(release_root/'.tree').read_text().strip() if (release_root/'.tree').is_file() else ''
    if rev_marker!=candidate_revision:reasons.append('REVISION_MARKER_MISMATCH')
    if tree_marker!=candidate_tree:reasons.append('TREE_MARKER_MISMATCH')
    if missing:reasons.append('TRACKED_BLOB_MISSING')
    if mismatched:reasons.append('TRACKED_BLOB_MISMATCH')
    if extras:reasons.append('UNTRACKED_RELEASE_PAYLOAD_FORBIDDEN')
    if unsupported:reasons.append('UNSUPPORTED_GIT_ENTRY_TYPE')
    if metadata_collisions:reasons.append('RELEASE_ENVELOPE_PATH_TRACKED_IN_GIT')
    manifest=sorted((rel,oid) for mode,kind,oid,rel in entries if kind=='blob')
    md=hashlib.sha256(json.dumps(manifest,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    return {'schema':SCHEMA,'status':'PASS' if not reasons else 'BLOCK','candidate_revision':candidate_revision,
      'candidate_tree':candidate_tree,'git_tree':actual_tree,'source_git_root':str(source_git_root),'release_root':str(release_root),
      'checked_blobs':checked,'tracked_blob_count':sum(1 for _,k,_,_ in entries if k=='blob'),'missing_count':len(missing),
      'mismatch_count':len(mismatched),'extra_payload_count':len(extras),'unsupported_entry_count':len(unsupported),
      'metadata_collision_count':len(metadata_collisions),'manifest_digest':'sha256:'+md,'reason_codes':reasons,
      'missing_sample':missing[:20],'mismatch_sample':mismatched[:20],'extra_payload_sample':extras[:20],
      'unsupported_sample':unsupported[:20],'metadata_collision_sample':metadata_collisions[:20],'automatic_external_spend_eur':0}

def safe_extract_tar(raw:bytes,target:Path)->None:
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as tf:
        for member in tf.getmembers():
            q=PurePosixPath(member.name)
            if q.is_absolute() or '..' in q.parts:raise ValueError('UNSAFE_GIT_ARCHIVE_PATH:'+member.name)
        tf.extractall(target)

def materialize(repo:Path,revision:str,release_root:Path,preparation:Path,receipt:Path)->dict[str,Any]:
    repo=repo.resolve();release_root=release_root.absolute();preparation=preparation.resolve();receipt=receipt.absolute()
    if release_root.exists():raise ValueError('RELEASE_ROOT_ALREADY_EXISTS')
    if receipt.exists():raise ValueError('MATERIALIZATION_RECEIPT_ALREADY_EXISTS')
    tree=git_tree(repo,revision);meta=json.loads(preparation.read_text(encoding='utf-8'))
    if not isinstance(meta,dict):raise ValueError('PREPARATION_JSON_ROOT_NOT_OBJECT')
    if meta.get('candidate_revision') not in (None,revision):raise ValueError('PREPARATION_REVISION_MISMATCH')
    if meta.get('candidate_tree') not in (None,tree):raise ValueError('PREPARATION_TREE_MISMATCH')
    release_root.parent.mkdir(parents=True,exist_ok=True)
    stage=release_root.parent/('.staging-'+release_root.name+'-'+os.urandom(4).hex())
    stage.mkdir()
    try:
        raw=git(repo,'archive','--format=tar',revision,binary=True);safe_extract_tar(raw,stage)
        meta.update({'schema':'chacha.dev/release-preparation/v1','candidate_revision':revision,'candidate_tree':tree,
          'source_git_root':str(repo),'materializer':'exact-git-release','tracked_git_payload_immutable':True,
          'materialized_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'automatic_external_spend_eur':0})
        (stage/'.revision').write_text(revision+'\n',encoding='utf-8');(stage/'.tree').write_text(tree+'\n',encoding='utf-8');atomic_json(stage/'.release-preparation.json',meta)
        verification=verify_release(stage,repo,revision,tree)
        if verification.get('status')!='PASS':raise ValueError('EXACT_GIT_MATERIALIZATION_FAILED:'+','.join(verification.get('reason_codes') or []))
        os.replace(stage,release_root)
        out={'schema':MATERIALIZATION_SCHEMA,'status':'PASS','candidate_revision':revision,'candidate_tree':tree,
          'release_root':str(release_root),'source_git_root':str(repo),'verification':verification,'automatic_external_spend_eur':0}
        atomic_json(receipt,out);return out
    except Exception:
        shutil.rmtree(stage,ignore_errors=True);raise

def main()->int:
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    m=sub.add_parser('materialize');m.add_argument('--repo-root',type=Path,required=True);m.add_argument('--revision',required=True);m.add_argument('--release-root',type=Path,required=True);m.add_argument('--preparation',type=Path,required=True);m.add_argument('--receipt',type=Path,required=True)
    v=sub.add_parser('verify');v.add_argument('--repo-root',type=Path,required=True);v.add_argument('--revision',required=True);v.add_argument('--tree',required=True);v.add_argument('--release-root',type=Path,required=True);v.add_argument('--receipt',type=Path)
    a=ap.parse_args()
    try:
        if a.cmd=='materialize':out=materialize(a.repo_root,a.revision,a.release_root,a.preparation,a.receipt)
        else:
            out=verify_release(a.release_root,a.repo_root,a.revision,a.tree)
            if a.receipt:atomic_json(a.receipt,out)
        print(json.dumps(out,ensure_ascii=False));return 0 if out.get('status')=='PASS' else 20
    except Exception as e:
        print(json.dumps({'schema':SCHEMA,'status':'BLOCK','reason':str(e),'automatic_external_spend_eur':0},ensure_ascii=False));return 20
if __name__=='__main__':raise SystemExit(main())
