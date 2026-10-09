import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
from canonical_component_registry import validate_guardian_event_references as check


def test_canonical_role_is_not_dynamic_subject():
    try:
        check({"events": [{"subject_contract_id": "role:example"}]})
    except ValueError as error:
        assert "CANONICAL_ROLE_IN_DYNAMIC_SUBJECT_REFERENCE" in str(error)
    else:
        raise AssertionError("Canonical role must be rejected")


def test_canonical_actor_role_allowed():
    check({"events": [{"subject_role": "example",
                       "actor_contract_id": "role:example"}]})


def test_dynamic_subject_reference_allowed():
    check({"events": [{"subject_contract_id": "agent:example"}]})


if __name__ == "__main__":
    test_canonical_role_is_not_dynamic_subject()
    test_canonical_actor_role_allowed()
    test_dynamic_subject_reference_allowed()
    print("CONTRACT_REFERENCE_REGRESSION=PASS")
