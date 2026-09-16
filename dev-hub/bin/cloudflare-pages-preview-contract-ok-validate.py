#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
contract = json.loads((ROOT/'dev-hub/config/cloudflare-pages-preview-contract.v1.json').read_text())
bindings = json.loads((ROOT/'dev-hub/config/cloudflare-pages-project-bindings.v1.json').read_text())
registry = json.loads((ROOT/'dev-hub/config/provider-adapters.v1.json').read_text())

assert contract['runtime_status'] == 'CONTRACT_OK'
assert contract['decision'] == 'ADOPT'
assert contract['security']['preview_only'] is True
assert contract['security']['production_deploy'] is False
assert contract['intent_contract']['caller_metadata_allowlist'] == ['source_commit_sha','source_branch']
assert contract['output_contract']['provider_result_trust'] == 'UNVERIFIED'
assert contract['contract_qualification']['production_branch_fail_closed'] is True
assert contract['contract_qualification']['caller_project_override_fail_closed'] is True
assert contract['contract_qualification']['workers_checks_excluded'] is True
assert contract['admission']['automatic_promotion'] is False
assert contract['admission']['next_transition'] == 'CONTRACT_OK->PILOT'

b = bindings['projects']['wfgg']
assert b['repository'] == 'chachasan090375/WfGg'
assert b['pages_project'] == 'wfgg'
assert b['production_branch'] == 'main'
assert b['github_check_name'] == 'Cloudflare Pages'
assert b['github_app_slug'] == 'cloudflare-workers-and-pages'
assert bindings['policy']['credentials_stored'] is False

ad = registry['adapters']['cloudflare-pages-adapter']
assert ad['status'] == 'CONTRACT_OK'
assert ad['executable'] is None
assert ad['supports'] == ['preview-deploy']

path = ROOT/'dev-hub/adapters/cloudflare-pages-adapter.py'
spec = importlib.util.spec_from_file_location('cfpages_adapter', path)
mod = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mod)

summary = """Preview URL: https://c132a897.wfgg.pages.dev\nBranch Preview URL: https://feature-x.wfgg.pages.dev"""
immutable, alias = mod.parse_preview_urls(summary, 'wfgg')
assert immutable == 'https://c132a897.wfgg.pages.dev'
assert alias == 'https://feature-x.wfgg.pages.dev'

check = {
  'id': 123,
  'name': 'Cloudflare Pages',
  'head_sha': 'a'*40,
  'status': 'completed',
  'conclusion': 'success',
  'external_id': 'deployment-id',
  'app': {'slug':'cloudflare-workers-and-pages'},
  'output': {'summary': summary},
}
worker = {
  'id': 456,
  'name': 'Workers Builds: wfgg-api',
  'head_sha': 'a'*40,
  'status': 'completed',
  'conclusion': 'success',
  'app': {'slug':'cloudflare-workers-and-pages'},
  'output': {'summary':'Preview URL: https://deadbeef-wfgg-api.example.workers.dev'},
}
selected, got_url, got_alias = mod.matching_check([worker, check], b, 'a'*40)
assert selected and selected['id'] == 123
assert got_url == immutable and got_alias == alias

base = {
  'schema':'chacha.dev/dispatch-envelope/v1','project':'wfgg',
  'task':{'id':'preview','permission':'preview-deploy'},
  'bindings':[{'provider':'cloudflare-pages','adapter':'cloudflare-pages-adapter'}],
  'metadata':{'cloudflare_pages':{'source_commit_sha':'a'*40,'source_branch':'feature-x'}},
}
os.environ['GITHUB_REPOSITORY'] = 'chachasan090375/WfGg'
os.environ['GITHUB_REF_NAME'] = 'feature-x'
_, _, err = mod.validate_request(base)
assert err is None, err
prod = json.loads(json.dumps(base)); prod['metadata']['cloudflare_pages']['source_branch']='main'
os.environ['GITHUB_REF_NAME'] = 'main'
_, _, err = mod.validate_request(prod)
assert err == 'CLOUDFLARE_PAGES_PRODUCTION_BRANCH_FORBIDDEN'
os.environ['GITHUB_REF_NAME'] = 'feature-x'
override = json.loads(json.dumps(base)); override['metadata']['cloudflare_pages']['project_name']='other'
_, _, err = mod.validate_request(override)
assert err == 'CLOUDFLARE_PAGES_CALLER_OVERRIDE_FORBIDDEN'
wrongperm = json.loads(json.dumps(base)); wrongperm['task']['permission']='production-deploy'
_, _, err = mod.validate_request(wrongperm)
assert err == 'CLOUDFLARE_PAGES_PREVIEW_PERMISSION_REQUIRED'

print('CLOUDFLARE_PAGES_PREVIEW_CONTRACT_OK=PASS')
print('PRODUCTION_BRANCH=BLOCKED')
print('CALLER_PROJECT_OVERRIDE=BLOCKED')
print('WORKERS_CHECK_SELECTION=IGNORED')
print('PROVIDER_RESULT_TRUST=UNVERIFIED')
