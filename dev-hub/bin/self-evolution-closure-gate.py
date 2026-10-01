#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED')
    return x

def gate(policy:dict[str,Any],train:dict[str,Any],foundry:dict[str,Any],evolution:dict[str,Any])->dict[str,Any]:
    if policy.get('schema')!='chacha.dev/self-evolution-closure-gate-policy/v1':raise ValueError('POLICY_SCHEMA')
    blockers=[]
    if train.get('schema')!=policy.get('required_train_pilot_schema') or train.get('status')!='PASS':blockers.append('TRAIN_PLANNING_PILOT_NOT_PASS')
    if train.get('freeze_performed') is not False or train.get('composition_performed') is not False or train.get('promotion_performed') is not False:blockers.append('TRAIN_PILOT_MUTATED_STATE')
    if foundry.get('schema')!=policy.get('required_foundry_pilot_schema') or foundry.get('status')!='PASS':blockers.append('FOUNDRY_PILOT_NOT_PASS')
    if foundry.get('pilot_execution_performed') is not False or foundry.get('promotion_performed') is not False or foundry.get('production_mutation') is not False:blockers.append('FOUNDRY_PILOT_MUTATED_STATE')
    if evolution.get('schema')!=policy.get('required_universal_policy_schema'):blockers.append('UNIVERSAL_POLICY_SCHEMA')
    p=evolution.get('principles') if isinstance(evolution.get('principles'),dict) else {}
    if p.get('active_self_mutation') is not False:blockers.append('ACTIVE_SELF_MUTATION_NOT_DISABLED')
    if p.get('self_promotion') is not False:blockers.append('SELF_PROMOTION_NOT_DISABLED')
    if int(p.get('automatic_external_spend_eur',-1))!=0:blockers.append('NONZERO_EXTERNAL_SPEND')
    return {'schema':'chacha.dev/self-evolution-closure-gate/v1','status':'PASS' if not blockers else 'HOLD','blockers':blockers,'self_evolution_terminal_evidence_ready':not blockers,'execution_authority':False,'production_mutation':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--train-pilot',type=Path,required=True);ap.add_argument('--foundry-pilot',type=Path,required=True);ap.add_argument('--evolution-policy',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=gate(load(a.policy),load(a.train_pilot),load(a.foundry_pilot),load(a.evolution_policy));a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_SELF_EVOLUTION_CLOSURE_GATE='+out['status']);print('EXECUTION_AUTHORITY=NO');return 0 if out['status']=='PASS' else 10
if __name__=='__main__':raise SystemExit(main())
