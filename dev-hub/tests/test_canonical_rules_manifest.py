#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/'config'
manifest=json.loads((CFG/'canonical-rules-manifest.v1.json').read_text())
supp=json.loads((CFG/'canonical-rules-supplement.v1.json').read_text())
remote=json.loads((CFG/'remote-mcp-primary-route.v1.json').read_text())
assert manifest['authority']=='PRIMARY_CANONICAL_RULE_INDEX'
assert manifest['principles']['rules_are_not_memory_only'] is True
assert manifest['principles']['prompt_sent_is_not_application_proof'] is True
assert manifest['principles']['automatic_external_spend_eur']==0
ids=[r['rule_id'] for r in supp['rules']]
assert len(ids)==len(set(ids))
required={'canon-anti-loop','canon-stop-latch','canon-human-production-authority','canon-local-sqlite-authority','canon-native-local-ha-off-by-default','canon-remote-mcp-capability-safety','canon-wfgg-last-war-read-only','canon-consultant-project-tenancy'}
assert required.issubset(set(ids))
assert remote['invariant']['primary_route']=='CHACHA_PROPRIETARY_REMOTE_MCP'
assert remote['invariant']['remote_desktop_commander_is_fallback_only'] is True
assert manifest['application_state']['propagated_to_runtime'] is False
print('CHACHA_DEV_CANONICAL_RULES_MANIFEST=PASS')
print('SUPPLEMENT_RULE_COUNT='+str(len(ids)))
print('REMOTE_PRIMARY_ROUTE=CHACHA_PROPRIETARY_REMOTE_MCP')
