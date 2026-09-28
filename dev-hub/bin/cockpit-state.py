#!/usr/bin/env python3
import datetime,json,os,subprocess,time,urllib.request
from pathlib import Path

OUT=Path('/opt/chacha-dev/runtime/live-ui/current/ui/cockpit.json')
CURRENT=Path('/opt/chacha-dev/platform/current')
PROGRESS=Path('/opt/chacha-dev/runtime/progress/progress.json')
STOP=Path('/opt/chacha-dev/runtime/control/emergency-stop.json')
OP=Path('/opt/chacha-dev/runtime/cockpit/current-operation.json')
GAPS=Path('/opt/chacha-dev/runtime/cockpit/autonomy-gaps.json')
SOURCE_GAPS=Path('/opt/chacha-dev/platform/current/dev-hub/config/autonomy-gap-roadmap.v1.json')

def iso(): return datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
def load(path,default=None):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return {} if default is None else default
def text(path,default=''):
    try:return path.read_text(encoding='utf-8').strip()
    except Exception:return default
def unit(name):
    try:
        r=subprocess.run(['/usr/bin/systemctl','is-active',name],capture_output=True,text=True,timeout=3)
        return r.returncode==0 and r.stdout.strip()=='active'
    except Exception:return False
def health(url):
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'ChaCha-DEV-Cockpit/1.0'})
        with urllib.request.urlopen(req,timeout=4) as r:x=json.loads(r.read().decode('utf-8','replace'))
        return 'PASS' if str(x.get('status') or '').lower() in {'ok','pass'} else 'WARN'
    except Exception:return 'UNAVAILABLE'
def production_version(rev,release):
    prep=load(release/'.release-preparation.json',{})
    if prep.get('version'):return str(prep['version'])
    return {'20b25080c143ec547938d0723ccc411e1fa0fe5e':'8.2.7'}.get(rev,'unknown')
def snapshot():
    release=Path(os.path.realpath(CURRENT)); rev=text(release/'.revision','unknown')
    op=load(OP,{}) ; cand=op.get('candidate') if isinstance(op.get('candidate'),dict) else {}
    pr=load(PROGRESS,{}) ; stop=load(STOP,{})
    ds=unit('chacha-dev-direct-operator.service')
    es=unit('chacha-dev-emergency-stop-surface.service')
    eb=unit('chacha-dev-emergency-control-bridge.service')
    if bool(stop.get('active')): stop_state='ACTIVE'
    elif es and eb: stop_state='READY'
    else: stop_state='FAIL'
    cstate=str(cand.get('state') or cand.get('status') or 'QUALIFIED_NOT_DEPLOYED')
    if cstate=='STAGED_NOT_ACTIVE': cstate='QUALIFIED_NOT_DEPLOYED'
    return {
      'schema':'chacha.dev/user-cockpit/v1','scope':'chacha-dev-only','observed_at':iso(),
      'production':{'version':production_version(rev,release),'revision':rev,'state':'ACTIVE','path':str(release)},
      'candidate':{'version':cand.get('version','8.3.1'),'revision':cand.get('revision','c6a5e89adf7d5a2d3efdb6110fc4ea10f91f72fc'),'tree':cand.get('tree','0ffea921ffb47bcf2c0b749d98566bc5fac51a69'),'state':cstate},
      'operation':{'label':op.get('name') or 'Autonomy Core — cockpit et observabilité utilisateur','platform_percent':pr.get('platform_maturity_percent',86),'active_work_percent':op.get('percent',pr.get('active_work_percent',0)),'runtime_status':op.get('state') or pr.get('status') or 'IDLE'},
      'health':{'guardian':health('https://chacha-dev-guardian.chachasan090375.workers.dev/healthz'),'sentinel':health('https://chacha-dev-sentinel.chachasan090375.workers.dev/healthz'),'direct_operator':'PASS' if ds else 'FAIL','emergency_stop':stop_state},
      'truth':{'decided':op.get('decided') or 'Priorité actuelle : construire l’autonomie du système agentique avec visibilité utilisateur permanente.','executed':op.get('executed') or 'Le cockpit live est matérialisé hors release ; aucune promotion production n’a été effectuée.','verified':op.get('verified') or 'Les états sont relus depuis le runtime et les services réels.'},
      'next_human_boundary':op.get('human_boundary') or 'Validation visuelle du cockpit par l’utilisateur',
      'next_step':op.get('next_step') or 'Vérifier le cockpit puis reprendre le chantier Autonomy Core.',
      'autonomy_gaps':list((load(GAPS if GAPS.is_file() else SOURCE_GAPS,{}).get('gaps') or [])),
      'automatic_external_spend_eur':0,'execution_authority':False
    }
def publish():
    x=snapshot(); OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix('.json.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(tmp,OUT)
def main():
    while True:
        try:publish()
        except Exception:pass
        time.sleep(2)
if __name__=='__main__':main()
