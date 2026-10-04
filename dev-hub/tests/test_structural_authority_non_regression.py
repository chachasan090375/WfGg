#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
C=json.loads((ROOT/"dev-hub/config/architecture-decision-council.v1.json").read_text())
L=json.loads((ROOT/"dev-hub/config/technology-watch-logician.v1.json").read_text())
assert C.get("central_orchestrator_is_final_decider") is True
assert C.get("agent_candidate_review",{}).get("architecture_council_may_auto_promote") is False
assert L.get("principles",{}).get("architecture_council_final_authority") is False
assert L.get("principles",{}).get("architecture_council_recommendation_authority") is True
assert "FINAL_ARCHITECTURE_DECISION" in L.get("structural_falsification",{}).get("forbidden_authorities",[])
assert "PROMOTE_RELEASE" in L.get("structural_falsification",{}).get("forbidden_authorities",[])
I=(ROOT/"dev-hub/bin/intendant-platform-consolidator.py").read_text()
assert 'ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=NO' in I
assert 'ARCHITECTURE_COUNCIL_RECOMMENDATION_AUTHORITY=YES' in I
print("CHACHA_DEV_STRUCTURAL_AUTHORITY_NON_REGRESSION=PASS")
