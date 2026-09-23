#!/usr/bin/env python3
from __future__ import annotations
import argparse,ast,hashlib,json,os,re,subprocess,time
from pathlib import Path
from typing import Any

CONFLICT=re.compile(r"^(<<<<<<<|=======|>>>>>>>)",re.M)
TODO=re.compile(r"\b(TODO|FIXME|HACK|XXX)\b",re.I)
TEXT_EXT={".py",".js",".mjs",".cjs",".ts",".tsx",".jsx",".sh",".bash",".json",".jsonc",".md",".yml",".yaml",".toml",".css",".html"}

def now()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def canon(v:Any)->str:return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v:Any)->str:return "sha256:"+hashlib.sha256(canon(v).encode()).hexdigest()
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def run(cmd:list[str],cwd:Path,env:dict[str,str]|None=None,timeout:int=180)->dict[str,Any]:
    e=os.environ.copy()
    if env:e.update(env)
    p=subprocess.run(cmd,cwd=cwd,env=e,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)
    return {"command":cmd,"returncode":p.returncode,"stdout":p.stdout[-8000:],"stderr":p.stderr[-8000:]}

def changed_files(root:Path,base:str|None,head:str)->list[Path]:
    if base:
        p=run(["git","diff","--name-only","--diff-filter=ACMR",base,head],root,timeout=30)
        if p["returncode"]==0:
            return [root/x for x in p["stdout"].splitlines() if x.strip() and (root/x).is_file()]
    p=run(["git","ls-files"],root,timeout=30)
    if p["returncode"]!=0:return []
    return [root/x for x in p["stdout"].splitlines() if x.strip() and (root/x).is_file()]

def python_function_warnings(path:Path,threshold:int)->list[dict[str,Any]]:
    try:
        tree=ast.parse(path.read_text(encoding="utf-8"))
    except Exception:return []
    out=[]
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and getattr(n,"end_lineno",None):
            lines=int(n.end_lineno)-int(n.lineno)+1
            if lines>threshold:out.append({"function":n.name,"line":n.lineno,"lines":lines})
    return out

def syntax_check(path:Path,root:Path)->dict[str,Any]|None:
    ext=path.suffix.lower()
    rel=str(path.relative_to(root))
    if ext==".py":
        r=run(["python3","-m","py_compile",rel],root,timeout=60)
    elif ext in {".js",".mjs",".cjs"}:
        if subprocess.run(["bash","-lc","command -v node >/dev/null"],stdout=subprocess.DEVNULL).returncode!=0:return {"file":rel,"status":"SKIPPED","reason":"node_missing"}
        r=run(["node","--check",rel],root,timeout=60)
    elif ext in {".sh",".bash"}:
        r=run(["bash","-n",rel],root,timeout=60)
    elif ext==".json":
        r=run(["python3","-m","json.tool",rel],root,timeout=60)
    else:return None
    return {"file":rel,"status":"PASS" if r["returncode"]==0 else "FAIL","detail":r}

def audit(root:Path,policy:dict[str,Any],base:str|None,head:str,run_tests:bool)->dict[str,Any]:
    thresholds=policy.get("thresholds") or {}
    files=changed_files(root,base,head)
    blocking=[];warnings=[];syntax=[]
    scanned=0;lines_total=0
    for path in files:
        if path.suffix.lower() not in TEXT_EXT:continue
        rel=str(path.relative_to(root));scanned+=1
        try:text=path.read_text(encoding="utf-8")
        except UnicodeDecodeError:continue
        lines=text.splitlines();lines_total+=len(lines)
        if CONFLICT.search(text):blocking.append({"check":"merge-conflict-markers","file":rel})
        syn=syntax_check(path,root)
        if syn:
            syntax.append(syn)
            if syn["status"]=="FAIL":blocking.append({"check":"syntax","file":rel,"detail":syn["detail"]})
        long=[i+1 for i,x in enumerate(lines) if len(x)>int(thresholds.get("max_line_length_warning",240))]
        if long:warnings.append({"check":"long-lines","file":rel,"count":len(long),"sample_lines":long[:20]})
        trailing=[i+1 for i,x in enumerate(lines) if x.rstrip()!=x]
        if trailing:warnings.append({"check":"trailing-whitespace","file":rel,"count":len(trailing),"sample_lines":trailing[:20]})
        if len(lines)>int(thresholds.get("max_file_lines_warning",2500)):
            warnings.append({"check":"large-files","file":rel,"lines":len(lines)})
        todo=len(TODO.findall(text))
        density=(todo*1000/max(1,len(lines)))
        if density>float(thresholds.get("max_todo_fixme_per_1000_lines_warning",25)):
            warnings.append({"check":"todo-fixme-density","file":rel,"count":todo,"per_1000_lines":round(density,2)})
        if path.suffix.lower()==".py":
            for item in python_function_warnings(path,int(thresholds.get("max_python_function_lines_warning",180))):
                warnings.append({"check":"large-python-functions","file":rel,**item})
    tests=[]
    if run_tests:
        env={str(k):str(v) for k,v in (policy.get("test_environment") or {}).items()}
        for spec in policy.get("mandatory_platform_tests") or []:
            if isinstance(spec,dict):
                rel=str(spec.get("path") or "")
                test_env=dict(env);test_env.update({str(k):str(v) for k,v in (spec.get("env") or {}).items()})
            else:
                rel=str(spec);test_env=dict(env)
            p=root/rel
            if not rel or not p.is_file():
                blocking.append({"check":"mandatory-tests","test":rel,"reason":"missing"})
                continue
            r=run(["python3",rel],root,env=test_env,timeout=240)
            row={"test":rel,"status":"PASS" if r["returncode"]==0 else "FAIL","detail":r}
            tests.append(row)
            if r["returncode"]!=0:blocking.append({"check":"mandatory-tests","test":rel,"detail":r})
    verdict="PASS" if not blocking else "BLOCK"
    result={
      "schema":"chacha.dev/sentinel-technical-audit/v1","generated_at":now(),"revision":head,
      "base_revision":base,"verdict":verdict,"scanned_file_count":scanned,"scanned_line_count":lines_total,
      "blocking_findings":blocking,"advisory_findings":warnings,"syntax_checks":syntax,"test_results":tests,
      "tests_executed":run_tests,"technical_quality_is_external_advisory_except_blocking_policy":True,
      "direct_code_mutation":False,"central_orchestrator_owns_remediation":True,
      "automatic_external_spend_eur":0
    }
    result["audit_digest"]=digest(result)
    return result

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("."))
    ap.add_argument("--policy",type=Path,default=Path("dev-hub/config/sentinel-technical-policy.v1.json"))
    ap.add_argument("--base")
    ap.add_argument("--head",default="HEAD")
    ap.add_argument("--run-tests",action="store_true")
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args();root=a.repo_root.resolve()
    pol=load(root/a.policy if not a.policy.is_absolute() else a.policy)
    head_run=run(["git","rev-parse",a.head],root,timeout=30)
    if head_run["returncode"]!=0:raise SystemExit("SENTINEL_HEAD_RESOLUTION_FAILED")
    head=head_run["stdout"].strip()
    base=None
    if a.base:
        b=run(["git","rev-parse",a.base],root,timeout=30)
        if b["returncode"]==0:base=b["stdout"].strip()
    out=audit(root,pol,base,head,a.run_tests)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_SENTINEL_TECHNICAL_AUDIT="+out["verdict"])
    print("REVISION="+head)
    print("BLOCKING_FINDINGS="+str(len(out["blocking_findings"])))
    print("ADVISORY_FINDINGS="+str(len(out["advisory_findings"])))
    print("DIRECT_CODE_MUTATION=NO")
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if out["verdict"]=="PASS" else 20

if __name__=="__main__":raise SystemExit(main())
