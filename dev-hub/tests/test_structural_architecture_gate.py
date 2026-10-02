import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name): return json.loads((ROOT/'config'/name).read_text())
def test_logician_is_falsifier_not_duplicate_authority():
    x=load('technology-watch-logician.v1.json')['structural_falsification']
    assert x['enabled'] and x['role']=='ADVERSARIAL_EVIDENCE_ONLY'
    assert {'FINAL_ARCHITECTURE_DECISION','MUTATE_CANONICAL_GRAPH','MUTATE_RUNTIME','PROMOTE_RELEASE'} <= set(x['forbidden_authorities'])
def test_canonical_route_and_existing_subject_are_mandatory():
    x=load('canonical-component-registry.v1.json')
    assert x['principles']['canonical_execution_route_authority_required']
    assert x['execution_route_authority']['existing_subject_must_be_reused']
    assert x['execution_route_authority']['resume_requires_canonical_mission_owner']
def test_persistent_convoy_survives_client_and_resumes_nonterminal():
    x=load('persistent-missions.v1.json')
    assert x['principles']['client_lifecycle_independent']
    assert x['roadmap_convoy']['resume_from_first_nonterminal_train']
    assert x['roadmap_convoy']['one_train_at_a_time']
    assert x['roadmap_convoy']['automatic_external_spend_eur']==0
def test_gate_separates_existing_agent_responsibilities():
    r=load('structural-architecture-gate.v1.json')['responsibilities']
    assert len(set(r.values()))==len(r)
    assert r['logician']=='FALSIFY_ONLY' and r['guardian']=='POLICY_ENFORCEMENT'
