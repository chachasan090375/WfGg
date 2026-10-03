#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED')
    return x
def valid_cutover(policy:dict[str,Any],lineage:dict[str,Any]|None,coverage:dict[str,Any])->bool:
    rule=policy.get('historical_missing_context') or {}
    if rule.get('mode')!='QUARANTINE_PRE_CUTOVER_ONLY':return False
    if not isinstance(lineage,dict) or lineage.get('schema')!=rule.get('required_lineage_cutover_schema') or lineage.get('status')!='PASS':return False
    if rule.get('require_missing_after_cutover_zero',True) and int(lineage.get('missing_after_cutover') or 0)!=0:return False
    if rule.get('require_invalid_timestamp_events_zero',True) and int(lineage.get('invalid_timestamp_events') or 0)!=0:return False
    if rule.get('require_coverage_missing_context_match',True) and int(lineage.get('historical_missing_quarantined') or 0)!=int(coverage.get('missing_context_count') or 0):return False
    return True
def gate(policy:dict[str,Any],coverage:dict[str,Any],route:dict[str,Any],confidence:dict[str,Any],lineage_cutover:dict[str,Any]|None=None)->dict[str,Any]:
    if policy.get('schema')!='chacha.dev/learning-closure-gate-policy/v1':raise ValueError('POLICY_SCHEMA')
    blockers=[];cutover_ok=valid_cutover(policy,lineage_cutover,coverage)
    coverage_status=coverage.get('status')
    if coverage.get('schema')!='chacha.dev/learning-coverage-report/v1' or not (coverage_status=='PASS' or (coverage_status=='PASS_WITH_ADVISORY' and cutover_ok)):blockers.append('LEARNING_COVERAGE_NOT_EXACT_PASS')
    if float(coverage.get('coverage_percent') or 0)<float(policy.get('required_learning_coverage_percent') or 100):blockers.append('LEARNING_COVERAGE_BELOW_100')
    if int(coverage.get('gap_count') or 0)!=0:blockers.append('LEARNING_GAPS_REMAIN')
    if int(coverage.get('missing_context_count') or 0)!=0 and not cutover_ok:blockers.append('LEARNING_CONTEXT_MISSING')
    if route.get('schema')!='chacha.dev/cognitive-route-learning-summary/v1' or route.get('status')!='PASS':blockers.append('ROUTE_LEARNING_NOT_PASS')
    if route.get('router_mutation_authorized') is True or route.get('registry_mutation_authorized') is True:blockers.append('ROUTE_LEARNING_MUTATION_AUTHORITY')
    if confidence.get('schema')!='chacha.dev/model-capability-confidence/v1' or confidence.get('status')!='PASS':blockers.append('CONFIDENCE_NOT_PASS')
    entries=[x for x in confidence.get('entries') or [] if isinstance(x,dict)];verified=[x for x in entries if x.get('state')==policy.get('required_confidence_state')]
    if len(verified)<int(policy.get('minimum_verified_capabilities') or 3):blockers.append('VERIFIED_CAPABILITIES_INSUFFICIENT')
    if confidence.get('execution_authority') is True:blockers.append('CONFIDENCE_HAS_EXECUTION_AUTHORITY')
    out={'schema':'chacha.dev/learning-closure-gate/v2' if lineage_cutover is not None else 'chacha.dev/learning-closure-gate/v1','status':'PASS' if not blockers else 'HOLD','blockers':blockers,'coverage_percent':coverage.get('coverage_percent'),'verified_capabilities':len(verified),'learning_terminal_evidence_ready':not blockers,'execution_authority':False,'production_mutation':False,'automatic_external_spend_eur':0}
    if lineage_cutover is not None:out['historical_missing_quarantined']=int(lineage_cutover.get('historical_missing_quarantined') or 0)
    return out
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--coverage',type=Path,required=True);ap.add_argument('--route-learning',type=Path,required=True);ap.add_argument('--confidence',type=Path,required=True);ap.add_argument('--lineage-cutover',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    lineage=load(a.lineage_cutover) if a.lineage_cutover else None;out=gate(load(a.policy),load(a.coverage),load(a.route_learning),load(a.confidence),lineage);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_LEARNING_CLOSURE_GATE='+out['status']);print('EXECUTION_AUTHORITY=NO');return 0 if out['status']=='PASS' else 10
if __name__=='__main__':raise SystemExit(main())
