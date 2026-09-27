#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Any
import provider_quota_circuit as pqc
SCHEMA='chacha.dev/provider-zero-cost-attestation/v1'
PROVIDER='antigravity'
MODEL_PREFERENCES=[('gemini-3.8-flash-medium','gemini models'),('claude-sonnet-4-6','claude and gpt models'),('gpt-oss-120b-medium','claude and gpt models')]
def now()->datetime:return datetime.now(timezone.utc)
def iso(v:datetime)->str:return v.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
def sha(raw:bytes)->str:return 'sha256:'+hashlib.sha256(raw).hexdigest()
def save(path:Path,x:dict[str,Any])->None:
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');os.replace(tmp,path)
def run_json(backend:Path,home:Path,slash:str,timeout:int=40)->tuple[int,dict[str,Any]|None,bytes,bytes]:
 env=os.environ.copy();env.pop('GEMINI_API_KEY',None);env['HOME']=str(home)
 try:p=subprocess.run([str(backend),'--print',slash,'--output-format','json','--print-timeout','20s'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=timeout)
 except Exception as exc:return 124,None,b'',type(exc).__name__.encode()
 try:x=json.loads(p.stdout.decode('utf-8','replace'))
 except Exception:x=None
 return p.returncode,x,p.stdout,p.stderr
def prepare_home(home:Path,token:Path)->Path:
 target=home/'.gemini/antigravity-cli';target.mkdir(parents=True,exist_ok=True)
 link=target/'antigravity-oauth-token'
 if link.exists() or link.is_symlink():
  if not link.is_symlink() or link.resolve()!=token.resolve():raise RuntimeError('ACCOUNT_TOKEN_LINK_UNTRUSTED')
 else:link.symlink_to(token)
 settings=target/'settings.json'
 settings.write_text(json.dumps({'useG1Credits':False,'enableTelemetry':False,'showTips':False,'showFeedbackSurvey':False,'enableTerminalSandbox':True},indent=2)+'\n',encoding='utf-8');settings.chmod(0o600)
 return settings
def result(status:str,output:Path,**kw)->dict[str,Any]:
 x={'schema':SCHEMA,'provider_id':PROVIDER,'status':status,'cost_class':'quota','observed_at':iso(now()),'automatic_external_spend_eur':0,**kw};save(output,x);return x
def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--provider',default=PROVIDER);ap.add_argument('--runtime-root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--backend',type=Path,default=Path('/usr/local/bin/agy'));ap.add_argument('--oauth-token',type=Path,default=Path('/root/.gemini/antigravity-cli/antigravity-oauth-token'));ap.add_argument('--valid-seconds',type=int,default=300);ap.add_argument('--minimum-remaining-fraction',type=float,default=0.01);a=ap.parse_args()
 if a.provider!=PROVIDER:result('BLOCK',a.output,quota_available=False,reason_codes=['PROVIDER_UNSUPPORTED']);return 20
 if not a.backend.is_file() or not os.access(a.backend,os.X_OK):result('BLOCK',a.output,quota_available=False,reason_codes=['BACKEND_MISSING']);return 20
 if not a.oauth_token.is_file():result('BLOCK',a.output,quota_available=False,reason_codes=['ACCOUNT_OAUTH_SESSION_MISSING']);return 20
 home=a.runtime_root.resolve()/'provider-economics/antigravity-account-home'
 try:prepare_home(home,a.oauth_token.resolve())
 except Exception as exc:result('BLOCK',a.output,quota_available=False,reason_codes=[type(exc).__name__+':'+str(exc)]);return 20
 crc,cfg,craw,cerr=run_json(a.backend,home,'/config')
 urc,usage,uraw,uerr=run_json(a.backend,home,'/usage')
 reasons=[]
 config=((cfg or {}).get('command') or {}).get('data',{}).get('config',{}) if isinstance(cfg,dict) else {}
 if crc!=0 or not isinstance(cfg,dict) or cfg.get('status')!='SUCCESS' or ((cfg.get('command') or {}).get('name'))!='config':reasons.append('ACCOUNT_CONFIG_PROBE_FAILED')
 if cfg and (cfg.get('num_turns')!=0 or ((cfg.get('usage') or {}).get('total_tokens') not in {0,None})):reasons.append('CONFIG_PROBE_CONSUMED_MODEL_TOKENS')
 if config.get('useG1Credits') is not False:reasons.append('AI_CREDIT_OVERAGE_NOT_DISABLED')
 if str(config.get('modelProvider') or ''):reasons.append('ACCOUNT_AUTH_NOT_ACTIVE')
 if urc!=0 or not isinstance(usage,dict) or usage.get('status')!='SUCCESS' or ((usage.get('command') or {}).get('name'))!='usage':reasons.append('ACCOUNT_USAGE_PROBE_FAILED')
 if usage and (usage.get('num_turns')!=0 or ((usage.get('usage') or {}).get('total_tokens') not in {0,None})):reasons.append('USAGE_PROBE_CONSUMED_MODEL_TOKENS')
 groups={}
 for group in ((((usage or {}).get('command') or {}).get('data') or {}).get('groups') or []):
  name=str(group.get('name') or '').strip().casefold()
  vals=[];reset=None
  for bucket in group.get('buckets') or []:
   try:vals.append(float(bucket.get('remaining_fraction')))
   except Exception:continue
   if reset is None:reset=bucket.get('reset_time')
  if vals:groups[name]={'remaining_fraction':min(vals),'reset_time':reset}
 env=os.environ.copy();env.pop('GEMINI_API_KEY',None);env['HOME']=str(home)
 try:mp=subprocess.run([str(a.backend),'models'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=40)
 except Exception as exc:mp=None;reasons.append('ACCOUNT_MODELS_PROBE_FAILED:'+type(exc).__name__)
 available=set()
 if mp is not None and mp.returncode==0:
  for line in mp.stdout.decode('utf-8','replace').splitlines():
   mid=line.split('\t',1)[0].strip()
   if mid:available.add(mid)
 else:reasons.append('ACCOUNT_MODELS_PROBE_FAILED')
 eligible=[];blocked_models=[];quota_eligible_before_circuit=[]
 for model,group_name in MODEL_PREFERENCES:
  row=groups.get(group_name) or {};remaining=row.get('remaining_fraction')
  if model in available and isinstance(remaining,(int,float)) and remaining>=a.minimum_remaining_fraction:
   quota_eligible_before_circuit.append(model)
   circuit=pqc.blocked(PROVIDER,model)
   if circuit:
    blocked_models.append({'model':model,'quota_group':group_name,'resume_at':circuit.get('resume_at')});continue
   eligible.append({'model':model,'quota_group':group_name,'remaining_fraction':remaining,'reset_time':row.get('reset_time')})
 selected=eligible[0] if eligible else None
 if not groups:reasons.append('ACCOUNT_BASELINE_QUOTA_MISSING')
 if selected is None:
  reasons.append('ACCOUNT_BASELINE_QUOTA_INSUFFICIENT')
  if quota_eligible_before_circuit and len(blocked_models)==len(quota_eligible_before_circuit):reasons.append('PROVIDER_MODEL_QUOTA_EXHAUSTED')
 remaining=(selected or {}).get('remaining_fraction');reset=(selected or {}).get('reset_time')
 fallback_resets=[str(v.get('resume_at')) for v in blocked_models if v.get('resume_at')]
 if reset is None and fallback_resets:reset=min(fallback_resets)
 if reset is None:
  quota_resets=[str(v.get('reset_time')) for v in groups.values() if isinstance(v,dict) and v.get('reset_time')]
  if quota_resets:reset=min(quota_resets)
 ttl=max(30,min(1800,int(a.valid_seconds)));expiry=now()+timedelta(seconds=ttl)
 if reset:
  try:
   rt=datetime.fromisoformat(str(reset).replace('Z','+00:00'))
   if rt<expiry:expiry=rt
  except Exception:pass
 passed=not reasons
 x=result('PASS' if passed else 'BLOCK',a.output,quota_available=bool(passed and selected),valid_until=iso(expiry),auth_mode='account-oauth',baseline_quota_only=True,overage_enabled=False,quota_remaining_fraction=remaining,quota_reset_time=reset,resume_at=reset if not passed else None,selected_model=(selected or {}).get('model'),selected_quota_group=(selected or {}).get('quota_group'),eligible_models=[r['model'] for r in eligible],blocked_models=blocked_models,quota_groups=groups,minimum_remaining_fraction=a.minimum_remaining_fraction,account_home=str(home),config_probe_digest=sha(craw),usage_probe_digest=sha(uraw),models_probe_digest=sha(mp.stdout if mp is not None else b''),config_probe_zero_tokens=bool(cfg and cfg.get('num_turns')==0 and ((cfg.get('usage') or {}).get('total_tokens') in {0,None})),usage_probe_zero_tokens=bool(usage and usage.get('num_turns')==0 and ((usage.get('usage') or {}).get('total_tokens') in {0,None})),reason_codes=sorted(set(reasons)),probe_stderr_digests={'config':sha(cerr),'usage':sha(uerr),'models':sha(mp.stderr if mp is not None else b'')})
 print(json.dumps(x,indent=2,ensure_ascii=False));return 0 if passed else 20
if __name__=='__main__':raise SystemExit(main())
