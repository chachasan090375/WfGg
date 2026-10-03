#!/usr/bin/env python3
from __future__ import annotations
import base64,importlib.util,json,tempfile,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def load(rel):return json.loads((ROOT/rel).read_text(encoding='utf-8'))
def mod():
 p=ROOT/'dev-hub/lib/direct_operator_m2m_auth.py';s=importlib.util.spec_from_file_location('m2m',p);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m
M=mod()

def registry(root:Path,enabled=True):
 secret=b'0123456789abcdef0123456789abcdef'
 p=root/'registry.json';p.write_text(json.dumps({'schema':M.REGISTRY_SCHEMA,'services':{'chacha-remote-operator-mcp':{'enabled':enabled,'secret_b64':base64.b64encode(secret).decode(),'allow':[{'method':'POST','path':'/api/v1/m2m/intent'},{'method':'GET','path_prefix':'/api/v1/m2m/jobs/'}]}}})+'\n')
 return p,secret

def test_valid_hmac_request_passes_and_identity_is_service_scoped():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);reg,secret=registry(root);store=M.FileNonceStore(root/'nonces',300);body=b'{"text":"go"}';now=1770000000
  h=M.build_headers('chacha-remote-operator-mcp',secret,'POST','/api/v1/m2m/intent',body,timestamp=now,nonce='nonce-1234567890abcdef')
  ident=M.verify_request(h,'POST','/api/v1/m2m/intent',body,registry_path=reg,nonce_claim=store.claim,now=now,max_clock_skew_seconds=30)
  assert ident.service_id=='chacha-remote-operator-mcp';assert ident.operator_identity=='service:chacha-remote-operator-mcp'

def test_nonce_replay_is_blocked():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);reg,secret=registry(root);store=M.FileNonceStore(root/'nonces',300);body=b'x';now=1770000000;nonce='nonce-abcdef1234567890'
  h=M.build_headers('chacha-remote-operator-mcp',secret,'POST','/api/v1/m2m/intent',body,timestamp=now,nonce=nonce)
  M.verify_request(h,'POST','/api/v1/m2m/intent',body,registry_path=reg,nonce_claim=store.claim,now=now)
  try:M.verify_request(h,'POST','/api/v1/m2m/intent',body,registry_path=reg,nonce_claim=store.claim,now=now);raise AssertionError('replay expected')
  except M.MachineAuthError as e:assert str(e)=='NONCE_REPLAYED'

def test_tampered_body_forbidden_route_disabled_service_and_stale_timestamp_fail_closed():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);reg,secret=registry(root);body=b'x';now=1770000000
  h=M.build_headers('chacha-remote-operator-mcp',secret,'POST','/api/v1/m2m/intent',body,timestamp=now,nonce='nonce-tamper123456789')
  try:M.verify_request(h,'POST','/api/v1/m2m/intent',b'y',registry_path=reg,nonce_claim=lambda *_:True,now=now);raise AssertionError('tamper expected')
  except M.MachineAuthError as e:assert str(e)=='BODY_DIGEST_MISMATCH'
  h2=M.build_headers('chacha-remote-operator-mcp',secret,'POST','/api/v1/forbidden',body,timestamp=now,nonce='nonce-route1234567890')
  try:M.verify_request(h2,'POST','/api/v1/forbidden',body,registry_path=reg,nonce_claim=lambda *_:True,now=now);raise AssertionError('route expected')
  except M.MachineAuthError as e:assert str(e)=='M2M_ROUTE_FORBIDDEN'
  reg2,_=registry(root,False)
  h3=M.build_headers('chacha-remote-operator-mcp',secret,'POST','/api/v1/m2m/intent',body,timestamp=now,nonce='nonce-disable12345678')
  try:M.verify_request(h3,'POST','/api/v1/m2m/intent',body,registry_path=reg2,nonce_claim=lambda *_:True,now=now);raise AssertionError('disabled expected')
  except M.MachineAuthError as e:assert str(e)=='SERVICE_NOT_AUTHORIZED'
  reg3,_=registry(root,True)
  h4=M.build_headers('chacha-remote-operator-mcp',secret,'POST','/api/v1/m2m/intent',body,timestamp=now-120,nonce='nonce-stale123456789')
  try:M.verify_request(h4,'POST','/api/v1/m2m/intent',body,registry_path=reg3,nonce_claim=lambda *_:True,now=now,max_clock_skew_seconds=30);raise AssertionError('stale expected')
  except M.MachineAuthError as e:assert str(e)=='TIMESTAMP_OUT_OF_WINDOW'

def test_current_line_birth_wrapper_passes_shadow_contract_shape():
 p=load('dev-hub/config/chacha-remote-operator-current-line.birth.v1.json');assert p['project_id']=='chacha-remote-operator';assert p['materialization_gate_required'] is True;assert p['runtime_secret_materialized'] is False;assert p['mcp_runtime_materialized'] is False;assert p['secure_tunnel_materialized'] is False;assert p['chatgpt_registration_complete'] is False;assert p['production_activation_authorized'] is False;assert p['automatic_external_spend_eur']==0


def test_machine_ingress_is_disabled_loopback_build_only_and_governed():
 p=load('dev-hub/config/direct-operator-machine-ingress.v1.json')
 assert p['enabled'] is False;assert p['transport']['bind']=='127.0.0.1';assert p['transport']['public_ingress_forbidden'] is True
 sc=p['service_contract'];assert sc['forced_channel']=='BUILD';assert sc['arbitrary_http_forbidden'] is True;assert sc['arbitrary_command_forbidden'] is True;assert sc['direct_central_orchestrator_call_forbidden'] is True;assert sc['direct_mutation_authority'] is False and sc['technical_decision_authority'] is False
 g=p['governance'];assert g['canonical_user_stop_state']=='/opt/chacha-dev/runtime/control/emergency-stop.json';assert g['canonical_user_stop_must_be_clear'] is True;assert g['downstream_guardian_required_before_mutation'] is True;assert g['sentinelle_required_before_production'] is True;assert g['umg_required'] is True and g['ccr_required'] is True;assert g['automatic_external_spend_eur']==0
 a=p['activation'];assert a['runtime_secret_materialized'] is False and a['direct_operator_handler_integrated'] is False and a['remote_mcp_client_integrated'] is False and a['pilot_allowed'] is False and a['production_activation_allowed'] is False

def test_chatgpt_exposure_is_private_disabled_and_not_source_of_truth():
 p=load('dev-hub/projects/chacha-remote-operator/config/chatgpt-exposure.v1.json')
 assert p['exposure_transport']['public_ingress_forbidden'] is True;assert p['exposure_transport']['mcp_must_remain_loopback_bound'] is True;assert p['exposure_transport']['automatic_external_spend_eur']==0
 assert p['direct_operator_target']['bridge_enabled'] is False;assert p['direct_operator_target']['direct_mutation_authority'] is False;assert p['direct_operator_target']['technical_decision_authority'] is False
 g=p['governance'];assert g['canonical_stop_required'] and g['guardian_required'] and g['sentinelle_required_before_production'] and g['bastion_required_for_network_exposure'] and g['umg_required'] and g['ccr_required'];assert g['chatgpt_is_not_operational_source_of_truth'] is True
 assert p['activation']['production_activation_allowed'] is False and p['activation']['runtime_secret_materialized'] is False and p['activation']['pilot_allowed_before_all_gates_pass'] is False

def test_runtime_materialization_remains_unmaterialized_human_boundary():
 p=load('dev-hub/projects/chacha-remote-operator/runtime.materialization.v1.json');a=p['activation'];t=p['secure_mcp_tunnel']
 assert a['mcp_source_qualified'] is True;assert a['tunnel_runtime_materialized'] is False;assert a['tunnel_identity_materialized'] is False;assert a['chatgpt_registration_complete'] is False;assert a['production_active'] is False
 assert t['status']=='UNMATERIALIZED';assert t['public_mcp_ingress_forbidden'] is True;assert t['network_initiation']=='OUTBOUND_ONLY';assert t['human_platform_provisioning_boundary'] is True
 assert p['governance']['automatic_external_spend_eur']==0

if __name__=='__main__':
 tests=[(n,v) for n,v in sorted(globals().items()) if n.startswith('test_') and callable(v)]
 for n,f in tests:f();print(n+'=PASS')
 print('CHACHA_DEV_REMOTE_MCP_CURRENT_LINE_CONVERGENCE=PASS');print('TEST_COUNT='+str(len(tests)));print('M2M_INGRESS_ENABLED=NO');print('REMOTE_MCP_RUNTIME_MATERIALIZED=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
