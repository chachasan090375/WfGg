#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def load(rel):return json.loads((ROOT/rel).read_text())
def mod():
 p=ROOT/'dev-hub/bin/virtual-os-device-lab-planner.py';s=importlib.util.spec_from_file_location('v',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
M=mod();P=load('dev-hub/config/virtual-os-device-lab.v1.json');I=load('dev-hub/evidence/virtual-os-lab-host-inventory-observed-2026-10-03.json');E=load('dev-hub/config/virtual-os-image-registry.v1.json')
def one(family,purpose='compatibility_test',**kw):
 t={'target_id':'t','family':family,'version':'x','purpose':purpose};t.update(kw);return {'matrix_id':'m','targets':[t]}

def test_linux_native_build_routes_to_vps_without_vm_image():
 o=M.plan(one('linux','build'),I,E,P);assert o['status']=='PASS';assert o['routes'][0]['host_id']=='chacha-vps-current';assert o['routes'][0]['status']=='READY'

def test_web_runtime_routes_to_vps():
 o=M.plan(one('web_runtime'),I,E,P);assert o['routes'][0]['host_id']=='chacha-vps-current' and o['routes'][0]['status']=='READY'

def test_qnap_is_real_kvm_host_but_windows_requires_verified_image():
 o=M.plan(one('windows'),I,E,P);r=o['routes'][0];assert r['host_id']=='chachanas-qnap-kvm' and r['status']=='READY_HOST_IMAGE_REQUIRED';assert o['gaps'][0]['kind']=='VERIFIED_BASE_IMAGE_MISSING'

def test_freebsd_can_use_qnap_after_verified_image():
 imgs=copy.deepcopy(E);imgs['images']=[{'image_id':'freebsd-test','family':'freebsd_unix','version':'x','sha256':'sha256:'+'1'*64,'verified':True,'immutable':True}]
 o=M.plan(one('freebsd_unix'),I,imgs,P);assert o['status']=='PASS';assert o['routes'][0]['host_id']=='chachanas-qnap-kvm';assert o['routes'][0]['image_id']=='freebsd-test'

def test_unverified_or_unhashed_image_never_satisfies_requirement():
 imgs=copy.deepcopy(E);imgs['images']=[{'image_id':'bad','family':'windows','verified':False,'sha256':'nope'}]
 o=M.plan(one('windows'),I,imgs,P);assert o['routes'][0]['status']=='READY_HOST_IMAGE_REQUIRED'

def test_ios_and_macos_require_apple_native_runner():
 for fam,role in [('ios','apple-native-ios'),('macos','apple-native-macos')]:
  o=M.plan(one(fam,'build'),I,E,P);assert o['routes'][0]['status']=='BLOCKED_RUNNER_MISSING';assert role in o['routes'][0]['required_roles']

def test_android_accelerated_emulator_does_not_fall_back_to_qnap_nested_vm():
 o=M.plan(one('android','accelerated_emulator'),I,E,P);assert o['routes'][0]['status']=='BLOCKED_RUNNER_MISSING';assert 'android-emulator-native-host' in o['routes'][0]['required_roles'];assert all(r.get('host_id')!='chachanas-qnap-kvm' for r in o['routes'])

def test_hardware_specific_validation_requires_physical_device():
 o=M.plan(one('android','compatibility_test',hardware_specific=True),I,E,P);assert o['routes'][0]['status']=='BLOCKED_RUNNER_MISSING';assert 'physical-device:android' in o['routes'][0]['required_roles']

def test_qnap_inventory_proves_virtualization_station_and_no_existing_vms():
 q=next(h for h in I['hosts'] if h['host_id']=='chachanas-qnap-kvm');v=q['virtualization_station'];assert v['enabled'] is True and v['dev_kvm'] is True and v['kvm_intel_loaded'] is True and v['libvirtd_running'] is True and v['defined_vm_count']==0;assert q['ram_total_gib']>7.5

def test_no_automatic_provisioning_spend_or_authority():
 o=M.plan(one('ios','build'),I,E,P);assert o['automatic_provisioning'] is False and o['automatic_external_spend_eur']==0 and o['execution_authority'] is False and o['production_authority'] is False

def test_birth_contract_is_shadow_and_umg_required():
 b=load('dev-hub/config/virtual-os-device-lab.birth.v1.json');assert b['materialization_gate_required'] is True and b['production_activation_authorized'] is False
if __name__=='__main__':
 tests=[(n,v) for n,v in sorted(globals().items()) if n.startswith('test_') and callable(v)]
 for n,f in tests:f();print(n+'=PASS')
 print('CHACHA_DEV_VIRTUAL_OS_DEVICE_LAB=PASS');print('TEST_COUNT='+str(len(tests)));print('PRODUCTION_ACTIVATION=NO');print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
