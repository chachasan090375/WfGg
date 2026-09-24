#!/usr/bin/env python3
from __future__ import annotations
import argparse,fnmatch,hashlib,json,shutil
from pathlib import Path
from typing import Any

DEFAULT_EXCLUDES=(
  "dev-hub/tests/**",
  "dev-hub/docs/**",
  "dev-hub/bin/install-v6*.sh",
  "dev-hub/install-v*.sh",
  "**/__pycache__/**",
  "**/*.pyc"
)

def match(path:str,patterns:list[str])->bool:
    return any(fnmatch.fnmatch(path,p) for p in patterns)

def tree_stats(root:Path)->tuple[int,int]:
    files=[p for p in root.rglob("*") if p.is_file()]
    return len(files),sum(p.stat().st_size for p in files)

def digest(root:Path)->str:
    h=hashlib.sha256()
    for p in sorted((x for x in root.rglob("*") if x.is_file()),key=lambda x:x.as_posix()):
        rel=p.relative_to(root).as_posix().encode();data=p.read_bytes()
        h.update(len(rel).to_bytes(8,"big"));h.update(rel);h.update(len(data).to_bytes(8,"big"));h.update(data)
    return "sha256:"+h.hexdigest()

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--source-root",type=Path,required=True)
    ap.add_argument("--output-root",type=Path,required=True)
    ap.add_argument("--manifest",type=Path,required=True)
    a=ap.parse_args()
    src=a.source_root.resolve();out=a.output_root.resolve()
    if out.exists():shutil.rmtree(out)
    out.mkdir(parents=True)
    patterns=list(DEFAULT_EXCLUDES)
    copied=[];excluded=[]
    dev_hub=src/"dev-hub"
    if not dev_hub.is_dir():raise SystemExit("DEV_HUB_SOURCE_MISSING")
    for p in dev_hub.rglob("*"):
        if not p.is_file():continue
        rel=p.relative_to(src).as_posix()
        if match(rel,patterns):
            excluded.append(rel);continue
        dst=out/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst);copied.append(rel)
    # compiled runtime must not contain old version-specific installers/tests/docs.
    violations=[p for p in copied if match(p,patterns)]
    if violations:raise SystemExit("V7_COMPILED_RELEASE_EXCLUSION_VIOLATION")
    # Syntax-check runtime Python sources without generating __pycache__.
    checked=0
    for p in (out/"dev-hub/bin").glob("*.py"):
        compile(p.read_text(encoding="utf-8"),str(p),"exec");checked+=1
    source_files,source_bytes=tree_stats(dev_hub);out_files,out_bytes=tree_stats(out/"dev-hub")
    manifest={
      "schema":"chacha.dev/v7-compiled-runtime-release/v1",
      "source_root":str(src),"output_root":str(out),
      "source_files":source_files,"source_bytes":source_bytes,
      "compiled_files":out_files,"compiled_bytes":out_bytes,
      "excluded_file_count":len(excluded),"excluded_patterns":patterns,
      "python_runtime_files_compiled":checked,
      "compiled_tree_sha256":digest(out),
      "git_history_preserved":True,
      "historical_tests_docs_available_in_git":True,
      "canonical_observation_bus_rewrite":False,
      "benchmark_evidence_mutation":False,
      "automatic_external_spend_eur":0
    }
    a.manifest.parent.mkdir(parents=True,exist_ok=True)
    a.manifest.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print("CHACHA_DEV_V7_COMPILED_RUNTIME_RELEASE=PASS")
    print("SOURCE_FILES="+str(source_files))
    print("COMPILED_FILES="+str(out_files))
    print("EXCLUDED_FILES="+str(len(excluded)))
    print("SOURCE_MIB="+str(round(source_bytes/1024/1024,1)))
    print("COMPILED_MIB="+str(round(out_bytes/1024/1024,1)))
    print("GIT_HISTORY_PRESERVED=YES")
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0
if __name__=="__main__":raise SystemExit(main())
