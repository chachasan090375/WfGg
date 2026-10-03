from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FAB=json.loads((ROOT/'dev-hub/config/specialization-fabric.v1.json').read_text())
ARC=json.loads((ROOT/'dev-hub/config/application-archetype-specialization.v1.json').read_text())
DOM=json.loads((ROOT/'dev-hub/config/domain-orchestration.v1.json').read_text())

def test_two_axes_share_one_canonical_memory_fabric():
 assert FAB['axes']['horizontal_domain']['model']=='HEAD_PLUS_ARM'
 assert FAB['axes']['vertical_application_archetype']['model']=='ARCHETYPE_HEAD_PLUS_ASSEMBLY_BLUEPRINT'
 assert FAB['canonical_memory_fabric']==ARC['canonical_memory_fabric']=='dev-hub/config/cognitive-memory-fabric.v1.json'
 assert FAB['rules']['single_canonical_memory_fabric_required'] is True

def test_archetypes_compose_existing_domains_without_duplicate_arms():
 domains=set(DOM['domains'])
 assert ARC['principles']['archetype_does_not_duplicate_domain_arms'] is True
 for aid,row in ARC['archetypes'].items():
  assert row['persistent'] is True,aid
  assert set(row['domain_weights']) <= domains,aid
  assert sum(row['domain_weights'].values())==100,aid

def test_required_foundation_archetypes_exist():
 assert {'game_realtime','business_management','system_infrastructure'} <= set(ARC['archetypes'])

def test_rare_archetypes_are_ephemeral_until_evidence_proves_them():
 d=ARC['dynamic_archetype_foundry']
 assert d['enabled_shadow_only'] is True and d['initial_state']=='EPHEMERAL_ARCHETYPE_PROFILE'
 assert d['minimum_accepted_projects_for_persistence']>=3
 assert d['benchmark_pass_required'] is True and d['technology_watch_revalidation_required'] is True
 assert d['logician_falsification_required'] is True and d['self_promotion_forbidden'] is True

def test_logician_becomes_cross_cutting_logic_math_specialist_without_final_authority():
 l=FAB['logician_specialization'];assert l['cross_cutting'] is True and l['final_decision_authority'] is False
 assert {'algorithms','mathematical_models','optimization','falsification','parallel_scenario_analysis'} <= set(l['competency_families'])

def test_technology_watch_updates_both_specialization_axes():
 w=FAB['technology_watch'];assert w['updates_horizontal_domain_knowledge'] is True and w['updates_vertical_archetype_knowledge'] is True
 assert w['technology_is_not_adopted_only_because_it_is_new'] is True and w['maturity_evidence_required'] is True

def test_cockpit_exposes_head_arm_archetype_and_cross_axis_progress():
 c=FAB['cockpit'];assert c['domain_icon_group_required'] is True and c['application_archetype_icon_group_required'] is True
 assert c['clickable_transparent_detail_overlay_required'] is True and c['detail_overlay_close_control_required'] is True
 assert {'head_score','arm_score','combined_expertise_score'} <= set(c['domain_metrics'])
 assert {'archetype_head_score','assembly_blueprint_score','demonstrated_delivery_score'} <= set(c['archetype_metrics'])
 assert 'cross_axis_readiness' in c['project_projection']

def test_specialization_never_expands_authority_or_spend():
 assert ARC['authority']['architecture_final_authority'] is False and ARC['authority']['permission_expansion_authority'] is False
 assert ARC['activation']['production_activation_authorized'] is False and FAB['activation']['production_activation_authorized'] is False
 assert FAB['automatic_external_spend_eur']==0 and ARC['principles']['automatic_external_spend_eur']==0

if __name__=='__main__':
 n=0
 for name,fn in sorted(globals().items()):
  if name.startswith('test_'):fn();print(name+'=PASS');n+=1
 print('CHACHA_DEV_SPECIALIZATION_FABRIC_2D=PASS');print('TEST_COUNT='+str(n));print('PRODUCTION_ACTIVATION=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
