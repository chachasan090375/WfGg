#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re,time
from pathlib import Path
from typing import Any

REPORT_SCHEMA="chacha.dev/version-coupling-audit/v1"
TEXT_EXTS={'.py','.sh','.json','.service','.timer','.yml','.yaml','.js','.mjs','.md'}
MAJOR='(?:7|8|9|[1-9][0-9]+)'
VERSION_LITERAL=re.compile(r'(?<![A-Za-z0-9])(?:V|v)?'+MAJOR+r'\.\d+(?:\.\d+)?')
STARTSWITH_MAJOR=re.compile(r'startswith\(\s*["\']'+MAJOR+r'\.')
MAJOR_COMPARE=re.compile(r'\b(?:major|platform_major|core_platform_major)\s*(?:==|!=|<=|>=|<|>)\s*'+MAJOR+r'\b')
PLATFORM_COMPARE=re.compile(r'\b(?:platform_version|core_platform_version)\b[^\n]{0,50}(?:==|!=|<=|>=|<|>)\s*["\']'+MAJOR+r'\.')
PLATFORM_FIELD=re.compile(r'["\'](?:platform_version|core_platform_version)["\']\s*:\s*["\']'+MAJOR+r'\.\d+(?:\.\d+)?["\']')

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n');os.replace(tmp,path)

def now_iso()->str:return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def classify(rel:str,line:str)->str:
    low=rel.casefold()
    if '/tests/' in '/'+low or '/docs/' in '/'+low or '/evidence/' in '/'+low:
        return 'TEST_OR_HISTORICAL_EVIDENCE'
    name=Path(rel).name.casefold()
    if name.startswith('install-v') or name.startswith('run-radar-v') or 'platform-baseline.v' in name:
        return 'RELEASE_INSTALLER_ARCHIVE'
    if STARTSWITH_MAJOR.search(line) or MAJOR_COMPARE.search(line) or PLATFORM_COMPARE.search(line):
        return 'ACTIVE_RUNTIME_VERSION_COUPLING'
    if PLATFORM_FIELD.search(line):
        return 'ACTIVE_POLICY_VERSION_COUPLING'
    if 'v7_runtime_health_pass' in line:
        return 'LEGACY_EVIDENCE_COMPATIBILITY'
    if 'clientInfo' in line or 'protocolVersion' in line:
        return 'EXTERNAL_OR_PROTOCOL_VERSION'
    if re.search(r'["\']version["\']\s*:',line):
        return 'COMPONENT_OR_POLICY_VERSION'
    return 'VERSION_REFERENCE_REVIEWED_NONBLOCKING'

def audit(root:Path)->dict[str,Any]:
    rows=[]
    for p in root.rglob('*'):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXTS or '.git' in p.parts or '__pycache__' in p.parts:continue
        rel=str(p.relative_to(root))
        try:lines=p.read_text(encoding='utf-8',errors='ignore').splitlines()
        except Exception:continue
        for i,line in enumerate(lines,1):
            if not VERSION_LITERAL.search(line) and 'v7_runtime_health_pass' not in line:continue
            rows.append({'path':rel,'line':i,'text':line.strip()[:500],'classification':classify(rel,line)})
    blocking=[r for r in rows if r['classification'] in {'ACTIVE_RUNTIME_VERSION_COUPLING','ACTIVE_POLICY_VERSION_COUPLING'}]
    counts={}
    for r in rows:counts[r['classification']]=counts.get(r['classification'],0)+1
    return {'schema':REPORT_SCHEMA,'generated_at':now_iso(),'reference_count':len(rows),
            'classification_counts':dict(sorted(counts.items())),'blocking_count':len(blocking),
            'blocking':blocking,'references':rows,'status':'PASS' if not blocking else 'BLOCKED',
            'automatic_external_spend_eur':0}
def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo-root',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--strict',action='store_true')
    a=ap.parse_args();out=audit(a.repo_root.resolve()/ 'dev-hub')
    save(a.output,out)
    print('CHACHA_DEV_VERSION_AGNOSTIC_ACTIVE_RUNTIME='+out['status'])
    print('REFERENCE_COUNT='+str(out['reference_count']))
    print('BLOCKING_COUNT='+str(out['blocking_count']))
    print('CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
    return 2 if a.strict and out['status']!='PASS' else 0

if __name__=='__main__':raise SystemExit(main())
