#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'config' / 'provider-selection-policy.v1.json'


def fail(msg):
    raise SystemExit(f'PROVIDER_SELECTION_POLICY_INVALID: {msg}')


def main():
    p = json.loads(POLICY.read_text(encoding='utf-8'))
    if p.get('schema') != 'chacha.dev/provider-selection-policy/v1':
        fail('schema')
    if p.get('engine') != 'provider-selection-engine' or p.get('mode') != 'PLAN_ONLY':
        fail('engine/mode')
    if p.get('decision_owner') != 'chacha-dev-architect' or p.get('dispatch_owner') != 'run-controller':
        fail('ownership separation')
    principles = p.get('principles', {})
    required_true = [
        'route_by_capability_not_vendor',
        'hard_policy_filters_before_scoring',
        'historical_quality_requires_verified_evidence',
        'selection_is_explainable',
        'selection_is_recorded',
        'selection_never_dispatches',
        'selection_never_changes_provider_status',
        'selection_never_bypasses_human_approval',
        'same_provider_cannot_produce_and_independently_verify_same_task',
        'insufficient_evidence_must_be_reported'
    ]
    for key in required_true:
        if principles.get(key) is not True:
            fail(key)
    eligibility = p.get('eligibility', {})
    if eligibility.get('require_adapter_runtime_status') != ['PILOT', 'ENABLED']:
        fail('runtime statuses')
    if eligibility.get('reject_unknown_health') is not True:
        fail('unknown health')
    weights = p.get('score', {}).get('weights', {})
    if sum(weights.values()) != 100:
        fail(f'weights sum={sum(weights.values())}')
    if set(weights) != {
        'task_capability_fit', 'verified_historical_quality', 'provider_health',
        'risk_fit', 'latency_fit', 'cost_fit', 'cross_provider_diversity'
    }:
        fail('weight dimensions')
    hist = p.get('score', {}).get('historical_window', {})
    if hist.get('minimum_verified_runs_for_confident_ranking', 0) < 3:
        fail('confidence sample too low')
    if p.get('output', {}).get('schema') != 'chacha.dev/provider-selection-plan/v1':
        fail('output schema')
    if p.get('output', {}).get('dispatch_authorized') is not False:
        fail('selector must not dispatch')
    if p.get('fallback', {}).get('scheduler_remains_authoritative_for_retry_and_failover') is not True:
        fail('scheduler authority')
    print('PROVIDER_SELECTION_POLICY_VALID: plan-only=true weights=100 scheduler_authoritative=true dispatch=false')


if __name__ == '__main__':
    main()
