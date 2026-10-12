package main

import rego.v1

stop_expected := {
  "missing": {"state": "UNKNOWN", "blocked": true},
  "corrupted": {"state": "UNKNOWN", "blocked": true},
  "invalid_type": {"state": "UNKNOWN", "blocked": true},
  "unreadable": {"state": "UNKNOWN", "blocked": true},
  "active": {"state": "ACTIVE", "blocked": true},
  "clear": {"state": "CLEAR", "blocked": false},
}

action_expected := {
  "success": {"phases": ["PRE_ACTION", "POST_ACTION"], "calls": 1, "returned": true, "outcome": "SUCCESS"},
  "nonzero": {"phases": ["PRE_ACTION", "POST_ACTION"], "calls": 1, "returned": false, "outcome": "FAILED"},
  "timeout": {"phases": ["PRE_ACTION", "POST_ACTION"], "calls": 1, "returned": false, "outcome": "TIMEOUT"},
  "spawn_error": {"phases": ["PRE_ACTION", "POST_ACTION"], "calls": 1, "returned": false, "outcome": "ERROR"},
  "pre_denied": {"phases": ["PRE_ACTION"], "calls": 0, "returned": false, "outcome": "NONE"},
  "post_denied": {"phases": ["PRE_ACTION", "POST_ACTION"], "calls": 1, "returned": false, "outcome": "SUCCESS"},
}

inventory_expected := {"below_limit": true, "at_limit": false, "malformed": false}

valid_stops if {
  is_array(input.stop_cases)
  count(input.stop_cases) == count(stop_expected)
  {x.name | some x in input.stop_cases} == object.keys(stop_expected)
  every x in input.stop_cases {
    x.state == stop_expected[x.name].state
    x.blocked == stop_expected[x.name].blocked
  }
}

valid_actions if {
  is_array(input.action_cases)
  count(input.action_cases) == count(action_expected)
  {x.name | some x in input.action_cases} == object.keys(action_expected)
  every x in input.action_cases {
    x.phases == action_expected[x.name].phases
    x.child_calls == action_expected[x.name].calls
    x.result_returned == action_expected[x.name].returned
    x.post_outcome == action_expected[x.name].outcome
    count(x.action_ids) == count(x.phases)
    count({id | some id in x.action_ids}) == 1
    every id in x.action_ids { is_string(id); startswith(id, "stage-"); count(id) > 6 }
  }
}

valid_inventories if {
  is_array(input.inventory_cases)
  count(input.inventory_cases) == count(inventory_expected)
  {x.name | some x in input.inventory_cases} == object.keys(inventory_expected)
  every x in input.inventory_cases { x.accepted == inventory_expected[x.name] }
}

valid_time if {
  is_string(input.observed_at)
  observed := time.parse_rfc3339_ns(input.observed_at)
  now := time.now_ns()
  observed <= now + 300000000000
  observed >= now - 3600000000000
}

valid_binding if {
  input.source_revision == data.expected.source_revision
  input.source_files == data.expected.source_files
  input.working_tree_modified == data.expected.working_tree_modified
  count(input.source_files) >= 4
}

deny contains "INPUT_OBJECT_REQUIRED" if { not is_object(input) }
deny contains "SCHEMA_INVALID" if { is_object(input); object.get(input, "schema", "") != "chacha.dev/local-safety-evidence/v1" }
deny contains "LOCAL_SCOPE_REQUIRED" if { is_object(input); object.get(input, "scope", "") != "LOCAL_FIXTURES_ONLY" }
deny contains "PRODUCTION_AUTHORITY_FORBIDDEN" if { is_object(input); object.get(input, "production_authorized", null) != false }
deny contains "STOP_BEHAVIOR_INVALID_OR_INCOMPLETE" if { not valid_stops }
deny contains "ACTION_LIFECYCLE_INVALID_OR_INCOMPLETE" if { not valid_actions }
deny contains "INVENTORY_BEHAVIOR_INVALID_OR_INCOMPLETE" if { not valid_inventories }
deny contains "SOURCE_BINDING_INVALID" if { not valid_binding }
deny contains "EVIDENCE_STALE_FUTURE_OR_INVALID" if { not valid_time }
