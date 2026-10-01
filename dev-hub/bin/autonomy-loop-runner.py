#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,json,os,subprocess,sys,uuid
from pathlib import Path
from typing import Any

def iso(): return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z")
def load(p:Path,default=None):
    try:
        x=json.loads(p.read_text(encoding="utf-8")); return x if isinstance(x,dict) else ({} if default is None else default)
    except Exception:return {} if default is None else default
def save(p:Path,x:dict[str,Any]):
    p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+".tmp");t.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");os.replace(t,p)
def run(argv:list[str],timeout:int)->subprocess.CompletedProcess[str]:
    return subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)
def emergency_active(path:Path)->bool:return load(path,{}).get("active") is True
def parse_iso(value:Any):
    try:return datetime.datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone(datetime.timezone.utc)
    except Exception:return None
def unit_allowed(unit:str,policy:dict[str,Any])->bool:
    allowed=set(str(x) for x in ((policy.get("runtime") or {}).get("allowed_systemd_units") or []));return unit in allowed
def dispatch_owner(action:dict[str,Any],policy:dict[str,Any],systemctl_bin:Path,timeout:int)->dict[str,Any]:
    spec=((policy.get("owner_actions") or {}).get(str(action.get("action") or "")) or {}).get("dispatch") or {}
    if spec.get("type")!="systemd-unit":return {"status":"BLOCKED","reason":"OWNER_DISPATCH_UNSUPPORTED","action":action}
    unit=str(spec.get("unit") or "")
    if not unit_allowed(unit,policy):return {"status":"BLOCKED","reason":"OWNER_UNIT_NOT_ALLOWLISTED","unit":unit,"action":action}
    p=run([str(systemctl_bin),"start",unit],timeout)
    return {"status":"DISPATCHED" if p.returncode==0 else "BLOCKED","owner":action.get("owner"),"action":action.get("action"),"issue_code":action.get("issue_code"),"subject":action.get("subject"),"unit":unit,"returncode":p.returncode,"stdout_tail":p.stdout[-1200:],"stderr_tail":p.stderr[-1200:],"direct_mutation_by_supervisor":False}
def cli(repo:Path,name:str,*args:str,timeout:int=120)->dict[str,Any]:
    out=Path(args[args.index("--output")+1])
    p=run([sys.executable,str(repo/"dev-hub/bin"/name),*args],timeout)
    if not out.is_file():raise RuntimeError(name+"_OUTPUT_MISSING:"+p.stderr[-1000:])
    return load(out,{})
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",type=Path,required=True);ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime"));ap.add_argument("--platform-root",type=Path,default=Path("/opt/chacha-dev/platform"));ap.add_argument("--policy",type=Path);ap.add_argument("--self-policy",type=Path);ap.add_argument("--systemctl-bin",type=Path,default=Path("/usr/bin/systemctl"));ap.add_argument("--test-mode",action="store_true");a=ap.parse_args()
    repo=a.repo_root.resolve();policy=load(a.policy or repo/"dev-hub/config/autonomy-supervision.v1.json");self_policy=a.self_policy or repo/"dev-hub/config/autonomy-self-model.v1.json";cfg=policy.get("runtime") or {};runtime=a.runtime_root.resolve();platform=a.platform_root.resolve()
    state_path=Path(str(cfg.get("state_file")));work_root=Path(str(cfg.get("work_root")))
    if a.test_mode:
        state_path=runtime/"autonomy-core/loop-state.json";work_root=runtime/"autonomy-core/work"
    emergency=Path(str(cfg.get("emergency_stop"))); emergency=runtime/"control/emergency-stop.json" if a.test_mode else emergency
    max_cycles=max(1,min(int(cfg.get("max_cycles_per_run") or 3),10));owner_timeout=max(30,min(int(cfg.get("owner_timeout_seconds") or 1200),3600));run_id="autonomy-"+uuid.uuid4().hex[:12];run_root=work_root/run_id;run_root.mkdir(parents=True,exist_ok=True)
    if emergency_active(emergency):
        out={"schema":"chacha.dev/autonomy-loop-run/v1","run_id":run_id,"status":"STOPPED","next_state":"AWAIT_HUMAN","reason":"EMERGENCY_STOP_ACTIVE","cycles":0,"direct_mutation_by_supervisor":False,"automatic_external_spend_eur":0};save(run_root/"run.json",out);print("CHACHA_DEV_AUTONOMY_LOOP=STOPPED");return 0
    history=[]
    for cycle in range(1,max_cycles+1):
        before=run_root/f"cycle-{cycle}-self-model.json";planp=run_root/f"cycle-{cycle}-plan.json"
        model=cli(repo,"autonomy-self-model.py","--repo-root",str(repo),"--runtime-root",str(runtime),"--platform-root",str(platform),"--policy",str(self_policy),"--output",str(before))
        plan=cli(repo,"autonomy-supervision-controller.py","--mode","plan","--policy",str(a.policy or repo/"dev-hub/config/autonomy-supervision.v1.json"),"--self-model",str(before),"--output",str(planp))
        state_out=run_root/f"cycle-{cycle}-state.out.json";pstate=run([sys.executable,str(repo/"dev-hub/bin/autonomy-loop-state.py"),"--state",str(state_path),"--self-model",str(before),"--plan",str(planp)],60)
        if plan.get("next_state") in {"RESUME","WAIT_EXTERNAL","AWAIT_HUMAN","BLOCKED"}:
            human_plan_path=None;human_plan=None
            if plan.get("next_state")=="AWAIT_HUMAN":
                human_plan_path=run_root/f"cycle-{cycle}-human-remediation-plan.json"
                human_plan=cli(repo,"human-remediation-plan.py","--plan",str(planp),"--self-model",str(before),"--policy",str(repo/"dev-hub/config/human-remediation-planning.v1.json"),"--output",str(human_plan_path))
                if human_plan.get("status")!="PASS":raise RuntimeError("HUMAN_REMEDIATION_PLAN_BLOCKED")
            result={"schema":"chacha.dev/autonomy-loop-run/v1","run_id":run_id,"status":plan.get("status"),"next_state":plan.get("next_state"),"cycles":cycle,"history":history,"direct_mutation_by_supervisor":False,"automatic_external_spend_eur":0}
            if human_plan_path is not None:
                result["human_remediation_plan"]=str(human_plan_path);result["human_remediation_dossier_count"]=int((human_plan or {}).get("dossier_count") or 0)
            save(run_root/"run.json",result);print("CHACHA_DEV_AUTONOMY_LOOP="+str(result["status"]));print("NEXT_STATE="+str(result["next_state"]));return 0 if plan.get("next_state")!="BLOCKED" else 2
        actions=[x for x in plan.get("actions") or [] if isinstance(x,dict)]
        state_now=load(state_path,{})
        issue_state=state_now.get("issues") if isinstance(state_now.get("issues"),dict) else {}
        max_attempts=max(1,min(int(cfg.get("max_attempts_per_issue") or 3),20));cooldown=max(0,min(int(cfg.get("retry_cooldown_seconds") or 0),86400))
        exhausted=[];cooling=[];now=datetime.datetime.now(datetime.timezone.utc)
        for action in actions:
            key=str(action.get("issue_code"))+"|"+str(action.get("subject"))
            row=issue_state.get(key) if isinstance(issue_state.get(key),dict) else {}
            if int(row.get("attempts") or 0)>=max_attempts: exhausted.append(key);continue
            last=parse_iso(row.get("last_attempt_at"))
            if cooldown and last and (now-last).total_seconds()<cooldown: cooling.append(key)
        if exhausted:
            result={"schema":"chacha.dev/autonomy-loop-run/v1","run_id":run_id,"status":"BLOCKED","next_state":"AWAIT_HUMAN","reason":"AUTONOMY_ATTEMPT_BUDGET_EXHAUSTED","issues":sorted(exhausted),"cycles":cycle,"history":history,"direct_mutation_by_supervisor":False,"automatic_external_spend_eur":0};save(run_root/"run.json",result);print("CHACHA_DEV_AUTONOMY_LOOP=BLOCKED");print("NEXT_STATE=AWAIT_HUMAN");return 0
        if cooling:
            result={"schema":"chacha.dev/autonomy-loop-run/v1","run_id":run_id,"status":"WAITING_RETRY","next_state":"RETRY_LATER","reason":"AUTONOMY_RETRY_COOLDOWN","issues":sorted(cooling),"cycles":cycle,"history":history,"direct_mutation_by_supervisor":False,"automatic_external_spend_eur":0};save(run_root/"run.json",result);print("CHACHA_DEV_AUTONOMY_LOOP=WAITING_RETRY");print("NEXT_STATE=RETRY_LATER");return 0
        # One owner unit is triggered once even if several issues map to it.
        grouped={}
        for action in actions:
            spec=((policy.get("owner_actions") or {}).get(str(action.get("action") or "")) or {}).get("dispatch") or {}
            key=(str(spec.get("type") or ""),str(spec.get("unit") or ""),str(action.get("action") or ""))
            grouped.setdefault(key,[]).append(action)
        dispatched=[]
        for _,group in grouped.items():
            if emergency_active(emergency):
                dispatched.append({"status":"BLOCKED","reason":"EMERGENCY_STOP_ACTIVE_DURING_DISPATCH","action":group[0]});break
            owner_result=dispatch_owner(group[0],policy,a.systemctl_bin,owner_timeout)
            for action in group:
                dispatched.append({**owner_result,"issue_code":action.get("issue_code"),"subject":action.get("subject"),"owner":action.get("owner"),"action":action.get("action")})
        # Attempts are state of the autonomy loop itself, never owner state.
        state_now=load(state_path,{})
        rows=state_now.get("issues") if isinstance(state_now.get("issues"),dict) else {}
        for d in dispatched:
            if d.get("status")!="DISPATCHED": continue
            key=str(d.get("issue_code"))+"|"+str(d.get("subject"));row=rows.get(key) if isinstance(rows.get(key),dict) else {}
            row["attempts"]=int(row.get("attempts") or 0)+1;row["last_action"]=d.get("action");row["last_attempt_at"]=iso();rows[key]=row
        state_now["issues"]=rows;save(state_path,state_now)
        execution={"schema":"chacha.dev/autonomy-owner-execution/v1","run_id":run_id,"cycle":cycle,"actions":dispatched,"supervisor_direct_mutation":False,"automatic_external_spend_eur":0};execp=run_root/f"cycle-{cycle}-execution.json";save(execp,execution)
        if any(x.get("status")!="DISPATCHED" for x in dispatched):
            result={"schema":"chacha.dev/autonomy-loop-run/v1","run_id":run_id,"status":"BLOCKED","next_state":"BLOCKED","reason":"OWNER_DISPATCH_FAILED","cycles":cycle,"history":history,"execution":execution,"direct_mutation_by_supervisor":False,"automatic_external_spend_eur":0};save(run_root/"run.json",result);print("CHACHA_DEV_AUTONOMY_LOOP=BLOCKED");return 2
        after=run_root/f"cycle-{cycle}-after.json";fresh=cli(repo,"autonomy-self-model.py","--repo-root",str(repo),"--runtime-root",str(runtime),"--platform-root",str(platform),"--policy",str(self_policy),"--output",str(after))
        # A dispatched owner is not claimed successful: only disappeared issues are verified on the fresh model.
        before_keys={(x.get("code"),x.get("subject")) for x in (model.get("reconciliation") or {}).get("issues") or [] if isinstance(x,dict)};after_keys={(x.get("code"),x.get("subject")) for x in (fresh.get("reconciliation") or {}).get("issues") or [] if isinstance(x,dict)}
        for row in execution["actions"]:
            key=(row.get("issue_code"),row.get("subject"));row["status"]="VERIFIED" if key in before_keys-after_keys else "DISPATCHED"
        save(execp,execution)
        verp=run_root/f"cycle-{cycle}-verification.json";verification=cli(repo,"autonomy-supervision-controller.py","--mode","verify","--policy",str(a.policy or repo/"dev-hub/config/autonomy-supervision.v1.json"),"--before",str(before),"--after",str(after),"--execution",str(execp),"--output",str(verp))
        history.append({"cycle":cycle,"plan":plan.get("status"),"verification":verification.get("status"),"remaining":verification.get("remaining") or []})
        if verification.get("next_state")!="RESUME":
            result={"schema":"chacha.dev/autonomy-loop-run/v1","run_id":run_id,"status":"PARTIAL","next_state":"RETRY_LATER","cycles":cycle,"history":history,"direct_mutation_by_supervisor":False,"automatic_external_spend_eur":0};save(run_root/"run.json",result);print("CHACHA_DEV_AUTONOMY_LOOP=PARTIAL");print("NEXT_STATE=RETRY_LATER");return 0
        if verification.get("next_state")=="RESUME":
            finalp=run_root/f"cycle-{cycle}-final-plan.json";finalplan=cli(repo,"autonomy-supervision-controller.py","--mode","plan","--policy",str(a.policy or repo/"dev-hub/config/autonomy-supervision.v1.json"),"--self-model",str(after),"--output",str(finalp));run([sys.executable,str(repo/"dev-hub/bin/autonomy-loop-state.py"),"--state",str(state_path),"--self-model",str(after),"--plan",str(finalp)],60)
            result={"schema":"chacha.dev/autonomy-loop-run/v1","run_id":run_id,"status":"CONVERGED","next_state":"RESUME","cycles":cycle,"history":history,"direct_mutation_by_supervisor":False,"automatic_external_spend_eur":0};save(run_root/"run.json",result);print("CHACHA_DEV_AUTONOMY_LOOP=CONVERGED");print("NEXT_STATE=RESUME");return 0
    result={"schema":"chacha.dev/autonomy-loop-run/v1","run_id":run_id,"status":"PARTIAL","next_state":"CLASSIFY","cycles":max_cycles,"history":history,"direct_mutation_by_supervisor":False,"automatic_external_spend_eur":0};save(run_root/"run.json",result);print("CHACHA_DEV_AUTONOMY_LOOP=PARTIAL");print("NEXT_STATE=CLASSIFY");return 0
if __name__=="__main__":raise SystemExit(main())
