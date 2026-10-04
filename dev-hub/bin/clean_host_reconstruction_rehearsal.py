#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sqlite3,subprocess,tarfile,tempfile
from pathlib import Path
from typing import Any

def sha256(p:Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return 'sha256:'+h.hexdigest()

def safe_extract(tf:tarfile.TarFile,dst:Path)->int:
    dst=dst.resolve();members=tf.getmembers()
    for m in members:
        target=(dst/m.name).resolve()
        try:target.relative_to(dst)
        except ValueError:raise ValueError('TAR_PATH_ESCAPE:'+m.name)
        if m.issym() or m.islnk():
            raise ValueError('TAR_LINK_FORBIDDEN:'+m.name)
    tf.extractall(dst,members=members,filter='data')
    return len(members)

def sqlite_ok(p:Path)->bool:
    uri='file:'+str(p.resolve())+'?mode=ro'
    con=sqlite3.connect(uri,uri=True)
    try:return con.execute('pragma integrity_check').fetchone()[0]=='ok'
    finally:con.close()

def rehearse(capsule:Path)->dict[str,Any]:
    capsule=capsule.resolve();manifest=json.loads((capsule/'manifest.json').read_text())
    if manifest.get('secrets_included') is not False:raise ValueError('CAPSULE_SECRET_BOUNDARY_INVALID')
    checks=[]
    for rel,expected in (manifest.get('files') or {}).items():
        p=capsule/rel
        checks.append({'file':rel,'present':p.is_file(),'digest_match':p.is_file() and sha256(p)==expected})
    for row in manifest.get('runtime_databases') or []:
        rel=str(row.get('file') or '');p=capsule/rel
        checks.append({'file':rel,'present':p.is_file(),'digest_match':p.is_file() and sha256(p)==row.get('sha256')})
    if not checks or not all(c['present'] and c['digest_match'] for c in checks):raise ValueError('CAPSULE_DIGEST_VERIFICATION_FAILED')
    with tempfile.TemporaryDirectory(prefix='chacha-clean-host-') as td:
        root=Path(td);repo=root/'repo';release=root/'release'
        bundle=capsule/'WfGg.bundle'
        verify_repo=root/'verify-repo';verify_repo.mkdir()
        init=subprocess.run(['git','init','-q',str(verify_repo)],text=True,capture_output=True)
        if init.returncode!=0:raise ValueError('GIT_VERIFY_REPO_INIT_FAILED:'+init.stderr[-500:])
        bv=subprocess.run(['git','-C',str(verify_repo),'bundle','verify',str(bundle)],text=True,capture_output=True)
        if bv.returncode!=0:raise ValueError('GIT_BUNDLE_VERIFY_FAILED:'+bv.stderr[-500:])
        branch=str(manifest.get('git_bundle_branch') or 'chacha-active')
        clone=subprocess.run(['git','clone','-q','-b',branch,str(bundle),str(repo)],text=True,capture_output=True)
        if clone.returncode!=0:raise ValueError('GIT_BUNDLE_CLONE_FAILED:'+clone.stderr[-500:])
        head=str(manifest.get('git_head') or '')
        cat=subprocess.run(['git','-C',str(repo),'cat-file','-e',head+'^{commit}'],text=True,capture_output=True)
        if cat.returncode!=0:raise ValueError('GIT_HEAD_NOT_RECONSTRUCTED:'+head)
        fsck=subprocess.run(['git','-C',str(repo),'fsck','--no-dangling'],text=True,capture_output=True)
        if fsck.returncode!=0:raise ValueError('GIT_FSCK_FAILED:'+fsck.stderr[-500:])
        release.mkdir()
        with tarfile.open(capsule/'active-release.tar.gz','r:gz') as tf:member_count=safe_extract(tf,release)
        revision_files=list(release.rglob('.revision'))
        revision_values=[p.read_text(errors='replace').strip() for p in revision_files]
        prod=str(manifest.get('production_revision') or '')
        release_revision_verified=(not revision_files) or prod in revision_values
        if not release_revision_verified:raise ValueError('RELEASE_REVISION_MISMATCH')
        db_results=[]
        for row in manifest.get('runtime_databases') or []:
            p=capsule/str(row['file']);ok=sqlite_ok(p);db_results.append({'file':row['file'],'integrity_check':'ok' if ok else 'FAILED'})
        if not all(x['integrity_check']=='ok' for x in db_results):raise ValueError('SQLITE_INTEGRITY_FAILED')
        repo_files=sum(1 for p in repo.rglob('*') if p.is_file())
        release_files=sum(1 for p in release.rglob('*') if p.is_file())
    return {
      'schema':'chacha.dev/clean-host-reconstruction-rehearsal/v1','status':'PASS','mode':'ISOLATED_NON_MUTATING',
      'capsule':str(capsule),'production_revision':manifest.get('production_revision'),'git_head':manifest.get('git_head'),
      'manifest_hash_checks':checks,'git_bundle_verify':'PASS','git_clone_from_bundle':'PASS','git_bundle_branch':str(manifest.get('git_bundle_branch') or 'chacha-active'),'git_head_reconstructed':'PASS','git_fsck':'PASS',
      'release_archive_safe_extract':'PASS','release_archive_member_count':member_count,'release_revision_verified':release_revision_verified,
      'sqlite_integrity':db_results,'repo_file_count':repo_files,'release_file_count':release_files,
      'systemd_started':False,'current_link_modified':False,'network_dependency_after_capsule_copy':False,
      'automatic_external_spend_eur':0,'production_authority':False
    }

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--capsule',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    try:out=rehearse(a.capsule);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n');print('CHACHA_DEV_CLEAN_HOST_RECONSTRUCTION_REHEARSAL=PASS');return 0
    except Exception as e:
        out={'schema':'chacha.dev/clean-host-reconstruction-rehearsal/v1','status':'BLOCK','reason':str(e),'automatic_external_spend_eur':0,'production_authority':False};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out));return 20
if __name__=='__main__':raise SystemExit(main())
