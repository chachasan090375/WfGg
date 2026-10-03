from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
POL=json.loads((ROOT/'dev-hub/config/domain-specialist-memory.v1.json').read_text())
DOM=json.loads((ROOT/'dev-hub/config/domain-orchestration.v1.json').read_text())

def test_specialist_namespaces_derive_from_canonical_domains():
 assert POL['domain_catalog']=='dev-hub/config/domain-orchestration.v1.json'
 assert len(DOM['domains'])>=8
 assert POL['memory_namespace_template']=='specialist:{domain}'
def test_dark_intelligence_is_never_direct_memory_input():
 d=POL['source_planes']['dark_intelligence'];assert d['direct_ingestion_forbidden'] is True
 assert d['accepted_input']=='CORROBORATED_TECHNOLOGY_DOSSIER_ONLY';assert d['isolation_required'] is True
def test_specialist_memory_cannot_expand_authority():
 p=POL['principles'];assert p['memory_cannot_expand_permissions'] is True;assert p['memory_cannot_grant_architecture_authority'] is True
def test_material_claims_require_truth_pipeline():
 v=POL['verification'];assert v['technology_truth_scoring_required'] is True;assert v['source_reputation_required'] is True
 assert v['logician_falsification_required_for_material_claims'] is True;assert v['cross_source_corroboration_required_for_high_confidence'] is True
def test_agent_integration_prefers_domain_then_fallback():
 a=POL['agent_integration'];assert a['context_order']==['specialist_domain_memory','project_domain_memory','central_memory_fallback']
 assert a['agent_self_training_from_unverified_sources_forbidden'] is True

def test_expert_status_is_measured_and_benchmarked():
 s=POL['specialization_score'];assert s['minimum_expert_score']==80;assert s['expert_label_requires_benchmark_pass'] is True
 assert sum(s['dimensions'].values())==100;assert s['score_cannot_expand_permissions'] is True;assert s['score_cannot_self_promote_agent'] is True

def test_specialist_plane_is_shadow_only():
 assert POL['activation']['production_activation_authorized'] is False;assert POL['activation']['shadow_only'] is True
if __name__=='__main__':
 n=0
 for name,fn in sorted(globals().items()):
  if name.startswith('test_'):fn();print(name+'=PASS');n+=1
 print('CHACHA_DEV_DOMAIN_SPECIALIST_MEMORY=PASS');print('TEST_COUNT='+str(n));print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
