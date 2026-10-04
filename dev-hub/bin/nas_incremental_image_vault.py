#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,re,shlex,sqlite3,subprocess,tarfile,tempfile,time
from pathlib import Path

def now(): return time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
def iso(): return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def load(p): return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return 'sha256:'+h.hexdigest()
def run(a,timeout=900,stdin=None): return subprocess.run(a,input=stdin,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=isinstance(stdin,str) or stdin is None,check=False,timeout=timeout)
def ssh(host,cmd,timeout=900):
    p=run(['/usr/bin/ssh','-o','BatchMode=yes','-o','ConnectTimeout=12',host,cmd],timeout)
    if p.returncode: raise RuntimeError('SSH_FAILED:'+str(p.stderr)[-500:])
    return str(p.stdout)
def active_release(): return str(Path('/opt/chacha-dev/platform/current').resolve())
def active_revision():
    p=Path('/opt/chacha-dev/platform/current/.revision')
    return p.read_text().strip() if p.is_file() else Path(active_release()).name.rsplit('-',1)[-1]
def sqlite_backup(src:Path,dst:Path):
    dst.parent.mkdir(parents=True,exist_ok=True)
    s=sqlite3.connect(f'file:{src}?mode=ro',uri=True); d=sqlite3.connect(dst)
    with d: s.backup(d)
    d.execute('pragma integrity_check').fetchone(); d.close(); s.close()
def build_capsule(repo:Path,policy:dict,tmp:Path)->dict:
    c=tmp/'core-capsule'; c.mkdir(parents=True)
    bundle=c/'WfGg.bundle'; p=run(['git','-C',str(repo),'bundle','create',str(bundle),'--all'],900)
    if p.returncode: raise RuntimeError('GIT_BUNDLE_FAILED:'+str(p.stderr)[-500:])
    rel=Path(active_release()); tar=c/'active-release.tar.gz'
    with tarfile.open(tar,'w:gz') as tf: tf.add(rel,arcname=rel.name,recursive=True)
    dbs=[]
    for raw in policy['core_capsule']['runtime_databases']:
        src=Path(raw)
        if not src.is_file(): continue
        dst=c/'runtime-db'/src.name
        sqlite_backup(src,dst); dbs.append({'source':raw,'file':str(dst.relative_to(c)),'sha256':sha(dst)})
    files={'WfGg.bundle':sha(bundle),'active-release.tar.gz':sha(tar)}
    manifest={'schema':'chacha.dev/core-capsule-manifest/v1','created_at':iso(),'production_revision':active_revision(),'active_release':str(rel),'git_head':run(['git','-C',str(repo),'rev-parse','HEAD']).stdout.strip(),'files':files,'runtime_databases':dbs,'secrets_included':False}
    (c/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    manifest['manifest_sha256']=sha(c/'manifest.json')
    return manifest
def publish_capsule(host:str,source_root:str,capsule:Path,relpath:str):
    target=source_root.rstrip('/')+'/'+relpath.strip('/')
    tmp=target+'.incoming'
    ssh(host,f'rm -rf {shlex.quote(tmp)} && mkdir -p {shlex.quote(tmp)}',120)
    p=run(['/usr/bin/rsync','-a','--delete',str(capsule)+'/ ',],10) if False else None
    proc=run(['/usr/bin/rsync','-a','--delete',str(capsule)+'/',host+':'+tmp+'/'],900)
    if proc.returncode: raise RuntimeError('CAPSULE_RSYNC_FAILED:'+str(proc.stderr)[-500:])
    ssh(host,f'rm -rf {shlex.quote(target+".previous")} && if [ -e {shlex.quote(target)} ]; then mv {shlex.quote(target)} {shlex.quote(target+".previous")}; fi; mv {shlex.quote(tmp)} {shlex.quote(target)}',120)
def snapshot(host:str,source:str,vault:str,stamp:str)->dict:
    images=vault.rstrip('/')+'/images'; manifests=vault.rstrip('/')+'/manifests'; final=images+'/'+stamp; temp=final+'.incoming'
    ssh(host,f'mkdir -p {shlex.quote(images)} {shlex.quote(manifests)}; test ! -e {shlex.quote(final)}; rm -rf {shlex.quote(temp)}; mkdir -p {shlex.quote(temp)}',120)
    prev=ssh(host,f"ls -1 {shlex.quote(images)} 2>/dev/null | grep -v '[.]incoming$' | sort | tail -1",60).strip()
    link='' if not prev else ' --link-dest='+shlex.quote(images+'/'+prev)
    cmd=f'rsync -aH --numeric-ids{link} {shlex.quote(source.rstrip("/")+"/")} {shlex.quote(temp+"/")}'
    ssh(host,cmd,3600)
    diff=ssh(host,f'rsync -aHn --delete --itemize-changes --numeric-ids {shlex.quote(source.rstrip("/")+"/")} {shlex.quote(temp+"/")}',3600)
    if diff.strip(): raise RuntimeError('POST_COPY_DIVERGENCE:'+diff[:500])
    stats=ssh(host,f'printf "files="; find {shlex.quote(temp)} -type f | wc -l; printf "bytes="; du -sb {shlex.quote(temp)} | awk "{{print \\$1}}"',120)
    ssh(host,f'mv {shlex.quote(temp)} {shlex.quote(final)}; ln -sfn {shlex.quote(final)} {shlex.quote(vault.rstrip("/")+"/latest")}',120)
    vals=dict(x.split('=',1) for x in stats.strip().splitlines() if '=' in x)
    return {'image_id':stamp,'path':final,'previous_image':prev or None,'file_count':int(vals.get('files','0')),'logical_bytes':int(vals.get('bytes','0')),'post_copy_diff_empty':True}

def restore_probe(host:str,image_path:str,tmp:Path)->dict:
    probe=tmp/'restore-probe'; probe.mkdir(parents=True,exist_ok=True)
    base=image_path.rstrip('/')+'/backups/core-capsule/current'
    for rel in ('manifest.json','WfGg.bundle','runtime-db/guardian.db'):
        src=host+':'+base+'/'+rel
        dst=probe/Path(rel).name
        proc=run(['/usr/bin/rsync','-a',src,str(dst)],900)
        if proc.returncode: raise RuntimeError('RESTORE_PROBE_RSYNC_FAILED:'+rel+':'+str(proc.stderr)[-300:])
    manifest=json.loads((probe/'manifest.json').read_text())
    if manifest.get('production_revision')!=active_revision(): raise RuntimeError('RESTORE_PROBE_REVISION_MISMATCH')
    gb=run(['git','bundle','verify',str(probe/'WfGg.bundle')],120)
    if gb.returncode: raise RuntimeError('RESTORE_PROBE_GIT_BUNDLE_INVALID:'+str(gb.stderr)[-300:])
    db=sqlite3.connect(f"file:{probe/'guardian.db'}?mode=ro",uri=True)
    integrity=db.execute('pragma integrity_check').fetchone()[0]; db.close()
    if integrity!='ok': raise RuntimeError('RESTORE_PROBE_SQLITE_INVALID')
    return {'status':'PASS','git_bundle_verify':'PASS','sqlite_integrity':'ok','production_revision':manifest.get('production_revision')}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--repo-root',type=Path,required=True);ap.add_argument('--mode',choices=['plan','snapshot'],default='plan');ap.add_argument('--dirty-marker',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    pol=load(a.policy); host=pol['nas_host']; stamp=now(); result={'schema':'chacha.dev/nas-incremental-image-vault-receipt/v1','status':'PLAN','observed_at':iso(),'source_root':pol['source_root'],'vault_root':pol['vault_root'],'production_revision':active_revision(),'automatic_external_spend_eur':0}
    if a.mode=='snapshot':
        marker={}
        if a.dirty_marker and a.dirty_marker.is_file():
            try: marker=json.loads(a.dirty_marker.read_text())
            except Exception: marker={'status':'DIRTY','reason':'UNPARSEABLE_MARKER'}
        prior={}
        if a.output.is_file():
            try: prior=json.loads(a.output.read_text())
            except Exception: prior={}
        marker_revision=str(marker.get('production_revision') or '')
        if marker and marker_revision and marker_revision==active_revision() and str(prior.get('production_revision') or '')==active_revision() and prior.get('status')=='RESTORE_VERIFIED' and not marker.get('force'):
            result.update({'status':'NO_CHANGE','trigger':marker,'snapshot_created':False,'production_activation_authorized':False})
        else:
            with tempfile.TemporaryDirectory(prefix='chacha-core-capsule-') as td:
                cap=build_capsule(a.repo_root,pol,Path(td)); publish_capsule(host,pol['source_root'],Path(td)/'core-capsule',pol['core_capsule']['source_path']); img=snapshot(host,pol['source_root'],pol['vault_root'],stamp); probe=restore_probe(host,img['path'],Path(td))
            result.update({'status':'RESTORE_VERIFIED','trigger':marker or {'reason':'MANUAL'},'core_capsule':cap,'image':img,'restore_probe':probe,'snapshot_created':True,'production_activation_authorized':False})
        if a.dirty_marker and a.dirty_marker.exists() and result['status'] in {'RESTORE_VERIFIED','NO_CHANGE'}:
            a.dirty_marker.unlink()
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2)+'\n')
    print('CHACHA_DEV_NAS_INCREMENTAL_IMAGE_VAULT='+result['status']); print('PRODUCTION_REVISION='+result['production_revision']); print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
if __name__=='__main__':main()
