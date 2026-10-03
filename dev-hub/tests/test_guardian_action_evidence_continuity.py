#!/usr/bin/env python3
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WORKER=(ROOT/'guardian/worker.js').read_text(encoding='utf-8')
POL=json.load(open(ROOT/'config/guardian-action-evidence-continuity.v1.json'))

def test_policy_is_fail_closed():
    assert POL['warning_before_deadline_seconds']==60
    assert POL['post_fabrication_forbidden'] is True
    assert POL['expired_action_replay_forbidden'] is True
    assert POL['canonical_stop_mutation'] is False
    assert POL['automatic_external_spend_eur']==0

def test_worker_warns_before_expiry():
    assert "deadline_at <= datetime('now','+60 seconds')" in WORKER
    assert 'POST_ACTION_DUE_SOON' in WORKER
    assert 'lease-post-due-' in WORKER

def test_post_action_acks_due_warning():
    needle="UPDATE guardian_alerts SET status='ACKED' WHERE alert_id=?1 AND status='OPEN'"
    assert needle in WORKER
    post=WORKER.index('if(phase==="POST_ACTION")')
    ack=WORKER.index('.bind("lease-post-due-"+actionId).run();')
    assert ack>post

def test_existing_expiry_and_reconciliation_remain():
    assert 'POST_ACTION_MISSING' in WORKER
    assert 'ACTION_LEASE_NOT_EXPIRED' in WORKER
    assert 'original_action_reexecuted:false' in WORKER
    assert 'action_evidence_continuity:true' in WORKER
